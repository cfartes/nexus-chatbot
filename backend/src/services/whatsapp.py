from uuid import UUID

from src.repositories.tenants import TenantRepository
from src.schemas.whatsapp import WhatsAppConnection, WhatsAppQR
from src.services.openwa import OpenWAClient, OpenWAUnavailable

_KNOWN_STATES = frozenset({"CREATED", "DISCONNECTED", "STOPPED", "FAILED", "READY", "CONNECTED", "QR_READY", "STARTING"})


class WhatsAppService:
    def __init__(self, tenants: TenantRepository, client: OpenWAClient | None) -> None:
        self._tenants = tenants
        self._client = client

    async def connection(self, tenant_id: UUID) -> WhatsAppConnection:
        tenant = await self._tenants.get_connection(tenant_id)
        if tenant is None or tenant.openwa_session_id is None:
            return WhatsAppConnection(status="NOT_CONFIGURED")
        if self._client is None:
            raise OpenWAUnavailable
        status = await self._client.session_status(tenant.openwa_session_id)
        return WhatsAppConnection(
            status=status if status in _KNOWN_STATES else "UNKNOWN", phone_number=tenant.phone_number,
        )

    async def qr(self, tenant_id: UUID) -> WhatsAppQR:
        tenant = await self._tenants.get_connection(tenant_id)
        if tenant is None or tenant.openwa_session_id is None:
            return WhatsAppQR()
        if self._client is None:
            raise OpenWAUnavailable
        if await self._client.session_status(tenant.openwa_session_id) not in {"STARTING", "QR_READY"}:
            return WhatsAppQR()
        qr_code = await self._client.qr_code(tenant.openwa_session_id)
        current = await self._tenants.get_connection(tenant_id)
        if current is None or current.openwa_session_id != tenant.openwa_session_id:
            return WhatsAppQR()
        return WhatsAppQR(qr_code=qr_code)
