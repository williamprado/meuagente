from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app: str
    vector_db: str
    timestamp: datetime


class TokenConfigRequest(BaseModel):
    openai_api_key: str = Field(..., min_length=20)


class TokenConfigResponse(BaseModel):
    saved: bool
    source: str


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1)
    name: str = Field(default="Treinamento manual")
    chunk_strategy: str = Field(default="fixed")
    chunk_size: int = Field(default=1200, ge=300, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    metadata: dict[str, Any] | None = None
    openai_api_key: str | None = None


class IngestResponse(BaseModel):
    inserted: bool
    source_name: str
    stored_path: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    openai_api_key: str | None = None
    use_rag: bool = True
    metadata: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    token_source: str


class WhatsAppInboundRequest(BaseModel):
    sender: str
    sender_name: str | None = None
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class SettingsSummaryResponse(BaseModel):
    has_server_token: bool
    llm_model: str
    embedder_model: str

