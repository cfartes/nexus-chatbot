from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import administrator, administrator_mutation, superadministrator, superadministrator_mutation
from src.schemas.auth import Operator
from src.schemas.integrations import AISettings, HandoffEmail, IntegrationsView, OpenWASettings, ResendSettings
from src.services.integrations import IntegrationService, IntegrationUnavailable
from src.services.resend import ResendRejected

router = APIRouter(prefix="/integrations")
Reader = Annotated[Operator, Depends(superadministrator)]
PlatformWriter = Annotated[Operator, Depends(superadministrator_mutation)]


def integrations(request: Request) -> IntegrationService:
    service: IntegrationService = request.app.state.integrations
    return service


Service = Annotated[IntegrationService, Depends(integrations)]


@router.get("/handoff-email")
async def handoff_email(actor: Annotated[Operator, Depends(administrator)], service: Service, response: Response) -> HandoffEmail:
    response.headers["Cache-Control"] = "no-store"
    return HandoffEmail(email=await service.handoff_email(actor.tenant_id))


@router.put("/handoff-email")
async def save_handoff_email(
    content: HandoffEmail, actor: Annotated[Operator, Depends(administrator_mutation)], service: Service,
) -> HandoffEmail:
    await service.save_handoff_email(actor.tenant_id, content.email)
    return content


@router.get("")
async def view(actor: Reader, service: Service, response: Response) -> IntegrationsView:
    response.headers["Cache-Control"] = "no-store"
    return await service.view(actor.tenant_id)


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
async def openwa(content: OpenWASettings, actor: PlatformWriter, service: Service) -> IntegrationsView:
    try:
        return await service.save_openwa(actor.tenant_id, content)
    except IntegrationUnavailable:
        raise HTTPException(503, "Configure a chave de criptografia no servidor") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/resend/test", status_code=204)
async def test_resend(actor: PlatformWriter, service: Service) -> Response:
    client = await service.resend(actor.tenant_id, for_test=True)
    if client is None:
        raise HTTPException(422, "Salve a chave e o remetente do Resend antes de testar")
    try:
        await client.send_test()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except ResendRejected as error:
        raise HTTPException(424, str(error)) from None
    return Response(status_code=204)
