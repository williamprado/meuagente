const apiBase = "/api";
const waBase = "/whatsapp-api";
const QR_TTL_MS = 60 * 1000;
const PHONE_STORAGE_KEY = "meuagente.whatsapp.phone";

let conversationId = crypto.randomUUID();
let toastTimer = null;

const state = {
  chatPending: false,
  whatsapp: {
    status: null,
    qr: null,
    error: null,
    isConnecting: false,
  },
};

const elements = {
  tokenInput: document.getElementById("openai-token"),
  tokenSource: document.getElementById("token-source"),
  contentName: document.getElementById("content-name"),
  trainingContent: document.getElementById("training-content"),
  chunkStrategy: document.getElementById("chunk-strategy"),
  chunkSize: document.getElementById("chunk-size"),
  chunkOverlap: document.getElementById("chunk-overlap"),
  chatWindow: document.getElementById("chat-window"),
  chatMessage: document.getElementById("chat-message"),
  sendChat: document.getElementById("send-chat"),
  backendHealthDot: document.getElementById("backend-health-dot"),
  backendHealthText: document.getElementById("backend-health-text"),
  whatsappPhoneInput: document.getElementById("whatsapp-phone-input"),
  whatsappConnectionState: document.getElementById("whatsapp-connection-state"),
  whatsappFeedback: document.getElementById("whatsapp-feedback"),
  whatsappPhoneDisplay: document.getElementById("whatsapp-phone-display"),
  whatsappStatusDetail: document.getElementById("whatsapp-status-detail"),
  whatsappStatusBadge: document.getElementById("whatsapp-status-badge"),
  whatsappQR: document.getElementById("whatsapp-qr"),
  qrEmpty: document.getElementById("qr-empty"),
  qrEmptyTitle: document.getElementById("qr-empty-title"),
  qrEmptyText: document.getElementById("qr-empty-text"),
  generateWhatsAppQR: document.getElementById("generate-whatsapp-qr"),
  connectWhatsApp: document.getElementById("connect-whatsapp"),
  renewWhatsAppQR: document.getElementById("renew-whatsapp-qr"),
  copyWhatsAppStatus: document.getElementById("copy-whatsapp-status"),
  toast: document.getElementById("toast"),
};

document.getElementById("save-token").addEventListener("click", () => {
  saveToken().catch((error) => showToast(error.message, true));
});
document.getElementById("ingest-content").addEventListener("click", () => {
  ingestContent().catch((error) => showToast(error.message, true));
});
elements.sendChat.addEventListener("click", () => {
  sendChat().catch((error) => showToast(error.message, true));
});
elements.generateWhatsAppQR.addEventListener("click", () => {
  triggerWhatsAppConnection("generate").catch((error) => showToast(error.message, true));
});
elements.connectWhatsApp.addEventListener("click", () => {
  triggerWhatsAppConnection("connect").catch((error) => showToast(error.message, true));
});
elements.renewWhatsAppQR.addEventListener("click", () => {
  triggerWhatsAppConnection("renew").catch((error) => showToast(error.message, true));
});
elements.copyWhatsAppStatus.addEventListener("click", copyWhatsAppStatus);
elements.whatsappPhoneInput.addEventListener("input", handlePhoneInput);
elements.chatMessage.addEventListener("keydown", handleChatKeyDown);

restorePhoneDraft();
appendMessage(
  "agent",
  "Painel pronto. Configure o token, treine o conteúdo, conecte o WhatsApp e teste seu agente aqui."
);
refreshSummary();
refreshHealth();
refreshWhatsApp();
updateChatComposer();
setInterval(refreshHealth, 10000);
setInterval(refreshWhatsApp, 12000);
setInterval(renderWhatsAppPanel, 1000);

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || payload.error || `Erro ${response.status}`);
  }

  return response.json();
}

function currentToken() {
  const token = elements.tokenInput.value.trim();
  return token || null;
}

function digitsOnly(value) {
  return (value || "").replace(/\D/g, "");
}

