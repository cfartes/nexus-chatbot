from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from src.api.routes.auth import authenticated_operator, mutation_operator
from src.schemas.auth import Operator
from src.schemas.conversations import BotStateRequest, ConversationSummary, HistoryMessage, Queue, SendTextRequest, TransferRequest
from src.schemas.work import WorkReceipt
from src.services.conversations import BotUnavailable, ConversationService, ConversationUnavailable
from src.services.events import ConversationEvents

router = APIRouter(prefix="/conversations")


def conversation_service(request: Request) -> ConversationService:
    service: ConversationService = request.app.state.conversation_service
    return service


Reader = Annotated[Operator, Depends(authenticated_operator)]
Writer = Annotated[Operator, Depends(mutation_operator)]
Service = Annotated[ConversationService, Depends(conversation_service)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/events")
async def conversation_events(actor: Reader, request: Request) -> StreamingResponse:
    events: ConversationEvents = request.app.state.conversation_events
    return StreamingResponse(events.stream(actor.tenant_id), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })


@router.get("/operators")
async def operators(actor: Reader, service: Service, response: Response) -> list[Operator]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.operators(actor)
    except PermissionError:
        raise HTTPException(403, "Acesso restrito a administradores") from None


@router.get("")
async def queue_entries(
    actor: Reader, service: Service, response: Response, queue: Queue = "waiting",
    limit: PageSize = 50, offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[ConversationSummary]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.list_queue(actor, queue, limit, offset)
    except PermissionError:
        raise HTTPException(403, "Acesso restrito a administradores") from None


@router.get("/{conversation_id}/messages")
async def messages(
    conversation_id: UUID, actor: Reader, service: Service, response: Response,
    limit: PageSize = 50, before: UUID | None = None,
) -> list[HistoryMessage]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.history(actor, conversation_id, limit, before)
    except ConversationUnavailable:
        raise HTTPException(404, "Conversa indisponível") from None


@router.post("/{conversation_id}/messages", status_code=202)
async def send_text(conversation_id: UUID, message: SendTextRequest, actor: Writer, service: Service) -> WorkReceipt:
    try:
        return await service.send(actor, conversation_id, message)
    except ConversationUnavailable:
        raise HTTPException(409, "Conversa ou solicitação de envio indisponível") from None
    except ValueError:
        raise HTTPException(422, "Informe uma mensagem") from None


@router.put("/{conversation_id}/bot", status_code=204)
async def set_bot(conversation_id: UUID, request: BotStateRequest, actor: Writer, service: Service) -> Response:
    try:
        await service.set_bot(actor, conversation_id, request.active)
    except BotUnavailable:
        raise HTTPException(503, "IA ainda não configurada") from None
    except ConversationUnavailable:
        raise HTTPException(404, "Conversa indisponível") from None
    return Response(status_code=204)


@router.post("/{conversation_id}/claim", status_code=204)
async def claim(conversation_id: UUID, actor: Writer, service: Service) -> Response:
    try:
        await service.claim(actor, conversation_id)
    except ConversationUnavailable:
        raise HTTPException(409, "A conversa não está mais disponível na fila") from None
    return Response(status_code=204)


@router.post("/{conversation_id}/close", status_code=204)
async def close(conversation_id: UUID, actor: Writer, service: Service) -> Response:
    try:
        await service.close(actor, conversation_id)
    except ConversationUnavailable:
        raise HTTPException(409, "Conversa indisponível para encerrar. Aguarde eventuais mensagens em envio.") from None
    return Response(status_code=204)


@router.post("/{conversation_id}/transfer", status_code=204)
async def transfer(conversation_id: UUID, transfer_request: TransferRequest, actor: Writer, service: Service) -> Response:
    try:
        await service.transfer(actor, conversation_id, transfer_request.user_id)
    except PermissionError:
        raise HTTPException(403, "Acesso restrito a administradores") from None
    except ConversationUnavailable:
        raise HTTPException(409, "Conversa ou operador indisponível") from None
    return Response(status_code=204)
