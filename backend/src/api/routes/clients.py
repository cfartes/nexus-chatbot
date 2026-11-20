from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import superadministrator, superadministrator_mutation
from src.repositories.tenants import ClientConflict
from src.schemas.auth import Operator
from src.schemas.tenants import ClientCreate, ClientInvite, ClientRecord, ClientUpdate, PostalAddress, PostalCode
from src.services.clients import ClientService, PostalLookupUnavailable
from src.services.integrations import IntegrationUnavailable

router = APIRouter(prefix="/clients")
Reader = Annotated[Operator, Depends(superadministrator)]
Writer = Annotated[Operator, Depends(superadministrator_mutation)]


def clients(request: Request) -> ClientService:
    service: ClientService = request.app.state.client_service
    return service


Service = Annotated[ClientService, Depends(clients)]


@router.get("")
async def list_clients(_actor: Reader, service: Service, response: Response) -> list[ClientRecord]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list()


@router.get("/cep/{postal_code}")
async def postal_address(postal_code: PostalCode, _actor: Reader, service: Service, response: Response) -> PostalAddress:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.lookup_address(postal_code)
    except LookupError:
        raise HTTPException(404, "CEP não encontrado. Preencha o endereço manualmente.") from None
    except PostalLookupUnavailable:
        raise HTTPException(503, "A consulta de CEP está indisponível. Preencha o endereço manualmente.") from None


@router.post("", status_code=201)
async def create_client(content: ClientCreate, _actor: Writer, service: Service) -> ClientInvite:
    try:
        return await service.create(content)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure o Resend antes de cadastrar clientes.") from None
    except ClientConflict:
        raise HTTPException(409, "O e-mail do administrador já está em uso.") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/{tenant_id}/invite")
async def renew_admin(tenant_id: UUID, _actor: Writer, service: Service) -> ClientInvite:
    try:
        return await service.renew(tenant_id)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure o Resend antes de enviar convites.") from None
    except LookupError:
        raise HTTPException(404, "Nenhum convite pendente para este cliente.") from None


@router.put("/{tenant_id}", status_code=204)
async def update_client(tenant_id: UUID, content: ClientUpdate, _actor: Writer, service: Service) -> None:
    await _update(tenant_id, content, service)


@router.delete("/{tenant_id}", status_code=204)
async def archive_client(tenant_id: UUID, actor: Writer, service: Service) -> None:
    if tenant_id == actor.tenant_id:
        raise HTTPException(422, "A empresa do SuperAdmin não pode ser arquivada.")
    await _update(tenant_id, None, service)


async def _update(tenant_id: UUID, content: ClientUpdate | None, service: Service) -> None:
    try:
        await service.update(tenant_id, content)
    except LookupError:
        raise HTTPException(404, "Cliente ativo não encontrado.") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