function formatPhone(value) {
  let digits = digitsOnly(value).slice(0, 13);
  if (!digits) {
    return "";
  }

  if (!digits.startsWith("55")) {
    digits = `55${digits}`.slice(0, 13);
  }

  const country = digits.slice(0, 2);
  const area = digits.slice(2, 4);
  const local = digits.slice(4);
  const firstBlockSize = local.length > 8 ? 5 : 4;
  const firstBlock = local.slice(0, firstBlockSize);
  const secondBlock = local.slice(firstBlockSize);

  let formatted = `+${country}`;

  if (area) {
    formatted += ` (${area}`;
    if (area.length === 2) {
      formatted += ")";
    }
  }

  if (firstBlock) {
    formatted += ` ${firstBlock}`;
  }

  if (secondBlock) {
    formatted += `-${secondBlock}`;
  }

  return formatted.trim();
}

function handlePhoneInput(event) {
  const formatted = formatPhone(event.target.value);
  event.target.value = formatted;
  persistPhoneDraft(formatted);
  renderWhatsAppPanel();
}

function persistPhoneDraft(value) {
  try {
    if (value) {
      localStorage.setItem(PHONE_STORAGE_KEY, value);
    } else {
      localStorage.removeItem(PHONE_STORAGE_KEY);
    }
  } catch (error) {
    console.debug("Não foi possível salvar rascunho do número.", error);
  }
}

function restorePhoneDraft() {
  try {
    const draft = localStorage.getItem(PHONE_STORAGE_KEY);
    if (draft) {
      elements.whatsappPhoneInput.value = formatPhone(draft);
    }
  } catch (error) {
    console.debug("Não foi possível restaurar rascunho do número.", error);
  }
}

