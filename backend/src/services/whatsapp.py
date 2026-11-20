from re import fullmatch, sub
from uuid import UUID

from src.repositories.tenants import TenantRepository
from src.schemas.whatsapp import WhatsAppConnection, WhatsAppQR
from src.services.openwa import OpenWAUnavailable
from src.services.integrations import IntegrationService

_KNOWN_STATES = frozenset({"CREATED", "DISCONNECTED", "STOPPED", "FAILED", "READY", "CONNECTED", "QR_READY", "STARTING",
                           "INITIALIZING", "AUTHENTICATING", "ACTION_REQUIRED", "WRONG_NUMBER", "VERIFYING_NUMBER"})


class PairingConflict(Exception):
    pass


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
        try:
            status, detected_phone = await client.session_identity(tenant.openwa_session_id) if client else ("NOT_CONFIGURED", None)
        except OpenWAUnavailable as error:
            return WhatsAppConnection(status="UNAVAILABLE", session_id=tenant.openwa_session_id,
                                      phone_number=tenant.phone_number, error=str(error) or "Falha ao consultar o OpenWA.")
        if status in {"READY", "CONNECTED"} and tenant.phone_number:
            if detected_phone and detected_phone != tenant.phone_number:
                status = "WRONG_NUMBER"
            elif not tenant.openwa_number_verified:
                status = "VERIFYING_NUMBER"
        return WhatsAppConnection(
            status=status if status in _KNOWN_STATES or not client else "UNKNOWN", phone_number=tenant.phone_number,
            session_id=tenant.openwa_session_id,
        )

    async def pair(self, tenant_id: UUID) -> None:
        if not self._integrations.webhook_url(tenant_id):
            raise ValueError("Configure primeiro a origem pública HTTPS e a empresa do webhook no servidor")
        async with self._tenants.pairing_lock(tenant_id) as acquired:
            if not acquired:
                raise PairingConflict("Já existe um pareamento em andamento")
            tenant = await self._tenants.get_connection(tenant_id)
            if tenant is None or not tenant.phone_number:
                raise ValueError("Salve o número do WhatsApp antes de iniciar o pareamento")
            client = await self._integrations.openwa(tenant_id)
            if client is None:
                raise ValueError("Solicite ao SuperAdmin que configure o servidor e a chave OpenWA")
            session_id = tenant.openwa_session_id
            if session_id is None:
                session_id = await client.ensure_session(f"nexus-atende-{tenant_id}")
                if not await self._tenants.bind_session(tenant_id, tenant.phone_number, session_id):
                    raise PairingConflict("O telefone ou a sessão mudou. Recarregue e tente novamente")
            status, actual_phone = await client.session_identity(session_id)
            if status in {"READY", "CONNECTED"} and actual_phone and actual_phone != tenant.phone_number:
                raise PairingConflict("O número conectado ao OpenWA difere do número salvo. Confira a sessão dedicada no OpenWA.")
            if status in {"CREATED", "STOPPED", "FAILED", "DISCONNECTED"}:
                await client.start_session(session_id)

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
