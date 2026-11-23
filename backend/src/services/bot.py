import logging
from re import IGNORECASE, fullmatch, search, sub
from unicodedata import normalize
from uuid import UUID

from pydantic import HttpUrl

from src.repositories.bot import BotRepository
from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import BotContext, OpeningUpdate, PreviewResult
from src.schemas.operators import Department
from src.schemas.work import WorkItem
from src.services.integrations import IntegrationService
from src.services.openai import OpenAIClient
from src.services.technical_web import technical_excerpts

TECHNICAL = "Estou com uma dificuldade técnica no momento. Vou chamar nossa equipe para continuar o atendimento."
ASK_NAME = "Como posso chamar você?"
ASK_SUBJECT = "Como posso ajudar?"
DEPARTMENTS: tuple[tuple[Department, str], ...] = (
    ("comercial", "Comercial"), ("financeiro", "Financeiro"), ("suporte", "Suporte"), ("sac", "SAC"),
)
DEPARTMENT_MENU = "Qual é o assunto do atendimento? Responda com o número da opção:\n\n" + "\n".join(
    f"{number}. {label}" for number, (_, label) in enumerate(DEPARTMENTS, 1)
)
TOPICS: tuple[tuple[Department, str], ...] = (
    ("financeiro", r"financeiro|boleto|cobranca|fatura|nota fiscal|pagamento|reembolso|segunda via"),
    ("comercial", r"comercial|preco|valor|quanto (?:custa|fica)|orcamento|proposta|contrata\w*|planos?|desconto|demonstracao"),
    ("sac", r"sac|reclam\w*|insatisfa\w*|ouvidoria|sugestao"),
    ("suporte", r"suporte|tecnic\w*|erro|falha|trav\w*|cache|cookies?|navegador|login|configur\w*|instal\w*"),
)
HANDOFF_MESSAGES: dict[Department, str] = {
    "comercial": "Vou encaminhar sua conversa ao Comercial para que a equipe possa confirmar os detalhes com você por aqui.",
    "financeiro": "Vou encaminhar sua conversa ao Financeiro para que a equipe possa verificar isso com você por aqui.",
    "suporte": "Vou chamar a equipe de Suporte para analisar o que está acontecendo e continuar o atendimento por aqui.",
    "sac": "Vou encaminhar sua conversa ao SAC para que a equipe possa dar continuidade ao seu atendimento por aqui.",
}
logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, repository: BotRepository, knowledge: KnowledgeRepository, integrations: IntegrationService,
                 web_sources: dict[UUID, list[HttpUrl]] | None = None) -> None:
        self._repository = repository
        self._knowledge = knowledge
        self._integrations = integrations
        self._web_sources = web_sources or {}

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
                prefix = _welcome(context) or "Olá!"
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
            elif (name := _customer_name(question)) is None:
                if not context.opening_question and not _generic(question):
                    opening = OpeningUpdate(origin_slug=context.origin_slug, pending_question=question)
                await self._repository.resolve(tenant_id, work, ASK_NAME, TECHNICAL, None, opening)
                return
            else:
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
        if not question or (not context.recent and _generic(question)):
            await self._repository.resolve(tenant_id, work, _prefixed(prefix, ASK_SUBJECT), TECHNICAL, None, opening)
            return
        context.question = question
        context.welcome_message = ""
        result, summary = await self._answer(tenant_id, context)
        answer = _prefixed(prefix, result.message) if result.status in {"answered", "clarify"} else None
        fallback = result.message
        if result.status == "unavailable":
            fallback = HANDOFF_MESSAGES[result.department] if result.department else TECHNICAL
        ask_department = result.status == "handoff" and result.department is None
        if ask_department:
            answer = _prefixed(prefix, result.message)
        await self._repository.resolve(tenant_id, work, answer, _prefixed(prefix, fallback), summary, opening,
                                       ask_department=ask_department, department=result.department)

    async def preview(self, tenant_id: UUID, question: str) -> PreviewResult:
        profile = await self._knowledge.welcome(tenant_id)
        context = BotContext(
            question=question, welcome_message=profile.message, name=None, previous_summary=None, recent=[], previous=[],
            company_name=profile.company_name, assistant_name=profile.assistant_name or "",
        )
        context.welcome_message = _welcome(context)
        result, _ = await self._answer(tenant_id, context)
        return result

    async def _answer(self, tenant_id: UUID, context: BotContext) -> tuple[PreviewResult, str | None]:
        welcome = f"{context.welcome_message}\n\n" if not context.recent and context.welcome_message else ""
        department = _department(context)
        handoff_message = welcome + (HANDOFF_MESSAGES[department] if department else DEPARTMENT_MENU)
        if _human_requested(context.question):
            return PreviewResult(status="handoff", message=handoff_message, sources=[], department=department,
                                 reason="O cliente pediu atendimento humano."), None
        client = await self._integrations.ai(tenant_id)
        if client is None:
            return PreviewResult(status="unavailable", message="A IA está indisponível. Confira o provedor e as credenciais.",
                                 sources=[], department=department), None
        outdated, indexed = await self._knowledge.index_ready(tenant_id, client.embedding_space)
        reindex = "Reimporte as fontes para indexá-las com o provedor de embeddings atual."
        if not indexed:
            if not outdated and department == "suporte":
                web_result = await self._web_answer(tenant_id, client, context, welcome)
                if web_result:
                    return web_result, None
            message = reindex if outdated else "Adicione fontes à base de conhecimento antes de testar a IA."
            return PreviewResult(status="unavailable", message=message, sources=[], department=department), None
        summary = None
        if context.previous:
            try:
                summary = await client.summarize(context.previous, context.previous_summary)
            except (OSError, ValueError) as error:
                logger.warning("Conversation recap unavailable (%s)", type(error).__name__)
        sources: list[str] = []
        try:
            query = (f"{context.origin_name}: {context.question}" if context.origin_name else context.question)[:4000]
            prior = [line.removeprefix("customer: ") for line in context.recent if line.startswith("customer: ")]
            context_terms = "\n".join(line[:250] for line in [line for line in prior if not _generic(line)][-2:])
            contextual = f"{query}\n{context_terms}"[:4000] if context_terms else query
            first = contextual if len(context.question.split()) <= 12 else query
            vector = await client.embed(first)
            knowledge = await self._knowledge.search(tenant_id, vector, client.embedding_space, first)
            if not knowledge:
                return PreviewResult(status="unavailable", message="A base mudou durante a consulta. Tente novamente.", sources=[]), summary
            sources = list(dict.fromkeys(match.source for match in knowledge))
            recap = summary or context.previous_summary
            result = await client.answer(context, [match.content for match in knowledge], recap)
            if result.needs_human:
                second = query if first != query else contextual
                expanded = await self._knowledge.search(tenant_id, vector if second == first else await client.embed(second),
                                                        client.embedding_space, second, candidates=6)
                extra = [match for match in expanded if match not in knowledge]
                if extra:
                    knowledge = (knowledge + extra)[:12]
                    sources = list(dict.fromkeys(match.source for match in knowledge))
                    result = await client.answer(context, [match.content for match in knowledge], recap)
        except (OSError, ValueError):
            return PreviewResult(status="unavailable", message="Não foi possível concluir a consulta. Confira a chave, o modelo e os limites do provedor.",
                                 sources=sources, department=department), summary
        answer = result.answer.strip()
        excerpts = knowledge
        if result.needs_human:
            if department == "suporte":
                web_result = await self._web_answer(tenant_id, client, context, welcome)
                if web_result:
                    return web_result, summary
            if outdated:
                return PreviewResult(status="unavailable", message=reindex, sources=sources, excerpts=excerpts,
                                     department=department), summary
            return PreviewResult(status="handoff", message=handoff_message, sources=sources, excerpts=excerpts, department=department,
                                 reason="Os trechos consultados não sustentaram uma resposta."), summary
        if not 0 < len(answer) <= 4096 or "\x00" in answer:
            return PreviewResult(status="unavailable", message="O modelo não retornou uma resposta utilizável. Confira o modelo configurado.", sources=sources), summary
        if result.needs_clarification:
            return PreviewResult(status="clarify", message=(welcome + answer)[:4096], sources=sources, excerpts=excerpts,
                                 reason="Falta um detalhe que o cliente pode esclarecer."), summary
        return PreviewResult(status="answered", message=(welcome + answer)[:4096], sources=sources, excerpts=excerpts), summary

    async def _web_answer(self, tenant_id: UUID, client: OpenAIClient, context: BotContext, welcome: str) -> PreviewResult | None:
        excerpts = await technical_excerpts(_normalized(context.question), self._web_sources.get(tenant_id, []))
        if not excerpts:
            return None
        try:
            result = await client.answer(context, [match.content for match in excerpts], None, web=True)
        except (OSError, ValueError):
            return None
        answer = result.answer.strip()
        if result.needs_human or result.needs_clarification or not answer or "\x00" in answer or search(r"https?://|www\.", answer, IGNORECASE):
            return None
        sources = [match.source for match in excerpts]
        citations = "\n\nFontes consultadas:\n" + "\n".join(sources)
        return PreviewResult(status="answered", message=(welcome + answer)[:max(0, 4096 - len(citations))] + citations,
                             sources=sources, excerpts=excerpts, reason="Consulta a documentação pública autorizada.")


def _normalized(value: str) -> str:
    return normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()


def _department(context: BotContext) -> Department | None:
    latest = [context.question, *(line.removeprefix("customer: ") for line in reversed(context.recent)
                                   if line.startswith("customer: "))]
    for line in latest:
        matches = [department for department, words in TOPICS if search(rf"\b(?:{words})\b", _normalized(line))]
        business = [department for department in matches if department != "suporte"]
        if matches:
            return business[0] if len(business) == 1 else matches[0] if len(matches) == 1 else None
    return None


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


def _welcome(context: BotContext) -> str:
    if not context.assistant_name:
        return context.welcome_message
    introduction = f"Sou {context.assistant_name}, assistente virtual da empresa {context.company_name}."
    return _prefixed(context.welcome_message or "Olá!", introduction)