function formatCountdown(msRemaining) {
  const totalSeconds = Math.max(0, Math.floor(msRemaining / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function getQrExpiresAt() {
  const updated = state.whatsapp.qr?.updated;
  if (!updated) {
    return null;
  }

  const timestamp = Date.parse(updated);
  return Number.isNaN(timestamp) ? null : timestamp + QR_TTL_MS;
}

function getPreferredPhone() {
  return formatPhone(state.whatsapp.status?.phone) || elements.whatsappPhoneInput.value || "-";
}

function setStatusBadge(label, toneClass) {
  elements.whatsappStatusBadge.textContent = label;
  elements.whatsappStatusBadge.classList.remove(
    "status-online",
    "status-offline",
    "status-pending",
    "status-expired",
    "status-error"
  );
  elements.whatsappStatusBadge.classList.add(toneClass);
}

function setButtonVisibility(button, isVisible) {
  button.classList.toggle("is-hidden", !isVisible);
}

function renderWhatsAppPanel() {
  const status = state.whatsapp.status;
  const qr = state.whatsapp.qr;
  const error = state.whatsapp.error;
  const rawStatus = error ? "erro" : status?.status || "idle";
  const hasQr = Boolean(qr?.qr_code);
  const isConnected = Boolean(status?.connected);
  const expiresAt = getQrExpiresAt();
  const msRemaining = expiresAt ? expiresAt - Date.now() : 0;
  const isQrExpired =
    rawStatus === "qr_timeout" || (hasQr && expiresAt !== null && msRemaining <= 0);

  let connectionLabel = "Não conectado";
  let feedback = "Gere um QR Code para iniciar a conexão com o WhatsApp.";
  let badgeLabel = "Offline";
  let badgeTone = "status-offline";
  let emptyTitle = "QR indisponível no momento";
  let emptyText = "Clique em Gerar QR Code para iniciar a conexão do número.";

  if (error) {
    feedback = `Não foi possível consultar o WhatsApp agora. ${error}`;
    badgeTone = "status-error";
    emptyTitle = "Falha ao carregar";
    emptyText = "Não conseguimos consultar o QR Code agora.";
  } else if (isConnected) {
    connectionLabel = "Conectado";
    feedback = "Conectado com sucesso ✅ Seu agente já pode responder.";
    badgeLabel = "Online";
    badgeTone = "status-online";
    emptyTitle = "Número conectado";
    emptyText = "O QR some assim que a conexão é concluída.";
  } else if (state.whatsapp.isConnecting && !hasQr) {
    connectionLabel = "Conectando...";
    feedback = "Estamos preparando o QR Code para esse número.";
    badgeTone = "status-pending";
    emptyTitle = "Gerando QR Code";
    emptyText = "Em instantes o código aparece aqui para escanear.";
  } else if (hasQr && !isQrExpired) {
    connectionLabel = "Conectando...";
    feedback = "QR gerado. Abra o WhatsApp no celular e escaneie o código para concluir.";
    badgeLabel = `Expira em ${formatCountdown(msRemaining)}`;
    badgeTone = "status-pending";
  } else if (isQrExpired) {
    feedback = "QR expirou. Clique em Renovar.";
    badgeLabel = "Expirado";
    badgeTone = "status-expired";
    emptyTitle = "QR expirado";
    emptyText = "Clique em Renovar para gerar um novo código e continuar.";
  } else if (rawStatus === "logged_out") {
    feedback = "A sessão foi desconectada. Gere um novo QR Code para reconectar.";
    emptyTitle = "Sessão desconectada";
    emptyText = "Gere um QR Code para conectar novamente este número.";
  } else if (rawStatus === "connect_error" || rawStatus === "qr_error") {
    feedback = "Não conseguimos iniciar a conexão. Tente gerar um novo QR Code.";
    badgeTone = "status-error";
    emptyTitle = "Conexão indisponível";
    emptyText = "Tente novamente para criar um novo QR Code.";
  }

  elements.whatsappConnectionState.textContent = connectionLabel;
  elements.whatsappFeedback.textContent = feedback;
  elements.whatsappPhoneDisplay.textContent = getPreferredPhone();
  elements.whatsappStatusDetail.textContent = rawStatus;
  setStatusBadge(badgeLabel, badgeTone);

  if (status?.phone) {
    const formattedPhone = formatPhone(status.phone);
    elements.whatsappPhoneInput.value = formattedPhone;
    persistPhoneDraft(formattedPhone);
  }

  if (hasQr && !isQrExpired && !isConnected && !error) {
    elements.whatsappQR.src = qr.qr_code;
    elements.whatsappQR.style.display = "block";
    elements.qrEmpty.style.display = "none";
  } else {
    elements.whatsappQR.style.display = "none";
    elements.qrEmpty.style.display = "flex";
    elements.qrEmptyTitle.textContent = emptyTitle;
    elements.qrEmptyText.textContent = emptyText;
  }

  const showRenew = !isConnected && isQrExpired;
  const showConnect = !isConnected && hasQr && !isQrExpired && !error;
  const showGenerate = !isConnected && !showConnect && !showRenew;

  setButtonVisibility(elements.generateWhatsAppQR, showGenerate);
  setButtonVisibility(elements.connectWhatsApp, showConnect);
  setButtonVisibility(elements.renewWhatsAppQR, showRenew);

  elements.generateWhatsAppQR.disabled = state.whatsapp.isConnecting;
  elements.connectWhatsApp.disabled = state.whatsapp.isConnecting;
  elements.renewWhatsAppQR.disabled = state.whatsapp.isConnecting;
}

function updateChatComposer() {
  elements.sendChat.disabled = state.chatPending;
  elements.sendChat.textContent = state.chatPending ? "Enviando..." : "Enviar";
}

function appendMessage(role, text) {
  const row = document.createElement("div");
  row.className = `chat-row ${role}`;

  const meta = document.createElement("span");
  meta.className = "chat-meta";
  meta.textContent = role === "user" ? "Você" : "Agente";

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.textContent = text;

  row.appendChild(meta);
  row.appendChild(bubble);
  elements.chatWindow.appendChild(row);
  elements.chatWindow.scrollTop = elements.chatWindow.scrollHeight;
}

function handleChatKeyDown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!state.chatPending) {
      sendChat().catch((error) => showToast(error.message, true));
    }
  }
}

