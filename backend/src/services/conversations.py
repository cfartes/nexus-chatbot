from uuid import UUID

from src.repositories.bot import BotRepository
from src.repositories.conversations import ConversationRepository
from src.repositories.outgoing_messages import OutgoingMessageRepository
from src.schemas.auth import Operator
from src.schemas.conversations import ConversationSummary, HistoryMessage, Queue, SendTextRequest, TransferNotice
from src.schemas.work import WorkReceipt
from src.services.integrations import IntegrationService


class ConversationUnavailable(Exception):
    pass


class BotUnavailable(Exception):
    pass


class ConversationService:
    def __init__(self, repository: ConversationRepository, outgoing: OutgoingMessageRepository,
                 bot: BotRepository, integrations: IntegrationService) -> None:
        self._repository = repository
        self._outgoing = outgoing
        self._bot = bot
        self._integrations = integrations

    async def operators(self, actor: Operator) -> list[Operator]:
        return await self._repository.operators(actor.tenant_id)

    async def send(self, actor: Operator, conversation_id: UUID, message: SendTextRequest) -> WorkReceipt:
        if not message.text.strip():
            raise ValueError("Informe uma mensagem")
        receipt = await self._outgoing.submit(actor, conversation_id, message.request_id, message.text)
        if receipt is None:
            raise ConversationUnavailable
        return receipt

    async def set_bot(self, actor: Operator, conversation_id: UUID, active: bool) -> None:
        if active and not await self._integrations.ai_enabled(actor.tenant_id):
            raise BotUnavailable
        if not await self._bot.set_active(actor, conversation_id, active):
            raise ConversationUnavailable

    async def list_queue(self, actor: Operator, queue: Queue, limit: int, offset: int, focus: UUID | None = None) -> list[ConversationSummary]:
        if queue == "assigned" and actor.role != "admin":
            raise PermissionError
        return await self._repository.list_queue(actor, queue, limit, offset, focus)

    async def history(
        self, actor: Operator, conversation_id: UUID, limit: int, before: UUID | None,
    ) -> list[HistoryMessage]:
        history = await self._repository.history(actor, conversation_id, limit, before)
        if history is None:
            raise ConversationUnavailable
        return history

    async def claim(self, actor: Operator, conversation_id: UUID) -> None:
        if not await self._repository.claim(actor, conversation_id):
            raise ConversationUnavailable

    async def close(self, actor: Operator, conversation_id: UUID) -> None:
        if not await self._repository.close(actor, conversation_id):
            raise ConversationUnavailable

    async def transfer(self, actor: Operator, conversation_id: UUID, user_id: UUID) -> None:
        if not await self._repository.transfer(actor, conversation_id, user_id):
            raise ConversationUnavailable

    async def transfer_notices(self, actor: Operator) -> list[TransferNotice]:
        return await self._repository.transfer_notices(actor)

    async def acknowledge_transfer(self, actor: Operator, notice_id: UUID) -> None:
        await self._repository.acknowledge_transfer(actor, notice_id)
