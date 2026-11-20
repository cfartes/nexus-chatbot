from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import administrator, administrator_mutation, superadministrator_mutation
from src.schemas.auth import Operator
from src.schemas.integrations import AISettings, IntegrationsView, OpenWASettings, ResendSettings
from src.services.integrations import IntegrationService, IntegrationUnavailable
from src.services.resend import ResendRejected

router = APIRouter(prefix="/integrations")
Reader = Annotated[Operator, Depends(administrator)]
Writer = Annotated[Operator, Depends(administrator_mutation)]
PlatformWriter = Annotated[Operator, Depends(superadministrator_mutation)]


def integrations(request: Request) -> IntegrationService:
    service: IntegrationService = request.app.state.integrations
    return service


Service = Annotated[IntegrationService, Depends(integrations)]


@router.get("")
async def view(actor: Reader, service: Service, response: Response) -> IntegrationsView:
    response.headers["Cache-Control"] = "no-store"
    return _visible(await service.view(actor.tenant_id), actor)


@router.put("/ai")
async def ai(content: AISettings, actor: PlatformWriter, service: Service) -> IntegrationsView:
    try:
        return await service.save_ai(actor.tenant_id, content)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure a chave de criptografia no servidor") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.put("/resend")
async def resend(content: ResendSettings, actor: PlatformWriter, service: Service) -> IntegrationsView:
    try:
        return await service.save_resend(actor.tenant_id, content)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure a chave de criptografia no servidor") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.put("/openwa")
async def openwa(content: OpenWASettings, actor: Writer, service: Service) -> IntegrationsView:
    try:
        return _visible(await service.save_openwa(actor.tenant_id, content), actor)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure a chave de criptografia no servidor") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/resend/test", status_code=204)
async def test_resend(actor: PlatformWriter, service: Service) -> Response:
    client = await service.resend(actor.tenant_id)
    if client is None:
        raise HTTPException(422, "Salve a chave e o remetente do Resend antes de testar")
    try:
        await client.send_test()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except ResendRejected as error:
        raise HTTPException(424, str(error)) from None
    return Response(status_code=204)


def _visible(config: IntegrationsView, actor: Operator) -> IntegrationsView:
    if actor.platform_admin:
        return config
    return config.model_copy(update={
        "provider": "openai", "model": "", "embedding_model": "", "ai_has_key": False,
        "embedding_has_key": False, "ollama_url": None, "resend_sender": "", "resend_recipient": "",
        "resend_has_key": False,
    })
