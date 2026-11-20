from re import fullmatch, sub
from uuid import UUID

from src.repositories.tenants import TenantRepository
from src.schemas.whatsapp import WhatsAppConnection, WhatsAppQR
from src.services.openwa import OpenWAUnavailable
from src.services.integrations import IntegrationService

_KNOWN_STATES = frozenset({"CREATED", "DISCONNECTED", "STOPPED", "FAILED", "READY", "CONNECTED", "QR_READY", "STARTING"})


class WhatsAppService:
    def __init__(self, tenants: TenantRepository, integrations: IntegrationService) -> None:
        self._tenants = tenants
        self._integrations = integrations

    async def update_phone(self, tenant_id: UUID, value: str) -> str:
        digits = sub(r"[ ().-]", "", value).removeprefix("+")
        if not fullmatch(r"[1-9][0-9]{7,14}", digits):
            raise ValueError("Informe um telefone com DDI e DDD, como +55 11 99999-9999")
        phone = f"+{digits}"
        await self._tenants.update_phone(tenant_id, phone)
        return phone

    async def connection(self, tenant_id: UUID) -> WhatsAppConnection:
        tenant = await self._tenants.get_connection(tenant_id)
        if tenant is None or tenant.openwa_session_id is None:
            return WhatsAppConnection(status="NOT_CONFIGURED", phone_number=tenant.phone_number if tenant else None)
        client = await self._integrations.openwa(tenant_id)
        status = await client.session_status(tenant.openwa_session_id) if client else "NOT_CONFIGURED"
        return WhatsAppConnection(
            status=status if status in _KNOWN_STATES or not client else "UNKNOWN", phone_number=tenant.phone_number,
            session_id=tenant.openwa_session_id,
        )

    async def qr(self, tenant_id: UUID) -> WhatsAppQR:
        tenant = await self._tenants.get_connection(tenant_id)
        if tenant is None or tenant.openwa_session_id is None:
            return WhatsAppQR()
        client = await self._integrations.openwa(tenant_id)
        if client is None:
            raise OpenWAUnavailable
        if await client.session_status(tenant.openwa_session_id) not in {"STARTING", "QR_READY"}:
            return WhatsAppQR()
        qr_code = await client.qr_code(tenant.openwa_session_id)
        current = await self._tenants.get_connection(tenant_id)
        if current is None or current.openwa_session_id != tenant.openwa_session_id:
            return WhatsAppQR()
        return WhatsAppQR(qr_code=qr_code)