async function refreshSummary() {
  try {
    const summary = await request(`${apiBase}/settings`, { method: "GET" });
    elements.tokenSource.textContent = summary.has_server_token
      ? "Token salvo no servidor"
      : "Sem token salvo";
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshHealth() {
  try {
    const health = await request(`${apiBase}/health`, { method: "GET" });
    const ok = health.status === "ok";
    elements.backendHealthDot.classList.toggle("ok", ok);
    elements.backendHealthText.textContent = ok
      ? `Aplicação saudável · Vetor ${health.vector_db}`
      : "Aplicação indisponível";
  } catch (error) {
    elements.backendHealthDot.classList.remove("ok");
    elements.backendHealthText.textContent = `Falha ao consultar saúde: ${error.message}`;
  }
}

async function saveToken() {
  const token = currentToken();
  if (!token) {
    showToast("Informe um token OpenAI para salvar.", true);
    return;
  }

  await request(`${apiBase}/config/token`, {
    method: "POST",
    body: JSON.stringify({ openai_api_key: token }),
  });

  elements.tokenSource.textContent = "Token salvo no servidor";
  showToast("Token salvo no backend.");
}

async function ingestContent() {
  const content = elements.trainingContent.value.trim();
  if (!content) {
    showToast("Informe conteúdo para ingestão.", true);
    return;
  }

  const payload = {
    name: elements.contentName.value.trim() || "Base manual",
    content,
    chunk_strategy: elements.chunkStrategy.value,
    chunk_size: Number(elements.chunkSize.value),
    chunk_overlap: Number(elements.chunkOverlap.value),
    openai_api_key: currentToken(),
  };

  const response = await request(`${apiBase}/ingest`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  showToast(`Conteúdo ingerido com sucesso em ${response.stored_path}.`);
}

async function sendChat() {
  if (state.chatPending) {
    return;
  }

  const message = elements.chatMessage.value.trim();
  if (!message) {
    showToast("Digite uma mensagem para conversar com o agente.", true);
    return;
  }

  state.chatPending = true;
  updateChatComposer();
  appendMessage("user", message);
  elements.chatMessage.value = "";

  try {
    const response = await request(`${apiBase}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        openai_api_key: currentToken(),
        use_rag: true,
      }),
    });

    conversationId = response.conversation_id;
    appendMessage("agent", response.answer);
  } catch (error) {
    appendMessage("agent", `Não consegui responder agora. ${error.message}`);
  } finally {
    state.chatPending = false;
    updateChatComposer();
    elements.chatMessage.focus();
  }
}

async function triggerWhatsAppConnection(intent) {
  state.whatsapp.isConnecting = true;
  renderWhatsAppPanel();

  try {
    await request(`${waBase}/connect`, { method: "POST", body: "{}" });
    if (intent === "renew") {
      showToast("Solicitação enviada. Gerando um novo QR Code.");
    } else if (intent === "connect") {
      showToast("Tentando concluir a conexão com o WhatsApp.");
    } else {
      showToast("Solicitação enviada. Gerando QR Code do WhatsApp.");
    }

    await refreshWhatsApp();
  } finally {
    state.whatsapp.isConnecting = false;
    renderWhatsAppPanel();
  }
}

async function refreshWhatsApp() {
  try {
    const [status, qr] = await Promise.all([
      request(`${waBase}/status`, { method: "GET" }),
      request(`${waBase}/qr`, { method: "GET" }),
    ]);

    state.whatsapp.status = status;
    state.whatsapp.qr = qr;
    state.whatsapp.error = null;
  } catch (error) {
    state.whatsapp.error = error.message;
  } finally {
    renderWhatsAppPanel();
  }
}

async function copyWhatsAppStatus() {
  const summary = [
    `Status do número: ${elements.whatsappConnectionState.textContent}`,
    `Badge: ${elements.whatsappStatusBadge.textContent}`,
    `Número ativo: ${elements.whatsappPhoneDisplay.textContent}`,
    `Status técnico: ${elements.whatsappStatusDetail.textContent}`,
    `Atualizado em: ${new Date().toLocaleString("pt-BR")}`,
  ].join("\n");

  try {
    await navigator.clipboard.writeText(summary);
    showToast("Status copiado para a área de transferência.");
  } catch (error) {
    showToast("Não foi possível copiar o status.", true);
  }
}

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.style.background = isError ? "rgba(180, 67, 67, 0.94)" : "rgba(23, 23, 23, 0.94)";
  elements.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 2600);
}
