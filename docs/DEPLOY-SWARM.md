# Deploy em Produção com Docker Swarm e Portainer

## Objetivo

Publicar o projeto em produção usando Docker Swarm com Traefik e rede externa `waianet`.

## Pré-requisitos

- Docker Swarm inicializado
- Traefik já operando no cluster
- Rede externa `waianet` existente
- DNS do domínio apontando para o Traefik

Verifique a rede:

```bash
docker network ls | grep waianet
```

Se necessário:

```bash
docker network create --driver overlay --attachable waianet
```

## 1. Preparar variáveis de ambiente

Copie o exemplo:

```bash
cp .env.example .env
```

Preencha obrigatoriamente:

- `APP_DOMAIN`
- `CORS_ORIGINS`
- `POSTGRES_PASSWORD`
- `MEUAGENTE_WHATSAPP_VERIFY_TOKEN`

Exemplo:

```env
APP_DOMAIN=meuagente.seu-dominio.com.br
CORS_ORIGINS=https://meuagente.seu-dominio.com.br
POSTGRES_PASSWORD=uma-senha-forte
MEUAGENTE_WHATSAPP_VERIFY_TOKEN=um-token-interno-forte
TRAEFIK_CERTRESOLVER=letsencryptresolver
TRAEFIK_DOCKER_NETWORK=waianet
```

## 2. Gerar as imagens

No diretório do projeto:

```bash
docker build -t meuagente-backend:latest ./backend
docker build -t meuagente-frontend:latest ./frontend
docker build -t meuagente-whatsapp:latest ./whatsapp
```

Se usar registry:

```bash
docker tag meuagente-backend:latest registry.exemplo.com/meuagente-backend:latest
docker tag meuagente-frontend:latest registry.exemplo.com/meuagente-frontend:latest
docker tag meuagente-whatsapp:latest registry.exemplo.com/meuagente-whatsapp:latest

docker push registry.exemplo.com/meuagente-backend:latest
docker push registry.exemplo.com/meuagente-frontend:latest
docker push registry.exemplo.com/meuagente-whatsapp:latest
```

Nesse caso, ajuste no `.env`:

```env
BACKEND_IMAGE=registry.exemplo.com/meuagente-backend:latest
FRONTEND_IMAGE=registry.exemplo.com/meuagente-frontend:latest
WHATSAPP_IMAGE=registry.exemplo.com/meuagente-whatsapp:latest
```

## 3. Deploy pela CLI

Exporte as variáveis do `.env` na sessão:

```bash
set -a
source .env
set +a
```

Faça o deploy:

```bash
docker stack deploy -c deploy/stack.yml meuagente
```

## 4. Deploy via Portainer

1. Crie uma nova Stack
2. Cole o conteúdo de `deploy/stack.yml`
3. Adicione as mesmas variáveis de ambiente do `.env` na interface do Portainer
4. Faça o deploy

Não cole senhas diretamente no YAML versionado.

## 5. Validar produção

Serviços:

```bash
docker stack services meuagente
```

Tarefas:

```bash
docker service ps meuagente_frontend
docker service ps meuagente_backend
docker service ps meuagente_whatsapp
docker service ps meuagente_vector-db
```

Logs:

```bash
docker service logs -f meuagente_frontend
docker service logs -f meuagente_backend
docker service logs -f meuagente_whatsapp
```

Health:

```bash
curl https://meuagente.seu-dominio.com.br/api/health
```

## Volumes usados

- `BACKEND_VOLUME_NAME`
- `WHATSAPP_VOLUME_NAME`
- `VECTOR_VOLUME_NAME`

Os nomes padrão são:

- `meuagente_backend_data`
- `meuagente_whatsapp_data`
- `meuagente_vector_db_data`

## Estratégia de atualização

Quando houver nova versão:

1. Rebuild ou publique as novas imagens
2. Atualize as tags no `.env` se necessário
3. Rode novamente:

```bash
set -a
source .env
set +a
docker stack deploy -c deploy/stack.yml meuagente
```

## Segurança recomendada

- Use senhas fortes e exclusivas
- Restrinja o domínio em `CORS_ORIGINS`
- Nunca comite `.env` real
- Nunca comite tokens do OpenAI
- Nunca comite credenciais de Portainer ou registry
