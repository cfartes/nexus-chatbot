import asyncio
import os
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import app
from src.repositories.tenants import TenantRepository


async def check_runtime() -> None:
    engine = create_async_engine(os.environ["NEXUS_ATENDE_TEST_DATABASE_URL"], pool_size=1)
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")

    try:
        repository = TenantRepository(engine)
        for tenant_id in (first, second):
            tenant = await repository.get_connection(tenant_id)
            assert tenant is not None and tenant.id == tenant_id
            async with engine.connect() as connection:
                visible = await connection.scalar(text("SELECT count(*) FROM nexus_atende.tenants"))
                assert visible == 0, "The pooled connection retained tenant scope"
    finally:
        await engine.dispose()

    os.environ["NEXUS_ATENDE_DATABASE_URL"] = os.environ["NEXUS_ATENDE_TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        live_repository: TenantRepository = app.state.tenant_repository
        tenant = await live_repository.get_connection(first)
        assert tenant is not None and tenant.id == first

    os.environ["NEXUS_ATENDE_DATABASE_URL"] = os.environ["NEXUS_ATENDE_TEST_ADMIN_URL"]
    try:
        async with app.router.lifespan_context(app):
            raise AssertionError("API started with an elevated database login")
    except RuntimeError as error:
        assert str(error) == "Database login must inherit nexus_atende_app and be subject to RLS"


if __name__ == "__main__":
    asyncio.run(check_runtime())
