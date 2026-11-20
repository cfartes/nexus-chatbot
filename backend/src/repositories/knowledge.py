from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.knowledge import KnowledgeSource


class KnowledgeRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def replace(self, tenant_id: UUID, source: str, chunks: list[tuple[str, list[float]]]) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                     {"key": f"knowledge:{tenant_id}:{source}"})
            await connection.execute(text("""
                DELETE FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id AND source = :source
            """), {"tenant_id": tenant_id, "source": source})
            if chunks:
                await connection.execute(text("""
                    INSERT INTO nexus_atende.knowledge_chunks (tenant_id, source, position, content, embedding)
                    VALUES (:tenant_id, :source, :position, :content, CAST(CAST(:embedding AS text) AS vector))
                """), [{"tenant_id": tenant_id, "source": source, "position": position, "content": content,
                         "embedding": str(embedding)} for position, (content, embedding) in enumerate(chunks)])

    async def sources(self, tenant_id: UUID) -> list[KnowledgeSource]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT source, count(*) AS chunks FROM nexus_atende.knowledge_chunks
                WHERE tenant_id = :tenant_id GROUP BY source ORDER BY source
            """), {"tenant_id": tenant_id})
            return [KnowledgeSource.model_validate(row) for row in result.mappings()]

    async def search(self, tenant_id: UUID, embedding: list[float]) -> list[str]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT content FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id
                    AND embedding <=> CAST(CAST(:embedding AS text) AS vector) <= 0.30
                ORDER BY embedding <=> CAST(CAST(:embedding AS text) AS vector) LIMIT 3
            """), {"tenant_id": tenant_id, "embedding": str(embedding)})
            return list(result.scalars())
