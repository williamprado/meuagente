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
token_store = TokenStore(
    settings.settings_file,
    default_provider=settings.default_provider,
    openai_model=settings.llm_model,
    gemini_model=settings.gemini_llm_model,
)
rag_service = RagService(settings)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def mask_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def describe_provider_error(action: str, exc: Exception, *, provider: str, model: str) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if provider == "gemini" and ("404 Not Found" in message or "404 NOT_FOUND" in message):
        return (
            f"Falha no {action} com Gemini: o modelo '{model}' nao esta disponivel para esta conta. "
            f"Use '{settings.gemini_llm_model}'."
        )
    return f"Falha no {action}: {message}"


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
    config = token_store.load_config()
    active_provider = config["active_provider"]
    has_any_server_token = any(bool(config[provider]["api_key"]) for provider in ("openai", "gemini"))
    embedder_model = (
        settings.embedder_model if active_provider == "openai" else settings.gemini_embedder_model
    )
    return SettingsSummaryResponse(
        active_provider=active_provider,
        has_server_token=has_any_server_token,
        llm_model=config[active_provider]["model"],
        embedder_model=embedder_model,
        openai={
            "configured": bool(config["openai"]["api_key"]),
            "model": config["openai"]["model"],
            "masked_key": mask_key(config["openai"]["api_key"]),
        },
        gemini={
            "configured": bool(config["gemini"]["api_key"]),
            "model": config["gemini"]["model"],
            "masked_key": mask_key(config["gemini"]["api_key"]),
        },
    )


@app.post(f"{settings.api_prefix}/config/token", response_model=TokenConfigResponse)
async def save_token(request: TokenConfigRequest) -> TokenConfigResponse:
    token_store.save(
        active_provider=request.active_provider,
        openai_api_key=request.openai_api_key,
        openai_model=request.openai_model,
        gemini_api_key=request.gemini_api_key,
        gemini_model=request.gemini_model,
    )
    return TokenConfigResponse(saved=True, source="server", active_provider=request.active_provider)


@app.post(f"{settings.api_prefix}/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    try:
        resolved = token_store.resolve(
            provider=request.provider,
            openai_api_key=request.openai_api_key,
            openai_model=request.openai_model,
            gemini_api_key=request.gemini_api_key,
            gemini_model=request.gemini_model,
        )
        stored_path = rag_service.ingest_text(
            resolved.token,
            provider=resolved.provider,
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
        resolved = token_store.resolve(
            provider=request.provider,
            openai_api_key=request.openai_api_key,
            openai_model=request.openai_model,
            gemini_api_key=request.gemini_api_key,
            gemini_model=request.gemini_model,
        )
        answer = rag_service.ask(
            resolved.token,
            provider=resolved.provider,
            model_id=resolved.model,
            message=request.message,
            conversation_id=conversation_id,
            use_rag=request.use_rag,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=describe_provider_error(
                "chat",
                exc,
                provider=resolved.provider,
                model=resolved.model,
            ),
        ) from exc
    return ChatResponse(
        answer=answer,
        conversation_id=conversation_id,
        token_source=resolved.source,
    )


@app.post(f"{settings.api_prefix}/whatsapp/inbound")
async def whatsapp_inbound(request: WhatsAppInboundRequest) -> dict[str, str]:
    conversation_id = request.conversation_id or request.sender
    try:
        resolved = token_store.resolve(
            provider=None,
            openai_api_key=None,
            openai_model=None,
            gemini_api_key=None,
            gemini_model=None,
        )
        answer = rag_service.ask(
            resolved.token,
            provider=resolved.provider,
            model_id=resolved.model,
            message=request.message,
            conversation_id=conversation_id,
            use_rag=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=describe_provider_error(
                "processamento do WhatsApp",
                exc,
                provider=resolved.provider,
                model=resolved.model,
            ),
        ) from exc
    return {"reply": answer, "conversation_id": conversation_id}
