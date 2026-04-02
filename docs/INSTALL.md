# Instalação com Docker Compose

## Objetivo

Subir o projeto localmente ou em um servidor simples usando `docker compose`.

## Pré-requisitos

- Docker instalado
- Docker Compose Plugin disponível

Verifique:

```bash
docker --version
docker compose version
```

## 1. Configurar ambiente

No diretório do projeto:

```bash
cp .env.example .env
```

Edite o arquivo `.env` e ajuste no mínimo:

- `POSTGRES_PASSWORD`
- `MEUAGENTE_WHATSAPP_VERIFY_TOKEN`
- `CORS_ORIGINS`

Para uso local, você pode deixar:

```env
APP_DOMAIN=localhost
CORS_ORIGINS=*
```

## 2. Subir os containers

```bash
docker compose up -d --build
```

## 3. Validar serviços

Painel:

```bash
curl http://localhost:8080
```

Backend:

```bash
curl http://localhost:8000/api/health
```

WhatsApp:

```bash
curl http://localhost:8081/status
```

## 4. Uso inicial

1. Abra `http://localhost:8080`
2. Salve um token OpenAI
3. Faça a ingestão do conteúdo
4. Gere o QR Code do WhatsApp
5. Teste a conversa no painel

## Comandos úteis

Subir:

```bash
docker compose up -d
```

Rebuildar:

```bash
docker compose up -d --build
```

Ver logs:

```bash
docker compose logs -f
```

Parar:

```bash
docker compose down
```

Parar removendo volumes:

```bash
docker compose down -v
```

## Persistência

Os dados ficam em volumes Docker nomeados:

- `backend_data`
- `whatsapp_data`
- `vector_db_data`

## Observações

- O token OpenAI salvo pelo painel fica em volume persistente do backend.
- O QR e a sessão do WhatsApp ficam persistidos no volume do serviço `whatsapp`.
- O frontend já faz proxy interno para backend e WhatsApp.
