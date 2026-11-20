from json import dumps
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.integrations import Provider


class StoredIntegrations(BaseModel):
    provider: Provider | None = None
    model: str | None = None
    embedding_model: str | None = None
    ai_key: str | None = None
    embedding_key: str | None = None
    resend_key: str | None = None
    sender: str | None = None
    recipient: str | None = None
    openwa_key: str | None = None
    openwa_url: str | None = None


class IntegrationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, tenant_id: UUID) -> StoredIntegrations:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            raw = await connection.scalar(text("""
                SELECT CAST(config AS text) FROM nexus_atende.integrations WHERE tenant_id = :tenant_id
            """), {"tenant_id": tenant_id})
            return StoredIntegrations.model_validate_json(raw) if raw else StoredIntegrations()

    async def save(self, tenant_id: UUID, changes: dict[str, str | None]) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("""
                INSERT INTO nexus_atende.integrations AS integrations (tenant_id, config)
                VALUES (:tenant_id, CAST(:config AS jsonb))
                ON CONFLICT (tenant_id) DO UPDATE SET config = integrations.config || excluded.config
            """), {"tenant_id": tenant_id, "config": dumps(changes)})
