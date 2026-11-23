from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from src.api.routes.auth import administrator, administrator_mutation, check_origin, superadministrator, superadministrator_mutation
from src.schemas.auth import Operator
from src.schemas.operators import AcceptInvite, FunctionInput, OperatorCreate, OperatorFunction, OperatorRecord, OperatorUpdate, UserInvite
from src.services.integrations import IntegrationUnavailable
from src.services.operators import OperatorService

router = APIRouter(prefix="/operators")


def operator_service(request: Request) -> OperatorService:
    service: OperatorService = request.app.state.operator_service
    return service


Reader = Annotated[Operator, Depends(administrator)]
Writer = Annotated[Operator, Depends(administrator_mutation)]
PlatformReader = Annotated[Operator, Depends(superadministrator)]
PlatformWriter = Annotated[Operator, Depends(superadministrator_mutation)]
Service = Annotated[OperatorService, Depends(operator_service)]


@router.get("/functions")
async def functions(actor: Reader, service: Service, response: Response) -> list[OperatorFunction]:
    response.headers["Cache-Control"] = "no-store"
    return await service.functions(actor.tenant_id)


@router.post("/functions", status_code=201)
async def create_function(content: FunctionInput, actor: Writer, service: Service) -> OperatorFunction:
    return await _save_function(content, actor, service)


@router.put("/functions/{function_id}")
async def update_function(function_id: UUID, content: FunctionInput, actor: Writer, service: Service) -> OperatorFunction:
    return await _save_function(content, actor, service, function_id)


async def _save_function(content: FunctionInput, actor: Operator, service: OperatorService,
                         function_id: UUID | None = None) -> OperatorFunction:
    try:
        saved = await service.save_function(actor.tenant_id, content, function_id)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise HTTPException(409, "Já existe uma função com esse nome.") from None
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if saved is None:
        raise HTTPException(404, "Função indisponível.")
    return saved


@router.delete("/functions/{function_id}", status_code=204)
async def delete_function(function_id: UUID, actor: Writer, service: Service) -> None:
    try:
        deleted = await service.delete_function(actor.tenant_id, function_id)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23503":
            raise HTTPException(409, "Altere o perfil dos colaboradores vinculados antes de excluir a função.") from None
        raise
    if not deleted:
        raise HTTPException(404, "Função indisponível.")


@router.get("")
async def operators(actor: Reader, service: Service, response: Response) -> list[OperatorRecord]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_operators(actor.tenant_id)


@router.post("", status_code=201)
async def create(operator: OperatorCreate, actor: Writer, service: Service) -> OperatorRecord:
    return await _create(operator, actor, service)


@router.get("/superadmins")
async def superadmins(actor: PlatformReader, service: Service, response: Response) -> list[OperatorRecord]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_operators(actor.tenant_id, platform=True)


@router.post("/superadmins", status_code=201)
async def create_superadmin(content: UserInvite, actor: PlatformWriter, service: Service) -> OperatorRecord:
    return await _create(OperatorCreate(name=content.name, email=content.email), actor, service, platform=True)


async def _create(operator: OperatorCreate, actor: Operator, service: Service, *, platform: bool = False) -> OperatorRecord:
    try:
        created = await service.create(actor.tenant_id, operator, platform=platform)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure o Resend e a origem pública antes de enviar convites") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if created is None:
        raise HTTPException(409, "E-mail indisponível")
    return created


@router.post("/{user_id}/invite")
async def renew(user_id: UUID, actor: Writer, service: Service) -> OperatorRecord:
    return await _renew(user_id, actor, service)


@router.post("/superadmins/{user_id}/invite")
async def renew_superadmin(user_id: UUID, actor: PlatformWriter, service: Service) -> OperatorRecord:
    return await _renew(user_id, actor, service, platform=True)


async def _renew(user_id: UUID, actor: Operator, service: Service, *, platform: bool = False) -> OperatorRecord:
    try:
        renewed = await service.renew(actor.tenant_id, user_id, platform=platform)
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
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise HTTPException(409, "E-mail indisponível") from None
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if updated is None:
        raise HTTPException(404, "Operador indisponível")
    return updated


@router.delete("/{user_id}", status_code=204)
async def delete(user_id: UUID, actor: Writer, service: Service) -> None:
    if not await service.delete(actor.tenant_id, user_id):
        raise HTTPException(404, "Atendente indisponível")
