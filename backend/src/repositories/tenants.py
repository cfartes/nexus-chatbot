from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.tenants import ClientChoice, ClientCreate, ClientRecord, ClientUpdate, TenantConnection


class PhoneInUse(Exception):
    pass


class ClientConflict(Exception):
    pass


class TenantRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def clients(self, *, include_details: bool = False) -> list[ClientRecord]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(text("""
                SELECT id, name, archived_at, admin_invite_pending,
                    CASE WHEN :include_details THEN details ELSE '{}'::jsonb END AS details
                FROM nexus_atende.client_registry()
            """), {"include_details": include_details})
            return [ClientRecord.model_validate(row) for row in rows.mappings()]

    async def active_choices(self) -> list[ClientChoice]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(text("SELECT id, name FROM nexus_atende.client_registry() WHERE archived_at IS NULL"))
            return [ClientChoice.model_validate(row) for row in rows.mappings()]

    async def create_client(self, tenant_id: UUID, content: ClientCreate, invite_hash: str) -> None:
        try:
            async with tenant_transaction(self._engine, tenant_id) as connection:
                await connection.execute(text("""
                    INSERT INTO nexus_atende.tenants (id, name, client_details) VALUES (:id, :name, CAST(:details AS jsonb))
                """), {"id": tenant_id, "name": content.name, "details": content.details.model_dump_json()})
                await connection.execute(text("""
                    INSERT INTO nexus_atende.users (tenant_id, name, email, password_hash, role, is_active, invite_hash, invite_expires)
                    VALUES (:id, :name, :email, '', 'admin', false, :invite_hash, now() + interval '24 hours')
                """), {"id": tenant_id, "name": content.admin.name, "email": content.admin.email, "invite_hash": invite_hash})
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise ClientConflict from None
            raise

    async def renew_admin(self, tenant_id: UUID, invite_hash: str) -> str | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            email: str | None = await connection.scalar(text("""
                UPDATE nexus_atende.users SET invite_hash = :invite_hash, invite_expires = now() + interval '24 hours'
                WHERE tenant_id = :id AND role = 'admin' AND password_hash = '' AND NOT platform_admin
                    AND EXISTS (SELECT 1 FROM nexus_atende.tenants WHERE id = :id AND archived_at IS NULL FOR SHARE)
                RETURNING email
            """), {"id": tenant_id, "invite_hash": invite_hash})
            return email

    async def update_client(self, tenant_id: UUID, content: ClientUpdate | None) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"id": tenant_id, "name": content.name if content else None,
                      "details": content.details.model_dump_json() if content and content.details else None}
            changed = await connection.scalar(text("""
                UPDATE nexus_atende.tenants SET name = coalesce(:name, name),
                    client_details = coalesce(CAST(:details AS jsonb), client_details),
                    archived_at = CASE WHEN :name IS NULL THEN now() ELSE archived_at END
                WHERE id = :id AND archived_at IS NULL RETURNING id
            """), values)
            if changed is not None and content is None:
                await connection.execute(text("DELETE FROM nexus_atende.sessions WHERE tenant_id = :id"), values)
                await connection.execute(text("""
                    UPDATE nexus_atende.work_items SET status = 'cancelled'
                    WHERE tenant_id = :id AND status IN ('pending', 'processing')
                """), values)
            return changed is not None

    async def update_phone(self, tenant_id: UUID, phone: str) -> None:
        try:
            async with tenant_transaction(self._engine, tenant_id) as connection:
                await connection.execute(text("""
                    UPDATE nexus_atende.tenants SET phone_number = :phone,
                        openwa_number_verified = openwa_number_verified AND phone_number IS NOT DISTINCT FROM :phone
                    WHERE id = :tenant_id AND archived_at IS NULL
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
                    WHERE id = :tenant_id AND archived_at IS NULL
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
                WHERE id = :tenant_id AND phone_number = :phone AND openwa_session_id IS NULL AND archived_at IS NULL RETURNING id
            """), {"tenant_id": tenant_id, "session_id": session_id, "phone": phone})
            return bound is not None

    async def verify_number(self, tenant_id: UUID, phone: str, session_id: UUID, verified: bool) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            checked = await connection.scalar(text("""
                UPDATE nexus_atende.tenants SET openwa_number_verified = :verified
                WHERE id = :tenant_id AND phone_number = :phone AND openwa_session_id = :session_id AND archived_at IS NULL RETURNING id
            """), {"tenant_id": tenant_id, "session_id": session_id, "phone": phone, "verified": verified})
            return checked is not None
