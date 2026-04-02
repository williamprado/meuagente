package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	qrcode "github.com/skip2/go-qrcode"
	_ "github.com/mattn/go-sqlite3"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	waLog "go.mau.fi/whatsmeow/util/log"
	"go.mau.fi/whatsmeow/types/events"
	waProto "go.mau.fi/whatsmeow/proto/waE2E"
	"google.golang.org/protobuf/proto"
)

type Config struct {
	ListenAddr string
	BackendURL string
	DataSource string
}

type App struct {
	cfg        Config
	client     *whatsmeow.Client
	httpClient *http.Client

	mu            sync.RWMutex
	lastQRCode    string
	lastQRAt      time.Time
	statusMessage string
}

type statusResponse struct {
	Connected     bool   `json:"connected"`
	LoggedIn      bool   `json:"logged_in"`
	Status        string `json:"status"`
	Phone         string `json:"phone,omitempty"`
	QRAvailable   bool   `json:"qr_available"`
	LastQRAt      string `json:"last_qr_at,omitempty"`
	BackendTarget string `json:"backend_target"`
}

type qrResponse struct {
	Status  string `json:"status"`
	QRCode  string `json:"qr_code,omitempty"`
	Updated string `json:"updated,omitempty"`
}

type inboundPayload struct {
	Sender         string `json:"sender"`
	SenderName     string `json:"sender_name,omitempty"`
	Message        string `json:"message"`
	ConversationID string `json:"conversation_id,omitempty"`
}

type backendReply struct {
	Reply string `json:"reply"`
}

func main() {
	cfg := Config{
		ListenAddr: getenv("WHATSAPP_LISTEN_ADDR", ":8081"),
		BackendURL: strings.TrimRight(getenv("WHATSAPP_BACKEND_URL", "http://backend:8000/api"), "/"),
		DataSource: getenv("WHATSAPP_SQLITE_DSN", "file:/data/whatsapp.db?_foreign_keys=on"),
	}

	app, err := newApp(cfg)
	if err != nil {
		log.Fatalf("erro iniciando app: %v", err)
	}

	go app.ensureConnected(context.Background())

	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.handleHealth)
	mux.HandleFunc("/status", app.handleStatus)
	mux.HandleFunc("/connect", app.handleConnect)
	mux.HandleFunc("/qr", app.handleQR)

	server := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           withCORS(mux),
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("whatsapp service em %s", cfg.ListenAddr)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("erro no servidor http: %v", err)
	}
}

func newApp(cfg Config) (*App, error) {
	container, err := sqlstore.New(context.Background(), "sqlite3", cfg.DataSource, waLog.Noop)
	if err != nil {
		return nil, fmt.Errorf("abrindo sqlstore: %w", err)
	}

	deviceStore, err := container.GetFirstDevice(context.Background())
	if err != nil {
		return nil, fmt.Errorf("obtendo device store: %w", err)
	}

	client := whatsmeow.NewClient(deviceStore, waLog.Stdout("WhatsMeow", "INFO", true))

	app := &App{
		cfg:        cfg,
		client:     client,
		httpClient: &http.Client{Timeout: 60 * time.Second},
	}
	app.setStatus("idle")
	client.AddEventHandler(app.handleEvent)
	return app, nil
}

func (a *App) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *App) handleStatus(w http.ResponseWriter, _ *http.Request) {
	a.mu.RLock()
	resp := statusResponse{
		Connected:     a.client.IsConnected(),
		LoggedIn:      a.client.IsLoggedIn(),
		Status:        a.statusMessage,
		QRAvailable:   a.lastQRCode != "",
		BackendTarget: a.cfg.BackendURL,
	}
	if a.client.Store.ID != nil {
		resp.Phone = a.client.Store.ID.User
	}
	if !a.lastQRAt.IsZero() {
		resp.LastQRAt = a.lastQRAt.Format(time.RFC3339)
	}
	a.mu.RUnlock()
	writeJSON(w, http.StatusOK, resp)
}

func (a *App) handleConnect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	go a.ensureConnected(r.Context())
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "connecting"})
}

