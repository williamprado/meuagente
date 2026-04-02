import hashlib
from pathlib import Path

from agno.agent import Agent
from agno.document.chunking.fixed import FixedSizeChunking
from agno.document.reader.text_reader import TextReader
from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge.text import TextKnowledgeBase
from agno.models.openai import OpenAIResponses
from agno.vectordb.pgvector import PgVector, SearchType

from app.config import Settings


class RagService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _vector_db(self, api_key: str) -> PgVector:
        return PgVector(
            table_name=self.settings.vector_table,
            db_url=self.settings.postgres_dsn,
            search_type=getattr(SearchType, self.settings.rag_search_type, SearchType.hybrid),
            embedder=OpenAIEmbedder(
                id=self.settings.embedder_model,
                api_key=api_key,
            ),
        )

    def _knowledge(self, api_key: str, path: str | None = None, reader: TextReader | None = None) -> TextKnowledgeBase:
        return TextKnowledgeBase(
            vector_db=self._vector_db(api_key=api_key),
            reader=reader or TextReader(chunk_size=self.settings.default_chunk_size),
            num_documents=self.settings.knowledge_max_results,
            path=path,
        )

    def _agent(self, api_key: str, use_rag: bool) -> Agent:
        return Agent(
            model=OpenAIResponses(
                id=self.settings.llm_model,
                api_key=api_key,
            ),
            knowledge=self._knowledge(api_key=api_key),
            search_knowledge=use_rag,
            add_knowledge_to_context=use_rag,
            markdown=True,
            instructions=[
                "Responda em portugues do Brasil.",
                "Use o conhecimento recuperado como prioridade quando ele existir.",
                "Se a base nao tiver informacao suficiente, deixe isso claro.",
            ],
        )

    def _reader(self, strategy: str, chunk_size: int, chunk_overlap: int) -> TextReader:
        if strategy == "semantic":
            from agno.document.chunking.semantic import SemanticChunking

            chunking_strategy = SemanticChunking()
        else:
            chunking_strategy = FixedSizeChunking(
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
        return TextReader(chunking_strategy=chunking_strategy)

    def ingest_text(
        self,
        api_key: str,
        *,
        content: str,
        name: str,
        chunk_strategy: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Path:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        safe_name = "".join(ch for ch in name.lower().replace(" ", "-") if ch.isalnum() or ch in "-_")
        stored_path = self.settings.uploads_dir / f"{safe_name or 'conteudo'}-{digest}.txt"
        stored_path.write_text(content, encoding="utf-8")
        reader = self._reader(
            strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        knowledge = self._knowledge(
            api_key=api_key,
            path=str(stored_path),
            reader=reader,
        )
        knowledge.load(upsert=True, skip_existing=False)
        return stored_path

    def ask(
        self,
        api_key: str,
        *,
        message: str,
        conversation_id: str,
        use_rag: bool,
    ) -> str:
        agent = self._agent(api_key=api_key, use_rag=use_rag)
        response = agent.run(
            message,
            session_id=conversation_id,
        )
        content = getattr(response, "content", response)
        return str(content)
