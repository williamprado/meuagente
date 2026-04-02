from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderName = Literal["openai", "gemini"]


class HealthResponse(BaseModel):
    status: str
    app: str
    vector_db: str
    timestamp: datetime


class TokenConfigRequest(BaseModel):
    active_provider: ProviderName = "openai"
    openai_api_key: str | None = Field(default=None, min_length=20)
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    gemini_api_key: str | None = Field(default=None, min_length=20)
    gemini_model: str = Field(default="gemini-2.5-flash", min_length=1)


class TokenConfigResponse(BaseModel):
    saved: bool
    source: str
    active_provider: ProviderName


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1)
    name: str = Field(default="Treinamento manual")
    chunk_strategy: str = Field(default="fixed")
    chunk_size: int = Field(default=1200, ge=300, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    metadata: dict[str, Any] | None = None
    provider: ProviderName | None = None
    openai_api_key: str | None = Field(default=None, min_length=20)
    openai_model: str | None = Field(default=None, min_length=1)
    gemini_api_key: str | None = Field(default=None, min_length=20)
    gemini_model: str | None = Field(default=None, min_length=1)


class IngestResponse(BaseModel):
    inserted: bool
    source_name: str
    stored_path: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    provider: ProviderName | None = None
    openai_api_key: str | None = Field(default=None, min_length=20)
    openai_model: str | None = Field(default=None, min_length=1)
    gemini_api_key: str | None = Field(default=None, min_length=20)
    gemini_model: str | None = Field(default=None, min_length=1)
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


class ProviderSummaryResponse(BaseModel):
    configured: bool
    model: str
    masked_key: str | None = None


class SettingsSummaryResponse(BaseModel):
    active_provider: ProviderName
    has_server_token: bool
    llm_model: str
    embedder_model: str
    openai: ProviderSummaryResponse
    gemini: ProviderSummaryResponse
