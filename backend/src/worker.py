import asyncio
import logging
from time import monotonic
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.repositories.auth import AuthRepository
from src.repositories.bot import BotRepository
from src.repositories.database import verify_runtime_access
from src.repositories.integrations import IntegrationRepository
from src.repositories.knowledge import KnowledgeRepository
from src.repositories.outgoing_messages import OutgoingMessageRepository
from src.repositories.tenants import TenantRepository
from src.repositories.work import WorkRepository
from src.services.bot import BotService
from src.services.integrations import IntegrationService
from src.services.openwa import OpenWAUnavailable
from src.settings import Settings

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, engine: AsyncEngine, settings: Settings, tenant_id: UUID) -> None:
        self._tenant_id = tenant_id
        self._repository = IntegrationRepository(engine)
        self._integrations = IntegrationService(self._repository, settings)
        self._tenants = TenantRepository(engine)
        self._webhook_secret = settings.openwa_webhook_secret
        self._work = WorkRepository(engine)
        self._outgoing = OutgoingMessageRepository(engine)
        self._bot = BotService(BotRepository(engine), KnowledgeRepository(engine), self._integrations)

    async def sync_webhook(self) -> None:
        tenant_id = self._tenant_id
        url = self._integrations.webhook_url(tenant_id)
        if not url or not self._webhook_secret:
            return
        async with self._repository.webhook_lock(tenant_id) as acquired:
            if not acquired:
                return
            client = await self._integrations.openwa(tenant_id)
            tenant = await self._tenants.get_connection(tenant_id)
            if not client:
                return
            status = "pending"
            if tenant and tenant.openwa_session_id:
                try:
                    await client.ensure_webhook(tenant.openwa_session_id, url, self._webhook_secret)
                    status = "active"
                except OpenWAUnavailable:
                    status = "error"
            if (await self._repository.get(tenant_id)).openwa_webhook_status != status:
                await self._repository.save(tenant_id, {"openwa_webhook_status": status})

    async def run_once(self) -> bool:
        resend = await self._integrations.resend(self._tenant_id)
        openwa = await self._integrations.openwa(self._tenant_id)
        work = await self._work.claim(self._tenant_id, bool(resend and resend.notifications_enabled), openwa is not None)
        if work is None:
            return False
        if work.kind == "rag":
            await self._bot.process(self._tenant_id, work)
        elif work.kind == "notify" and resend:
            await self._work.complete(self._tenant_id, work, await resend.notify(work))
        elif work.kind == "whatsapp" and openwa:
            await self._outgoing.dispatch(self._tenant_id, work, openwa.send_text)
        return True


async def run() -> None:
    settings = Settings()
    tenant_id = settings.openwa_webhook_tenant_id
    if tenant_id is None:
        raise ValueError("Set NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID for the pilot worker")
    engine = create_async_engine(settings.runtime_database_url(), pool_pre_ping=True, hide_parameters=True)
    try:
        await verify_runtime_access(engine)
        worker = Worker(engine, settings, tenant_id)
        auth = AuthRepository(engine)
        next_cleanup = 0.0
        next_webhook = 0.0
        while True:
            try:
                if monotonic() >= next_cleanup:
                    await auth.prune(tenant_id)
                    next_cleanup = monotonic() + 3600
                if monotonic() >= next_webhook:
                    next_webhook = monotonic() + 60
                    await worker.sync_webhook()
                if await worker.run_once():
                    continue
            except SQLAlchemyError as error:
                logger.error("Worker database operation failed (%s)", type(error).__name__)
            await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
