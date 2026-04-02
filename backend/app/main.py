from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.rag import RagService
from app.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SettingsSummaryResponse,
    TokenConfigRequest,
    TokenConfigResponse,
    WhatsAppInboundRequest,
)
from app.token_store import TokenStore

settings = get_settings()
token_store = TokenStore(settings.settings_file)
rag_service = RagService(settings)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            connect_timeout=3,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        vector_status = "ok"
    except Exception:
        vector_status = "unreachable"
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        vector_db=vector_status,
        timestamp=datetime.now(timezone.utc),
    )


@app.get(f"{settings.api_prefix}/settings", response_model=SettingsSummaryResponse)
async def get_summary() -> SettingsSummaryResponse:
    return SettingsSummaryResponse(
        has_server_token=token_store.load() is not None,
        llm_model=settings.llm_model,
        embedder_model=settings.embedder_model,
    )


@app.post(f"{settings.api_prefix}/config/token", response_model=TokenConfigResponse)
async def save_token(request: TokenConfigRequest) -> TokenConfigResponse:
    token_store.save(request.openai_api_key)
    return TokenConfigResponse(saved=True, source="server")


@app.post(f"{settings.api_prefix}/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    try:
        resolved = token_store.resolve(request.openai_api_key)
        stored_path = rag_service.ingest_text(
            resolved.token,
            content=request.content,
            name=request.name,
            chunk_strategy=request.chunk_strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha na ingestao: {exc}") from exc
    return IngestResponse(
        inserted=True,
        source_name=request.name,
        stored_path=str(stored_path),
    )


@app.post(f"{settings.api_prefix}/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversation_id or str(uuid4())
    try:
        resolved = token_store.resolve(request.openai_api_key)
        answer = rag_service.ask(
            resolved.token,
            message=request.message,
            conversation_id=conversation_id,
            use_rag=request.use_rag,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha no chat: {exc}") from exc
    return ChatResponse(
        answer=answer,
        conversation_id=conversation_id,
        token_source=resolved.source,
    )


@app.post(f"{settings.api_prefix}/whatsapp/inbound")
async def whatsapp_inbound(request: WhatsAppInboundRequest) -> dict[str, str]:
    conversation_id = request.conversation_id or request.sender
    try:
        resolved = token_store.resolve(None)
        answer = rag_service.ask(
            resolved.token,
            message=request.message,
            conversation_id=conversation_id,
            use_rag=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha no processamento do WhatsApp: {exc}") from exc
    return {"reply": answer, "conversation_id": conversation_id}
