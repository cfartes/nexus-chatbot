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
from src.services.integrations import IntegrationService, tenant_webhook_secret
from src.services.openwa import OpenWARateLimited, OpenWAUnavailable
from src.settings import Settings

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, engine: AsyncEngine, settings: Settings, tenant_id: UUID) -> None:
        self._tenant_id = tenant_id
        self._repository = IntegrationRepository(engine)
        self._integrations = IntegrationService(self._repository, settings)
        self._tenants = TenantRepository(engine)
        credentials = settings.webhook_credentials()
        self._webhook_secret = tenant_webhook_secret(credentials[0], tenant_id, credentials[1]) if credentials else None
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
            detail = None
            if tenant and tenant.openwa_session_id and tenant.phone_number:
                try:
                    session_status, phone = await client.session_identity(tenant.openwa_session_id)
                    verified = session_status in {"READY", "CONNECTED"} and phone == tenant.phone_number
                    binding_matches = await self._tenants.verify_number(tenant_id, tenant.phone_number, tenant.openwa_session_id, verified)
                    if verified and binding_matches:
                        await client.ensure_webhook(tenant.openwa_session_id, url, self._webhook_secret)
                        status = "active"
                    elif session_status in {"READY", "CONNECTED"} and phone:
                        status = "error"
                        detail = "O telefone conectado no OpenWA difere do telefone salvo."
                    elif session_status in {"READY", "CONNECTED"}:
                        detail = "Sessão conectada. O OpenWA ainda não informou o telefone para verificação."
                except OpenWARateLimited as error:
                    status = "rate_limited"
                    detail = str(error)
                except OpenWAUnavailable as error:
                    status = "error"
                    detail = str(error) or "Falha na consulta ao OpenWA."
            saved = await self._repository.get(tenant_id)
            if (saved.openwa_webhook_status, saved.openwa_webhook_error) != (status, detail):
                await self._repository.save(tenant_id, {"openwa_webhook_status": status, "openwa_webhook_error": detail})

    async def run_once(self) -> bool:
        resend = await self._integrations.resend(self._tenant_id)
        openwa = await self._integrations.openwa(self._tenant_id)
        work = await self._work.claim(self._tenant_id, bool(resend and resend.notifications_enabled), bool(openwa and not openwa.retry_after()))
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
        tenants = TenantRepository(engine)
        workers: dict[UUID, Worker] = {}
        auth = AuthRepository(engine)
        next_refresh = 0.0
        next_cleanup = 0.0
        next_sync: dict[UUID, float] = {}
        while True:
            try:
                if monotonic() >= next_refresh:
                    active = [client.id for client in await tenants.clients() if client.archived_at is None]
                    workers = {client_id: workers[client_id] if client_id in workers else Worker(engine, settings, client_id)
                               for client_id in active}
                    next_sync = {client_id: next_sync.get(client_id, 0.0) for client_id in active}
                    next_refresh = monotonic() + 120
                if monotonic() >= next_cleanup:
                    for client_id in workers:
                        await auth.prune(client_id)
                    next_cleanup = monotonic() + 3600
                processed = []
                for client_id, worker in workers.items():
                    # Give queued work the first provider call when a cooldown ends.
                    did_work = await worker.run_once()
                    processed.append(did_work)
                    if not did_work and monotonic() >= next_sync[client_id]:
                        await worker.sync_webhook()
                        next_sync[client_id] = monotonic() + 120
                if any(processed):
                    continue
            except SQLAlchemyError as error:
                logger.error("Worker database operation failed (%s)", type(error).__name__)
            await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
