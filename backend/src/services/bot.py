import logging
from re import search
from unicodedata import normalize
from uuid import UUID

from src.repositories.bot import BotRepository
from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import BotContext
from src.schemas.work import WorkItem
from src.services.openai import OpenAIClient

FALLBACK = "Vou encaminhar sua conversa para a equipe da Nexus. Um atendente continuará o atendimento aqui."
logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, repository: BotRepository, knowledge: KnowledgeRepository, client: OpenAIClient | None) -> None:
        self._repository = repository
        self._knowledge = knowledge
        self._client = client

    async def process(self, tenant_id: UUID, work: WorkItem) -> None:
        context = await self._repository.context(tenant_id, work)
        answer, summary = await self._answer(tenant_id, context) if context is not None else (None, None)
        await self._repository.resolve(tenant_id, work, answer, FALLBACK, summary)

    async def _answer(self, tenant_id: UUID, context: BotContext) -> tuple[str | None, str | None]:
        normalized = normalize("NFKD", context.question.casefold()).encode("ascii", "ignore").decode()
        if self._client is None or search(r"\b(atendente|operador|atendimento humano|falar com (uma pessoa|suporte))\b", normalized):
            return None, None
        summary = None
        if context.previous:
            try:
                summary = await self._client.summarize(context.previous, context.previous_summary)
            except (OSError, ValueError) as error:
                logger.warning("Conversation recap unavailable (%s)", type(error).__name__)
        try:
            knowledge = await self._knowledge.search(tenant_id, await self._client.embed(context.question[:4000]))
            if not knowledge:
                return None, summary
            result = await self._client.answer(context, knowledge, summary or context.previous_summary)
        except (OSError, ValueError):
            return None, summary
        answer = result.answer.strip()
        if result.needs_human or not 0 < len(answer) <= 4096 or "\x00" in answer:
            return None, summary
        return answer, summary
