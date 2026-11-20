import logging
from re import search
from unicodedata import normalize
from uuid import UUID

from src.repositories.bot import BotRepository
from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import BotContext, PreviewResult
from src.schemas.work import WorkItem
from src.services.integrations import IntegrationService

FALLBACK = "Vou encaminhar sua conversa para a equipe da Nexus. Um atendente continuará o atendimento aqui."
TECHNICAL = "Estou com uma dificuldade técnica no momento. Vou chamar a equipe da Nexus para continuar o atendimento."
logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, repository: BotRepository, knowledge: KnowledgeRepository, integrations: IntegrationService) -> None:
        self._repository = repository
        self._knowledge = knowledge
        self._integrations = integrations

    async def process(self, tenant_id: UUID, work: WorkItem) -> None:
        context = await self._repository.context(tenant_id, work)
        result, summary = await self._answer(tenant_id, context) if context is not None else (None, None)
        answer = result.message if result is not None and result.status == "answered" else None
        fallback = TECHNICAL if result is None or result.status == "unavailable" else result.message
        await self._repository.resolve(tenant_id, work, answer, fallback, summary)

    async def preview(self, tenant_id: UUID, question: str) -> PreviewResult:
        welcome_message = await self._knowledge.welcome(tenant_id)
        result, _ = await self._answer(tenant_id, BotContext(
            question=question, welcome_message=welcome_message, name=None, previous_summary=None, recent=[], previous=[],
        ))
        return result

    async def _answer(self, tenant_id: UUID, context: BotContext) -> tuple[PreviewResult, str | None]:
        welcome = f"{context.welcome_message}\n\n" if not context.recent and context.welcome_message else ""
        fallback = welcome + FALLBACK
        normalized = normalize("NFKD", context.question.casefold()).encode("ascii", "ignore").decode()
        if search(r"^(um |uma )?(atendente|operador)[!. ]*$|\b(quero (um |uma )?(atendente|operador|atendimento humano)|falar com (um atendente|uma pessoa|o suporte|suporte))\b", normalized):
            return PreviewResult(status="handoff", message=fallback, sources=[]), None
        client = await self._integrations.ai(tenant_id)
        if client is None:
            return PreviewResult(status="unavailable", message="A IA está indisponível. Confira o provedor e as credenciais.", sources=[]), None
        outdated, indexed = await self._knowledge.index_ready(tenant_id, client.embedding_space)
        reindex = "Reimporte as fontes para indexá-las com o provedor de embeddings atual."
        if not indexed:
            message = reindex if outdated else "Adicione fontes à base de conhecimento antes de testar a IA."
            return PreviewResult(status="unavailable", message=message, sources=[]), None
        summary = None
        if context.previous:
            try:
                summary = await client.summarize(context.previous, context.previous_summary)
            except (OSError, ValueError) as error:
                logger.warning("Conversation recap unavailable (%s)", type(error).__name__)
        sources: list[str] = []
        try:
            knowledge = await self._knowledge.search(tenant_id, await client.embed(context.question[:4000]), client.embedding_space)
            if not knowledge:
                return PreviewResult(status="unavailable", message="A base mudou durante a consulta. Tente novamente.", sources=[]), summary
            sources = list(dict.fromkeys(match.source for match in knowledge))
            result = await client.answer(context, [match.content for match in knowledge], summary or context.previous_summary)
        except (OSError, ValueError):
            return PreviewResult(status="unavailable", message="Não foi possível concluir a consulta. Confira a chave, o modelo e os limites do provedor.", sources=sources), summary
        answer = result.answer.strip()
        if result.needs_human:
            if outdated:
                return PreviewResult(status="unavailable", message=reindex, sources=sources), summary
            return PreviewResult(status="handoff", message=fallback, sources=sources), summary
        if not 0 < len(answer) <= 4096 or "\x00" in answer:
            return PreviewResult(status="unavailable", message="O modelo não retornou uma resposta utilizável. Confira o modelo configurado.", sources=sources), summary
        return PreviewResult(status="answered", message=(welcome + answer)[:4096], sources=sources), summary
