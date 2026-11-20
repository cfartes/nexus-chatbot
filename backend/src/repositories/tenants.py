from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.tenants import TenantConnection


class PhoneInUse(Exception):
    pass


class TenantRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def update_phone(self, tenant_id: UUID, phone: str) -> None:
        try:
            async with tenant_transaction(self._engine, tenant_id) as connection:
                await connection.execute(text("""
                    UPDATE nexus_atende.tenants SET phone_number = :phone,
                        openwa_number_verified = openwa_number_verified AND phone_number IS NOT DISTINCT FROM :phone
                    WHERE id = :tenant_id
                """), {"tenant_id": tenant_id, "phone": phone})
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise PhoneInUse from None
            raise

    async def get_connection(self, tenant_id: UUID) -> TenantConnection | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(
                text("""
                    SELECT id, phone_number, openwa_session_id, openwa_number_verified
                    FROM nexus_atende.tenants
                    WHERE id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            )
            row = result.mappings().one_or_none()
            return TenantConnection.model_validate(row) if row is not None else None

    @asynccontextmanager
    async def pairing_lock(self, tenant_id: UUID) -> AsyncIterator[bool]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            acquired = await connection.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:name, 0))"),
                                               {"name": f"openwa-pairing:{tenant_id}"})
            yield bool(acquired)

    async def bind_session(self, tenant_id: UUID, phone: str, session_id: UUID) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            bound = await connection.scalar(text("""
                UPDATE nexus_atende.tenants SET openwa_session_id = :session_id, openwa_number_verified = false
                WHERE id = :tenant_id AND phone_number = :phone AND openwa_session_id IS NULL RETURNING id
            """), {"tenant_id": tenant_id, "session_id": session_id, "phone": phone})
            return bound is not None

    async def verify_number(self, tenant_id: UUID, phone: str, session_id: UUID, verified: bool) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            checked = await connection.scalar(text("""
                UPDATE nexus_atende.tenants SET openwa_number_verified = :verified
                WHERE id = :tenant_id AND phone_number = :phone AND openwa_session_id = :session_id RETURNING id
            """), {"tenant_id": tenant_id, "session_id": session_id, "phone": phone, "verified": verified})
            return checked is not None
