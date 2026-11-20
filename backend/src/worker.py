import asyncio
import logging
from time import monotonic
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.repositories.auth import AuthRepository
from src.repositories.bot import BotRepository
from src.repositories.database import verify_runtime_access
from src.repositories.knowledge import KnowledgeRepository
from src.repositories.outgoing_messages import OutgoingMessageRepository
from src.repositories.work import WorkRepository
from src.services.bot import BotService
from src.services.openai import OpenAIClient
from src.services.openwa import OpenWAClient
from src.services.resend import ResendClient
from src.settings import Settings

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, engine: AsyncEngine, settings: Settings, tenant_id: UUID) -> None:
        self._tenant_id = tenant_id
        openwa = settings.openwa_credentials()
        resend = settings.resend_credentials()
        openai = settings.openai_api_key
        self._openwa = OpenWAClient(*openwa) if openwa else None
        self._resend = ResendClient(*resend) if resend else None
        self._work = WorkRepository(engine)
        self._outgoing = OutgoingMessageRepository(engine)
        self._bot = BotService(BotRepository(engine), KnowledgeRepository(engine),
                               OpenAIClient(openai, settings.openai_model) if openai and openai.get_secret_value() else None)

    async def run_once(self) -> bool:
        work = await self._work.claim(self._tenant_id, self._resend is not None, self._openwa is not None)
        if work is None:
            return False
        if work.kind == "rag":
            await self._bot.process(self._tenant_id, work)
        elif work.kind == "notify" and self._resend:
            await self._work.complete(self._tenant_id, work, await self._resend.notify(work))
        elif work.kind == "whatsapp" and self._openwa:
            await self._outgoing.dispatch(self._tenant_id, work, self._openwa.send_text)
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
        while True:
            try:
                if monotonic() >= next_cleanup:
                    await auth.prune(tenant_id)
                    next_cleanup = monotonic() + 3600
                if await worker.run_once():
                    continue
            except SQLAlchemyError as error:
                logger.error("Worker database operation failed (%s)", type(error).__name__)
            await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
