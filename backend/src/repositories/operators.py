from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.operators import OperatorRecord


class OperatorRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list(self, tenant_id: UUID) -> list[OperatorRecord]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT id, name, email, is_active, password_hash = '' AS invite_pending FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND role = 'operator' ORDER BY name, id
            """), {"tenant_id": tenant_id})
            return [OperatorRecord.model_validate(row) for row in result.mappings()]

    async def create(self, tenant_id: UUID, name: str, email: str, invite_hash: str) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                INSERT INTO nexus_atende.users (tenant_id, name, email, password_hash, role, is_active, invite_hash, invite_expires)
                VALUES (:tenant_id, :name, :email, '', 'operator', false, :invite_hash, now() + interval '24 hours')
                ON CONFLICT DO NOTHING RETURNING id, name, email, is_active, true AS invite_pending
            """), {"tenant_id": tenant_id, "name": name, "email": email, "invite_hash": invite_hash})
            row = result.mappings().one_or_none()
            return OperatorRecord.model_validate(row) if row is not None else None

    async def renew(self, tenant_id: UUID, user_id: UUID, invite_hash: str) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                UPDATE nexus_atende.users SET invite_hash = :invite_hash, invite_expires = now() + interval '24 hours'
                WHERE tenant_id = :tenant_id AND id = :id AND role = 'operator' AND password_hash = ''
                RETURNING id, name, email, is_active, true AS invite_pending
            """), {"tenant_id": tenant_id, "id": user_id, "invite_hash": invite_hash})
            row = result.mappings().one_or_none()
            return OperatorRecord.model_validate(row) if row is not None else None

    async def invite_valid(self, tenant_id: UUID, invite_hash: str) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            return await connection.scalar(text("""
                SELECT id FROM nexus_atende.users WHERE tenant_id = :tenant_id AND invite_hash = :invite_hash
                    AND invite_expires > now() AND role = 'operator' AND password_hash = ''
            """), {"tenant_id": tenant_id, "invite_hash": invite_hash}) is not None

    async def accept(self, tenant_id: UUID, invite_hash: str, password_hash: str) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            activated = await connection.scalar(text("""
                UPDATE nexus_atende.users SET is_active = true, password_hash = :password_hash,
                    invite_hash = NULL, invite_expires = NULL
                WHERE tenant_id = :tenant_id AND invite_hash = :invite_hash AND invite_expires > now()
                    AND role = 'operator' AND password_hash = '' RETURNING id
            """), {"tenant_id": tenant_id, "invite_hash": invite_hash, "password_hash": password_hash})
            return activated is not None

    async def update(
        self, tenant_id: UUID, user_id: UUID, name: str, active: bool,
    ) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant_id": tenant_id, "id": user_id, "name": name, "active": active}
            result = await connection.execute(text("""
                UPDATE nexus_atende.users SET name = :name, is_active = :active AND password_hash <> ''
                WHERE tenant_id = :tenant_id AND id = :id AND role = 'operator'
                RETURNING id, name, email, is_active, password_hash = '' AS invite_pending
            """), values)
            row = result.mappings().one_or_none()
            if row is None:
                return None
            if not active:
                await connection.execute(text("""
                    DELETE FROM nexus_atende.sessions WHERE tenant_id = :tenant_id AND user_id = :id
                """), values)
            if not active:
                await connection.execute(text("""
                    WITH released AS (
                        UPDATE nexus_atende.conversations SET state = 'waiting', assigned_user_id = NULL
                        WHERE tenant_id = :tenant_id AND assigned_user_id = :id RETURNING id
                    )
                    INSERT INTO nexus_atende.work_items (tenant_id, conversation_id, kind)
                    SELECT :tenant_id, id, 'notify' FROM released
                """), values)
            return OperatorRecord.model_validate(row)
