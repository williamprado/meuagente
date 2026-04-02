from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Meu Agente"
    api_prefix: str = "/api"
    data_dir: Path = Path("/data")
    uploads_dir: Path = Path("/data/uploads")
    settings_file: Path = Path("/data/settings.json")
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "*"
    postgres_user: str = "meuagente"
    postgres_password: str = "change-me"
    postgres_db: str = "meuagente"
    postgres_host: str = "vector-db"
    postgres_port: int = 5432
    vector_table: str = "knowledge_base"
    default_provider: str = "openai"
    embedder_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4.1-mini"
    gemini_embedder_model: str = "gemini-embedding-001"
    gemini_llm_model: str = "gemini-2.5-flash"
    rag_search_type: str = "hybrid"
    knowledge_max_results: int = 4
    default_chunk_size: int = 1200
    default_chunk_overlap: int = 200
    whatsapp_verify_token: str = "change-me"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MEUAGENTE_",
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings
