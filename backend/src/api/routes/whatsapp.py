from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import administrator, administrator_mutation
from src.repositories.tenants import PhoneInUse
from src.schemas.auth import Operator
from src.schemas.whatsapp import WhatsAppConnection, WhatsAppPhone, WhatsAppQR
from src.services.openwa import OpenWAUnavailable
from src.services.whatsapp import WhatsAppService

router = APIRouter(prefix="/whatsapp")


def whatsapp_service(request: Request) -> WhatsAppService:
    service: WhatsAppService = request.app.state.whatsapp_service
    return service


@router.put("/connection/phone")
async def update_phone(
    content: WhatsAppPhone,
    actor: Annotated[Operator, Depends(administrator_mutation)],
    service: Annotated[WhatsAppService, Depends(whatsapp_service)],
) -> WhatsAppPhone:
    try:
        return WhatsAppPhone(phone_number=await service.update_phone(actor.tenant_id, content.phone_number))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except PhoneInUse:
        raise HTTPException(409, "O número informado já está em uso") from None


@router.get("/connection")
async def connection(
    actor: Annotated[Operator, Depends(administrator)],
    service: Annotated[WhatsAppService, Depends(whatsapp_service)],
    response: Response,
) -> WhatsAppConnection:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.connection(actor.tenant_id)
    except OpenWAUnavailable:
        raise HTTPException(502, "Não foi possível consultar a sessão do WhatsApp") from None


@router.get("/connection/qr")
async def qr(
    actor: Annotated[Operator, Depends(administrator)],
    service: Annotated[WhatsAppService, Depends(whatsapp_service)],
    response: Response,
) -> WhatsAppQR:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.qr(actor.tenant_id)
    except OpenWAUnavailable:
        raise HTTPException(502, "Não foi possível consultar o QR Code do WhatsApp") from None
