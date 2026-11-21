from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.operators import FunctionInput, OperatorCreate, OperatorFunction, OperatorRecord, OperatorUpdate


class OperatorRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def functions(self, tenant_id: UUID) -> list[OperatorFunction]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT id, name, department FROM nexus_atende.operator_functions WHERE tenant_id = :tenant
                ORDER BY lower(name), id
            """), {"tenant": tenant_id})
            return [OperatorFunction.model_validate(row) for row in result.mappings()]

    async def save_function(self, tenant_id: UUID, content: FunctionInput, function_id: UUID | None) -> OperatorFunction | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant": tenant_id, "id": function_id, "name": content.name, "department": content.department}
            if function_id is None:
                result = await connection.execute(text("""
                    INSERT INTO nexus_atende.operator_functions (tenant_id, name, department)
                    VALUES (:tenant, :name, :department) RETURNING id, name, department
                """), values)
            else:
                result = await connection.execute(text("""
                    UPDATE nexus_atende.operator_functions SET name = :name, department = :department
                    WHERE tenant_id = :tenant AND id = :id RETURNING id, name, department
                """), values)
            row = result.mappings().one_or_none()
            return OperatorFunction.model_validate(row) if row is not None else None

    async def delete_function(self, tenant_id: UUID, function_id: UUID) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            return await connection.scalar(text("""
                DELETE FROM nexus_atende.operator_functions WHERE tenant_id = :tenant AND id = :id RETURNING id
            """), {"tenant": tenant_id, "id": function_id}) is not None

    async def list(self, tenant_id: UUID) -> list[OperatorRecord]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT id, name, email, department, function_id, is_active, password_hash = '' AS invite_pending FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND role = 'operator' AND deleted_at IS NULL ORDER BY name, id
            """), {"tenant_id": tenant_id})
            return [OperatorRecord.model_validate(row) for row in result.mappings()]

    async def create(self, tenant_id: UUID, operator: OperatorCreate, invite_hash: str) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant_id": tenant_id, "name": operator.name, "email": operator.email,
                      "department": operator.department, "invite_hash": invite_hash, "function_id": operator.function_id}
            if operator.function_id is not None:
                values["department"] = await connection.scalar(text("""
                    SELECT department FROM nexus_atende.operator_functions
                    WHERE tenant_id = :tenant_id AND id = :function_id FOR SHARE
                """), values)
                if values["department"] is None:
                    raise ValueError("Selecione uma função válida.")
            result = await connection.execute(text("""
                INSERT INTO nexus_atende.users (tenant_id, name, email, password_hash, role, is_active, invite_hash, invite_expires, department, function_id)
                VALUES (:tenant_id, :name, :email, '', 'operator', false, :invite_hash, now() + interval '24 hours', :department, :function_id)
                ON CONFLICT DO NOTHING RETURNING id, name, email, department, function_id, is_active, true AS invite_pending
            """), values)
            row = result.mappings().one_or_none()
            return OperatorRecord.model_validate(row) if row is not None else None

    async def renew(self, tenant_id: UUID, user_id: UUID, invite_hash: str) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                UPDATE nexus_atende.users SET invite_hash = :invite_hash, invite_expires = now() + interval '24 hours'
                WHERE tenant_id = :tenant_id AND id = :id AND role = 'operator' AND password_hash = '' AND deleted_at IS NULL
                RETURNING id, name, email, department, function_id, is_active, true AS invite_pending
            """), {"tenant_id": tenant_id, "id": user_id, "invite_hash": invite_hash})
            row = result.mappings().one_or_none()
            return OperatorRecord.model_validate(row) if row is not None else None

    async def invite_valid(self, tenant_id: UUID, invite_hash: str) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            return await connection.scalar(text("""
                SELECT id FROM nexus_atende.users WHERE tenant_id = :tenant_id AND invite_hash = :invite_hash
                    AND invite_expires > now() AND NOT platform_admin AND password_hash = '' AND deleted_at IS NULL
                    AND EXISTS (SELECT 1 FROM nexus_atende.tenants WHERE id = :tenant_id AND archived_at IS NULL)
            """), {"tenant_id": tenant_id, "invite_hash": invite_hash}) is not None

    async def accept(self, tenant_id: UUID, invite_hash: str, password_hash: str) -> bool:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            activated = await connection.scalar(text("""
                UPDATE nexus_atende.users SET is_active = true, password_hash = :password_hash,
                    invite_hash = NULL, invite_expires = NULL
                WHERE tenant_id = :tenant_id AND invite_hash = :invite_hash AND invite_expires > now()
                    AND NOT platform_admin AND password_hash = '' AND deleted_at IS NULL
                    AND EXISTS (SELECT 1 FROM nexus_atende.tenants WHERE id = :tenant_id AND archived_at IS NULL FOR SHARE)
                RETURNING id
            """), {"tenant_id": tenant_id, "invite_hash": invite_hash, "password_hash": password_hash})
            return activated is not None

    async def update(
        self, tenant_id: UUID, user_id: UUID, operator: OperatorUpdate | None,
    ) -> OperatorRecord | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            active = operator.is_active if operator is not None else False
            values = {"tenant_id": tenant_id, "id": user_id, "name": operator.name if operator else None,
                      "active": active, "email": operator.email if operator else None,
                      "department": operator.department if operator else None, "deleted": operator is None,
                      "function_id": operator.function_id if operator else None}
            if operator and operator.function_id is not None:
                values["department"] = await connection.scalar(text("""
                    SELECT department FROM nexus_atende.operator_functions
                    WHERE tenant_id = :tenant_id AND id = :function_id FOR SHARE
                """), values)
                if values["department"] is None:
                    raise ValueError("Selecione uma função válida.")
            result = await connection.execute(text("""
                UPDATE nexus_atende.users SET name = coalesce(:name, name), is_active = :active AND password_hash <> '',
                    email = coalesce(:email, email), department = coalesce(:department, department),
                    function_id = CASE WHEN :deleted OR :department IS NOT NULL THEN :function_id ELSE function_id END,
                    invite_hash = CASE WHEN :deleted OR email <> :email THEN NULL ELSE invite_hash END,
                    invite_expires = CASE WHEN :deleted OR email <> :email THEN NULL ELSE invite_expires END,
                    deleted_at = CASE WHEN :deleted THEN now() ELSE deleted_at END
                WHERE tenant_id = :tenant_id AND id = :id AND role = 'operator' AND deleted_at IS NULL
                RETURNING id, name, email, department, function_id, is_active, password_hash = '' AS invite_pending
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
                        UPDATE nexus_atende.conversations SET state = 'waiting', assigned_user_id = NULL,
                            inactivity_due_at = NULL, inactivity_notice_id = NULL
                        WHERE tenant_id = :tenant_id AND assigned_user_id = :id RETURNING id
                    )
                    INSERT INTO nexus_atende.work_items (tenant_id, conversation_id, kind)
                    SELECT :tenant_id, id, 'notify' FROM released
                """), values)
            return OperatorRecord.model_validate(row)
