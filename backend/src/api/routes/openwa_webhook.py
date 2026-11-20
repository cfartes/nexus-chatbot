from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from src.services.openwa_webhook import InvalidEvent, InvalidSignature, OpenWAWebhook

router = APIRouter(prefix="/webhooks/openwa")


@router.post("/{tenant_id}", status_code=204)
async def receive(tenant_id: UUID, request: Request) -> Response:
    webhook: OpenWAWebhook | None = request.app.state.openwa_webhook
    if webhook is None:
        raise HTTPException(404, "Webhook indisponível")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 512 * 1024:
            raise HTTPException(413, "Evento muito grande")
        raw.extend(chunk)
    try:
        await webhook.receive(tenant_id, request.headers.get("X-OpenWA-Signature", ""), bytes(raw))
    except InvalidSignature:
        raise HTTPException(403, "Evento não autorizado") from None
    except InvalidEvent:
        raise HTTPException(400, "Evento inválido") from None
    return Response(status_code=204)
