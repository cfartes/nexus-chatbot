from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


@asynccontextmanager
async def tenant_transaction(engine: AsyncEngine, tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('nexus.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield connection


async def verify_runtime_access(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        allowed = await connection.scalar(text("""
            SELECT pg_has_role(current_user, 'nexus_atende_app', 'USAGE')
                AND row_security_active('nexus_atende.tenants')
                AND row_security_active('nexus_atende.work_items')
                AND row_security_active('nexus_atende.knowledge_chunks')
        """))
    if not allowed:
        raise RuntimeError("Database login must inherit nexus_atende_app and be subject to RLS")
