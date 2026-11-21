from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.knowledge import AssistantProfile, ContactOrigin, KnowledgeMatch, KnowledgeSource, WelcomeMessage


class KnowledgeRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def origins(self, tenant_id: UUID) -> list[ContactOrigin]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT slug, name FROM nexus_atende.contact_origins WHERE tenant_id = :tenant_id ORDER BY name, slug
            """), {"tenant_id": tenant_id})
            return [ContactOrigin.model_validate(row) for row in result.mappings()]

    async def save_origin(self, tenant_id: UUID, origin: ContactOrigin) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("""
                INSERT INTO nexus_atende.contact_origins (tenant_id, slug, name) VALUES (:tenant_id, :slug, :name)
                ON CONFLICT (tenant_id, slug) DO UPDATE SET name = excluded.name
            """), {"tenant_id": tenant_id, "slug": origin.slug, "name": origin.name})

    async def origin(self, tenant_id: UUID, slug: str) -> str | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            name = await connection.scalar(text("""
                SELECT name FROM nexus_atende.contact_origins WHERE tenant_id = :tenant_id AND slug = :slug
            """), {"tenant_id": tenant_id, "slug": slug})
            return str(name) if name is not None else None

    async def welcome(self, tenant_id: UUID, content: WelcomeMessage | None = None) -> AssistantProfile:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            if content is not None:
                result = await connection.execute(text("""
                    UPDATE nexus_atende.tenants
                    SET welcome_message = :message, assistant_name = coalesce(:assistant_name, assistant_name)
                    WHERE id = :tenant_id
                    RETURNING welcome_message AS message, assistant_name, name AS company_name
                """), {"tenant_id": tenant_id, "message": content.message.strip(),
                       "assistant_name": None if content.assistant_name is None else content.assistant_name.strip()})
            else:
                result = await connection.execute(text("""
                    SELECT welcome_message AS message, assistant_name, name AS company_name
                    FROM nexus_atende.tenants WHERE id = :tenant_id
                """), {"tenant_id": tenant_id})
            row = result.mappings().one_or_none()
            return AssistantProfile.model_validate(row) if row is not None else AssistantProfile(message="", company_name="")

    async def replace(self, tenant_id: UUID, source: str, chunks: list[tuple[str, list[float]]], embedding_space: str = "") -> str:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                     {"key": f"knowledge:{tenant_id}"})
            if chunks:
                existing = await connection.scalar(text("""
                    SELECT source FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id
                    GROUP BY source
                    HAVING lower(source) = lower(:source)
                        OR array_agg(content ORDER BY position) = CAST(:contents AS text[])
                    ORDER BY (source = :source) DESC, (lower(source) = lower(:source)) DESC, source
                    LIMIT 1
                """), {"tenant_id": tenant_id, "source": source, "contents": [content for content, _ in chunks]})
                if existing is not None:
                    source = str(existing)
            await connection.execute(text("""
                DELETE FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id AND source = :source
            """), {"tenant_id": tenant_id, "source": source})
            if chunks:
                await connection.execute(text("""
                    INSERT INTO nexus_atende.knowledge_chunks (tenant_id, source, position, content, embedding, embedding_space)
                    VALUES (:tenant_id, :source, :position, :content, CAST(CAST(:embedding AS text) AS vector), :embedding_space)
                """), [{"tenant_id": tenant_id, "source": source, "position": position, "content": content,
                         "embedding": str(embedding), "embedding_space": embedding_space} for position, (content, embedding) in enumerate(chunks)])
            return source

    async def sources(self, tenant_id: UUID) -> list[KnowledgeSource]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT source, count(*) AS chunks FROM nexus_atende.knowledge_chunks
                WHERE tenant_id = :tenant_id GROUP BY source ORDER BY source
            """), {"tenant_id": tenant_id})
            return [KnowledgeSource.model_validate(row) for row in result.mappings()]

    async def search(
        self, tenant_id: UUID, embedding: list[float], embedding_space: str, query: str, *, candidates: int = 3,
    ) -> list[KnowledgeMatch]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                WITH keywords AS (
                    SELECT CAST(string_agg(quote_literal(term), ' | ') AS tsquery) AS query
                    FROM unnest(tsvector_to_array(to_tsvector('portuguese', :query))) AS terms(term)
                ), scoped AS NOT MATERIALIZED (
                    SELECT source, position, content, embedding FROM nexus_atende.knowledge_chunks
                    WHERE tenant_id = :tenant_id AND embedding_space = :embedding_space
                ), semantic AS (
                    SELECT source, position, content FROM scoped
                    ORDER BY embedding <=> CAST(CAST(:embedding AS text) AS vector), source, position
                    LIMIT :candidates
                ), lexical AS (
                    SELECT source, position, content FROM scoped CROSS JOIN keywords
                    WHERE to_tsvector('portuguese', source || ' ' || content) @@ keywords.query
                    ORDER BY ts_rank(to_tsvector('portuguese', source || ' ' || content), keywords.query) DESC,
                        source, position
                    LIMIT :candidates
                )
                SELECT source, content FROM semantic
                UNION
                SELECT source, content FROM lexical
            """), {"tenant_id": tenant_id, "embedding": str(embedding), "embedding_space": embedding_space,
                   "query": query, "candidates": candidates})
            return [KnowledgeMatch.model_validate(row) for row in result.mappings()]

    async def index_ready(self, tenant_id: UUID, embedding_space: str) -> tuple[bool, bool]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT count(*) FILTER (WHERE embedding_space <> :embedding_space) > 0 AS has_outdated_sources,
                    count(*) FILTER (WHERE embedding_space = :embedding_space) > 0 AS has_current_index
                FROM nexus_atende.knowledge_chunks WHERE tenant_id = :tenant_id
            """), {"tenant_id": tenant_id, "embedding_space": embedding_space})
            has_outdated_sources, has_current_index = result.one()
            return bool(has_outdated_sources), bool(has_current_index)
