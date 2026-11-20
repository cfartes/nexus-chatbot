from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.auth import LoginIdentity, Operator


class AuthRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def prune(self, tenant_id: UUID) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("""
                DELETE FROM nexus_atende.sessions WHERE tenant_id = :tenant_id AND expires_at <= now()
            """), {"tenant_id": tenant_id})
            await connection.execute(text("DELETE FROM nexus_atende.login_limits WHERE expires_at <= now()"))

    async def record_attempt(self, ip_key: str, identity_key: str) -> bool:
        async with self._engine.begin() as connection:
            for key, limit in ((ip_key, 30), (identity_key, 5)):
                attempts = await connection.scalar(text("""
                    INSERT INTO nexus_atende.login_limits AS limits (key_hash, attempts, expires_at)
                    VALUES (:key, 1, now() + interval '15 minutes')
                    ON CONFLICT (key_hash) DO UPDATE SET
                        attempts = CASE WHEN limits.expires_at <= now() THEN 1
                            ELSE least(limits.attempts + 1, 31) END,
                        expires_at = CASE WHEN limits.expires_at <= now() THEN excluded.expires_at
                            ELSE limits.expires_at END
                    RETURNING attempts
                """), {"key": key})
                if int(attempts) > limit:
                    return False
        return True

    async def find_identity(self, tenant_id: UUID, email: str) -> LoginIdentity | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT tenant_id, id, name, role, password_hash
                FROM nexus_atende.users WHERE tenant_id = :tenant_id AND lower(email) = :email AND is_active
            """), {"tenant_id": tenant_id, "email": email})
            row = result.mappings().one_or_none()
            return LoginIdentity.model_validate(row) if row is not None else None

    async def create_session(self, operator: Operator, token_hash: str, password_hash: str) -> bool:
        async with tenant_transaction(self._engine, operator.tenant_id) as connection:
            inserted = await connection.scalar(text("""
                INSERT INTO nexus_atende.sessions (tenant_id, user_id, token_hash)
                SELECT tenant_id, id, :token_hash FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND id = :user_id AND is_active AND password_hash = :password_hash
                FOR SHARE RETURNING token_hash
            """), {"tenant_id": operator.tenant_id, "user_id": operator.id,
                    "token_hash": token_hash, "password_hash": password_hash})
            return inserted is not None

    async def find_session(self, tenant_id: UUID, token_hash: str) -> Operator | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT users.tenant_id, users.id, users.name, users.role
                FROM nexus_atende.sessions AS sessions JOIN nexus_atende.users AS users
                    ON (users.tenant_id, users.id) = (sessions.tenant_id, sessions.user_id)
                WHERE sessions.tenant_id = :tenant_id AND sessions.token_hash = :token_hash
                    AND sessions.expires_at > now() AND users.is_active
            """), {"tenant_id": tenant_id, "token_hash": token_hash})
            row = result.mappings().one_or_none()
            return Operator.model_validate(row) if row is not None else None

    async def revoke_session(self, tenant_id: UUID, token_hash: str) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            await connection.execute(text("""
                DELETE FROM nexus_atende.sessions WHERE tenant_id = :tenant_id AND token_hash = :token_hash
            """), {"tenant_id": tenant_id, "token_hash": token_hash})

    async def password_hash(self, operator: Operator) -> str | None:
        async with tenant_transaction(self._engine, operator.tenant_id) as connection:
            stored: str | None = await connection.scalar(text("""
                SELECT password_hash FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND id = :user_id AND is_active
            """), {"tenant_id": operator.tenant_id, "user_id": operator.id})
            return stored

    async def change_password(self, operator: Operator, old_hash: str, new_hash: str, session_hash: str) -> bool:
        values = {"tenant_id": operator.tenant_id, "user_id": operator.id, "old_hash": old_hash,
                  "new_hash": new_hash, "session_hash": session_hash}
        async with tenant_transaction(self._engine, operator.tenant_id) as connection:
            changed = await connection.scalar(text("""
                UPDATE nexus_atende.users SET password_hash = :new_hash
                WHERE tenant_id = :tenant_id AND id = :user_id AND is_active AND password_hash = :old_hash
                RETURNING id
            """), values)
            if changed is None:
                return False
            await connection.execute(text("""
                DELETE FROM nexus_atende.sessions
                WHERE tenant_id = :tenant_id AND user_id = :user_id AND token_hash <> :session_hash
            """), values)
            return True
