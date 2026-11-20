from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import administrator, administrator_mutation, check_origin
from src.schemas.auth import Operator
from src.schemas.operators import AcceptInvite, OperatorCreate, OperatorRecord, OperatorUpdate
from src.services.integrations import IntegrationUnavailable
from src.services.operators import OperatorService

router = APIRouter(prefix="/operators")


def operator_service(request: Request) -> OperatorService:
    service: OperatorService = request.app.state.operator_service
    return service


Reader = Annotated[Operator, Depends(administrator)]
Writer = Annotated[Operator, Depends(administrator_mutation)]
Service = Annotated[OperatorService, Depends(operator_service)]


@router.get("")
async def operators(actor: Reader, service: Service, response: Response) -> list[OperatorRecord]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list(actor.tenant_id)


@router.post("", status_code=201)
async def create(operator: OperatorCreate, actor: Writer, service: Service) -> OperatorRecord:
    try:
        created = await service.create(actor.tenant_id, operator)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure o Resend e a origem pública antes de enviar convites") from None
    except ValueError:
        raise HTTPException(422, "Informe o nome") from None
    if created is None:
        raise HTTPException(409, "E-mail indisponível")
    return created


@router.post("/{user_id}/invite")
async def renew(user_id: UUID, actor: Writer, service: Service) -> OperatorRecord:
    try:
        renewed = await service.renew(actor.tenant_id, user_id)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure o Resend e a origem pública antes de enviar convites") from None
    if renewed is None:
        raise HTTPException(404, "Convite indisponível")
    return renewed


@router.post("/accept-invite", status_code=204)
async def accept(content: AcceptInvite, request: Request, service: Service) -> Response:
    check_origin(request)
    if not await service.accept(content):
        raise HTTPException(400, "Convite inválido ou expirado")
    return Response(status_code=204)


@router.put("/{user_id}")
async def update(user_id: UUID, operator: OperatorUpdate, actor: Writer, service: Service) -> OperatorRecord:
    try:
        updated = await service.update(actor.tenant_id, user_id, operator)
    except ValueError:
        raise HTTPException(422, "Informe o nome") from None
    if updated is None:
        raise HTTPException(404, "Operador indisponível")
    return updated
