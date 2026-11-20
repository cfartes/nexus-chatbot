from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from json import dumps
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.integrations import Provider, WebhookStatus


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
    openwa_webhook_status: WebhookStatus = "pending"


class IntegrationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def webhook_lock(self, tenant_id: UUID) -> AsyncIterator[bool]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            acquired = await connection.scalar(text("""
                SELECT pg_try_advisory_xact_lock(hashtextextended(:lock_name, 0))
            """), {"lock_name": f"openwa-registration:{tenant_id}"})
            yield bool(acquired)

    async def get(self, tenant_id: UUID) -> StoredIntegrations:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            raw = await connection.scalar(text("""
                SELECT CAST(config AS text) FROM nexus_atende.integrations WHERE tenant_id = :tenant_id
            """), {"tenant_id": tenant_id})
            return StoredIntegrations.model_validate_json(raw) if raw else StoredIntegrations()

    async def save(self, tenant_id: UUID, changes: dict[str, str | None], *, reset_openwa_verification: bool = False) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            if reset_openwa_verification:
                await connection.execute(text("""
                    UPDATE nexus_atende.tenants SET openwa_number_verified = false WHERE id = :tenant_id
                """), {"tenant_id": tenant_id})
            await connection.execute(text("""
                INSERT INTO nexus_atende.integrations AS integrations (tenant_id, config)
                VALUES (:tenant_id, CAST(:config AS jsonb))
                ON CONFLICT (tenant_id) DO UPDATE SET config = integrations.config || excluded.config
            """), {"tenant_id": tenant_id, "config": dumps(changes)})
