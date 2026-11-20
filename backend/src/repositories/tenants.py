from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.tenants import TenantConnection


class TenantRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_connection(self, tenant_id: UUID) -> TenantConnection | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(
                text("""
                    SELECT id, phone_number, openwa_session_id
                    FROM nexus_atende.tenants
                    WHERE id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            )
            row = result.mappings().one_or_none()
            return TenantConnection.model_validate(row) if row is not None else None
