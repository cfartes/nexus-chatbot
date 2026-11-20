from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.knowledge import KnowledgeMatch, KnowledgeSource


class KnowledgeRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def welcome(self, tenant_id: UUID, message: str | None = None) -> str:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            if message is not None:
                await connection.execute(text("""
                    UPDATE nexus_atende.tenants SET welcome_message = :message WHERE id = :tenant_id
                """), {"tenant_id": tenant_id, "message": message})
                return message
            value = await connection.scalar(text("""
                SELECT welcome_message FROM nexus_atende.tenants WHERE id = :tenant_id
            """), {"tenant_id": tenant_id})
            return str(value) if value is not None else ""

    async def replace(self, tenant_id: UUID, source: str, chunks: list[tuple[str, list[float]]], embedding_space: str = "") -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                     {"key": f"knowledge:{tenant_id}:{source}"})
            await connection.execute(text("""
                DELETE FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id AND source = :source
            """), {"tenant_id": tenant_id, "source": source})
            if chunks:
                await connection.execute(text("""
                    INSERT INTO nexus_atende.knowledge_chunks (tenant_id, source, position, content, embedding, embedding_space)
                    VALUES (:tenant_id, :source, :position, :content, CAST(CAST(:embedding AS text) AS vector), :embedding_space)
                """), [{"tenant_id": tenant_id, "source": source, "position": position, "content": content,
                         "embedding": str(embedding), "embedding_space": embedding_space} for position, (content, embedding) in enumerate(chunks)])

    async def sources(self, tenant_id: UUID) -> list[KnowledgeSource]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT source, count(*) AS chunks FROM nexus_atende.knowledge_chunks
                WHERE tenant_id = :tenant_id GROUP BY source ORDER BY source
            """), {"tenant_id": tenant_id})
            return [KnowledgeSource.model_validate(row) for row in result.mappings()]

    async def search(self, tenant_id: UUID, embedding: list[float], embedding_space: str) -> list[KnowledgeMatch]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT source, content FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id
                    AND embedding_space = :embedding_space
                    AND embedding <=> CAST(CAST(:embedding AS text) AS vector) <= 0.30
                ORDER BY embedding <=> CAST(CAST(:embedding AS text) AS vector) LIMIT 3
            """), {"tenant_id": tenant_id, "embedding": str(embedding), "embedding_space": embedding_space})
            return [KnowledgeMatch.model_validate(row) for row in result.mappings()]
