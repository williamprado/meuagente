# Meu Agente IA

Aplicação full stack para operar um agente com RAG e integração com WhatsApp Web.

O projeto foi preparado para repositório público e uso em produção:

- sem credenciais reais versionadas
- com `.gitignore` reforçado para arquivos locais e sensíveis
- com variáveis de ambiente por arquivo de exemplo
- com instalação via `docker compose`
- com deploy via `docker stack deploy` e Portainer

## Componentes

- `frontend/`: painel web em HTML, CSS e JavaScript servido por Nginx
- `backend/`: API `FastAPI` com RAG, ingestão e chat
- `whatsapp/`: microserviço `Go + whatsmeow` com QR Code e sessão persistente
- `deploy/`: artefatos de infraestrutura para Docker Swarm

## Arquitetura

1. O usuário acessa o painel web.
2. O frontend faz proxy interno para `/api` e `/whatsapp-api`.
3. O backend processa token, ingestão e chat.
4. O banco vetorial roda em `PgVector/PostgreSQL`.
5. O serviço de WhatsApp recebe mensagens, consulta o backend e responde.

## Requisitos

- Docker 24+ com Compose Plugin
- Para produção em Swarm: Docker Swarm inicializado
- Rede externa Traefik já existente: `waianet`
- DNS apontando para o host do Traefik

## Variáveis de ambiente

Copie o exemplo:

```bash
cp .env.example .env
```

Preencha principalmente:

- `APP_DOMAIN`
- `CORS_ORIGINS`
- `POSTGRES_PASSWORD`
- `MEUAGENTE_WHATSAPP_VERIFY_TOKEN`

Nunca versione `.env`, `.env.production` ou qualquer arquivo real de segredo.

## Instalação rápida com Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Acesse:

- Painel: `http://localhost:8080`
- Backend health: `http://localhost:8000/api/health`
- WhatsApp status: `http://localhost:8081/status`

Guia detalhado: [docs/INSTALL.md](./docs/INSTALL.md)

## Deploy em produção com Docker Swarm

1. Ajuste as variáveis de ambiente.
2. Gere ou publique as imagens.
3. Faça o deploy da stack:

```bash
set -a
source .env
set +a

docker stack deploy -c deploy/stack.yml meuagente
```

Guia detalhado: [docs/DEPLOY-SWARM.md](./docs/DEPLOY-SWARM.md)

## Build manual das imagens

```bash
docker build -t meuagente-backend:latest ./backend
docker build -t meuagente-frontend:latest ./frontend
docker build -t meuagente-whatsapp:latest ./whatsapp
```

## Volumes persistentes

- `meuagente_backend_data`: token salvo e arquivos de ingestão
- `meuagente_whatsapp_data`: sessão do WhatsApp
- `meuagente_vector_db_data`: banco vetorial

## Endpoints principais

Backend:

- `GET /api/health`
- `GET /api/settings`
- `POST /api/config/token`
- `POST /api/ingest`
- `POST /api/chat`
- `POST /api/whatsapp/inbound`

WhatsApp:

- `GET /health`
- `GET /status`
- `POST /connect`
- `GET /qr`

## Segurança para repositório público

- Não publique tokens OpenAI reais.
- Não publique senhas de banco reais.
- Não publique arquivos `.env`, dumps, bancos SQLite ou diretórios de dados.
- Não publique credenciais de Portainer, Traefik, GitHub ou provedores externos.

## Referências

- WhatsMeow: <https://github.com/tulir/whatsmeow>
- Documentação WhatsMeow: <https://pkg.go.dev/go.mau.fi/whatsmeow>