func (a *App) handleQR(w http.ResponseWriter, _ *http.Request) {
	a.mu.RLock()
	code := a.lastQRCode
	ts := a.lastQRAt
	status := a.statusMessage
	a.mu.RUnlock()

	if code == "" {
		writeJSON(w, http.StatusOK, qrResponse{Status: status})
		return
	}

	png, err := qrcode.Encode(code, qrcode.Medium, 320)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, qrResponse{
		Status:  status,
		QRCode:  "data:image/png;base64," + base64.StdEncoding.EncodeToString(png),
		Updated: ts.Format(time.RFC3339),
	})
}

func (a *App) ensureConnected(ctx context.Context) {
	if a.client.IsConnected() {
		a.setStatus("connected")
		return
	}

	if a.client.Store.ID == nil {
		qrChan, err := a.client.GetQRChannel(ctx)
		if err != nil {
			a.setStatus("qr_error")
			log.Printf("erro obtendo canal QR: %v", err)
			return
		}
		if err := a.client.Connect(); err != nil {
			a.setStatus("connect_error")
			log.Printf("erro conectando: %v", err)
			return
		}
		a.setStatus("waiting_qr_scan")
		for evt := range qrChan {
			switch evt.Event {
			case "code":
				a.setQRCode(evt.Code)
			case "success":
				a.clearQRCode()
				a.setStatus("connected")
			case "timeout":
				a.setStatus("qr_timeout")
			default:
				a.setStatus(evt.Event)
			}
		}
		return
	}

	if err := a.client.Connect(); err != nil {
		a.setStatus("connect_error")
		log.Printf("erro reconectando: %v", err)
		return
	}
	a.setStatus("connected")
}

func (a *App) handleEvent(evt interface{}) {
	switch v := evt.(type) {
	case *events.Connected:
		a.clearQRCode()
		a.setStatus("connected")
	case *events.Disconnected:
		a.setStatus("disconnected")
	case *events.LoggedOut:
		a.clearQRCode()
		a.setStatus("logged_out")
	case *events.Message:
		a.handleIncomingMessage(v)
	}
}

func (a *App) handleIncomingMessage(evt *events.Message) {
	if evt.Info.IsFromMe || evt.Info.Chat.Server != "s.whatsapp.net" {
		return
	}
	msg := extractText(evt)
	if strings.TrimSpace(msg) == "" {
		return
	}

	payload := inboundPayload{
		Sender:         evt.Info.Sender.String(),
		SenderName:     evt.Info.PushName,
		Message:        msg,
		ConversationID: evt.Info.Chat.String(),
	}

	reply, err := a.requestReply(payload)
	if err != nil {
		log.Printf("erro gerando resposta para %s: %v", payload.Sender, err)
		return
	}

	if err := a.sendText(evt.Info.Chat.String(), reply); err != nil {
		log.Printf("erro enviando resposta para %s: %v", payload.Sender, err)
	}
}

func extractText(evt *events.Message) string {
	if evt.Message == nil {
		return ""
	}
	if conversation := evt.Message.GetConversation(); conversation != "" {
		return conversation
	}
	if extended := evt.Message.GetExtendedTextMessage(); extended != nil {
		return extended.GetText()
	}
	return ""
}

func (a *App) requestReply(payload inboundPayload) (string, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequest(http.MethodPost, a.cfg.BackendURL+"/whatsapp/inbound", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return "", fmt.Errorf("backend retornou status %d", resp.StatusCode)
	}

	var reply backendReply
	if err := json.NewDecoder(resp.Body).Decode(&reply); err != nil {
		return "", err
	}
	return reply.Reply, nil
}

func (a *App) sendText(chat string, text string) error {
	jid, err := types.ParseJID(chat)
	if err != nil {
		return err
	}
	_, err = a.client.SendMessage(context.Background(), jid, &waProto.Message{
		Conversation: proto.String(text),
	})
	return err
}

func (a *App) setQRCode(code string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.lastQRCode = code
	a.lastQRAt = time.Now().UTC()
}

func (a *App) clearQRCode() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.lastQRCode = ""
	a.lastQRAt = time.Time{}
}

func (a *App) setStatus(status string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.statusMessage = status
}

func getenv(key string, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func init() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
}
