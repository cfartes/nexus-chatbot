from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.api.routes.auth import administrator
from src.schemas.auth import Operator
from src.schemas.whatsapp import WhatsAppConnection, WhatsAppQR
from src.services.openwa import OpenWAUnavailable
from src.services.whatsapp import WhatsAppService

router = APIRouter(prefix="/whatsapp")


def whatsapp_service(request: Request) -> WhatsAppService:
    service: WhatsAppService = request.app.state.whatsapp_service
    return service


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
