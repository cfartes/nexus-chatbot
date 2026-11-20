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
                SELECT id, name, email, is_active FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND role = 'operator' ORDER BY name, id
            """), {"tenant_id": tenant_id})
            return [OperatorRecord.model_validate(row) for row in result.mappings()]

    async def create(self, tenant_id: UUID, name: str, email: str, password_hash: str) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                INSERT INTO nexus_atende.users (tenant_id, name, email, password_hash, role)
                VALUES (:tenant_id, :name, :email, :password_hash, 'operator')
                ON CONFLICT DO NOTHING RETURNING id, name, email, is_active
            """), {"tenant_id": tenant_id, "name": name, "email": email, "password_hash": password_hash})
            row = result.mappings().one_or_none()
            return OperatorRecord.model_validate(row) if row is not None else None

    async def update(
        self, tenant_id: UUID, user_id: UUID, name: str, active: bool, password_hash: str | None,
    ) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant_id": tenant_id, "id": user_id, "name": name, "active": active, "password_hash": password_hash}
            result = await connection.execute(text("""
                UPDATE nexus_atende.users SET name = :name, is_active = :active,
                    password_hash = coalesce(:password_hash, password_hash)
                WHERE tenant_id = :tenant_id AND id = :id AND role = 'operator'
                RETURNING id, name, email, is_active
            """), values)
            row = result.mappings().one_or_none()
            if row is None:
                return None
            if not active or password_hash is not None:
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
