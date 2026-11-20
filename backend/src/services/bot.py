import logging
from re import IGNORECASE, fullmatch, search, sub
from unicodedata import normalize
from uuid import UUID

from src.repositories.bot import BotRepository
from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import BotContext, OpeningUpdate, PreviewResult
from src.schemas.operators import Department
from src.schemas.work import WorkItem
from src.services.integrations import IntegrationService

FALLBACK = "Vou encaminhar sua conversa para a equipe da Nexus. Um atendente continuará o atendimento aqui."
TECHNICAL = "Estou com uma dificuldade técnica no momento. Vou chamar a equipe da Nexus para continuar o atendimento."
ASK_NAME = "Como posso chamar você?"
ASK_SUBJECT = "Como posso ajudar?"
DEPARTMENTS: tuple[tuple[Department, str], ...] = (
    ("comercial", "Comercial"), ("financeiro", "Financeiro"), ("suporte", "Suporte"), ("sac", "SAC"),
)
DEPARTMENT_MENU = "Qual é o assunto do atendimento? Responda com o número da opção:\n\n" + "\n".join(
    f"{number}. {label}" for number, (_, label) in enumerate(DEPARTMENTS, 1)
)
logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, repository: BotRepository, knowledge: KnowledgeRepository, integrations: IntegrationService) -> None:
        self._repository = repository
        self._knowledge = knowledge
        self._integrations = integrations

    async def process(self, tenant_id: UUID, work: WorkItem) -> None:
        context = await self._repository.context(tenant_id, work)
        if context is None:
            await self._repository.resolve(tenant_id, work, None, TECHNICAL, None)
            return

        prefix = ""
        opening = None
        question = context.question.strip()
        if context.opening_pending:
            marker = search(r"^Olá, vim pelo [^\[\]\r\n]+\. \[Nexus:([a-z0-9-]{1,50})\]", question, flags=IGNORECASE)
            if marker is not None:
                question = question[marker.end():].strip()
                context.origin_name = await self._knowledge.origin(tenant_id, marker[1].lower())
                if context.origin_name is not None:
                    context.origin_slug = marker[1].lower()
            if context.origin_slug is None:
                prefix = context.welcome_message or "Olá!"
                if context.name:
                    greeting = "Bom dia" if 5 <= context.local_hour < 12 else "Boa tarde" if 12 <= context.local_hour < 18 else "Boa noite"
                    prefix += f"\n\n{greeting}, {context.name}!"
            opening = OpeningUpdate(origin_slug=context.origin_slug)
            if _generic(question):
                question = ""
            if not context.name and not _human_requested(question):
                opening.pending_question = question
                await self._repository.resolve(tenant_id, work, _prefixed(prefix, ASK_NAME), TECHNICAL, None, opening)
                return
        elif context.opening_question is not None:
            if _human_requested(question):
                opening = OpeningUpdate(origin_slug=context.origin_slug)
                await self._repository.resolve(tenant_id, work, DEPARTMENT_MENU, TECHNICAL, None,
                                               opening, ask_department=True)
                return
            name = _customer_name(question)
            if name is None:
                if not context.opening_question and not _generic(question):
                    opening = OpeningUpdate(origin_slug=context.origin_slug, pending_question=question)
                await self._repository.resolve(tenant_id, work, ASK_NAME, TECHNICAL, None, opening)
                return
            context.name = name
            opening = OpeningUpdate(origin_slug=context.origin_slug, customer_name=name)
            prefix = f"Prazer, {name}!"
            question = context.opening_question

        if context.awaiting_department:
            choice = fullmatch(r"([1-4])[.)]?", question)
            if choice:
                department, label = DEPARTMENTS[int(choice[1]) - 1]
                await self._repository.resolve(tenant_id, work, None, f"Vou encaminhar sua conversa para {label}.", None,
                                               opening, department=department)
            else:
                await self._repository.resolve(tenant_id, work, DEPARTMENT_MENU, TECHNICAL, None, opening)
            return
        if _human_requested(question):
            await self._repository.resolve(tenant_id, work, _prefixed(prefix, DEPARTMENT_MENU), TECHNICAL, None,
                                           opening, ask_department=True)
            return
        if not question or (not context.recent and _generic(question)):
            await self._repository.resolve(tenant_id, work, _prefixed(prefix, ASK_SUBJECT), TECHNICAL, None, opening)
            return
        context.question = question
        context.welcome_message = ""
        result, summary = await self._answer(tenant_id, context)
        answer = _prefixed(prefix, result.message) if result.status == "answered" else None
        fallback = TECHNICAL if result.status == "unavailable" else result.message
        await self._repository.resolve(tenant_id, work, answer, _prefixed(prefix, fallback), summary, opening)

    async def preview(self, tenant_id: UUID, question: str) -> PreviewResult:
        welcome_message = await self._knowledge.welcome(tenant_id)
        result, _ = await self._answer(tenant_id, BotContext(
            question=question, welcome_message=welcome_message, name=None, previous_summary=None, recent=[], previous=[],
        ))
        return result

    async def _answer(self, tenant_id: UUID, context: BotContext) -> tuple[PreviewResult, str | None]:
        welcome = f"{context.welcome_message}\n\n" if not context.recent and context.welcome_message else ""
        fallback = welcome + FALLBACK
        if _human_requested(context.question):
            return PreviewResult(status="handoff", message=welcome + DEPARTMENT_MENU, sources=[]), None
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
            query = f"{context.origin_name}: {context.question}" if context.origin_name else context.question
            knowledge = await self._knowledge.search(tenant_id, await client.embed(query[:4000]), client.embedding_space)
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


def _normalized(value: str) -> str:
    return normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()


def _human_requested(value: str) -> bool:
    return bool(search(
        r"^(um |uma )?(atendente|operador|atendimento humano)[!. ]*$|\b(quero (um |uma )?(atendente|operador|atendimento humano)|falar com (um |uma |o |a )?(atendente|operador|pessoa|humano|suporte|comercial|financeiro|sac))\b",
        _normalized(value),
    ))


def _generic(value: str) -> bool:
    return bool(fullmatch(
        r"(?:\s*(?:oi+|ola+|opa|e ai|bom dia|boa tarde|boa noite|tudo (?:bem|bom)|como vai|ok|beleza|obrigad[oa])(?: nexus)?\b[\s,.!?;:]*)*",
        _normalized(value).strip(" .,!?:;"),
    ))


def _customer_name(value: str) -> str | None:
    name = sub(r"^(?:meu nome [ée]|me chamo|eu sou|sou)\s+", "", value, flags=IGNORECASE).strip(" .!")
    if not name or len(name) > 100 or _generic(name):
        return None
    if search(r"\b(quero|preciso|pode|gostaria|qual|como|onde|quando|atendente|ajuda|suporte)\b", _normalized(name)):
        return None
    return name if fullmatch(r"[^\W\d_]+(?:[ '\-’][^\W\d_]+){0,7}", name) else None


def _prefixed(prefix: str, message: str) -> str:
    return (f"{prefix}\n\n{message}" if prefix else message)[:4096]
