from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from src.repositories.tenants import TenantRepository
from src.schemas.tenants import ClientCreate, ClientInvite, ClientName, ClientRecord
from src.services.operators import OperatorService
from src.services.resend import ResendRejected


class ClientService:
    def __init__(self, tenants: TenantRepository, operators: OperatorService, platform_tenant: UUID | None) -> None:
        self._tenants = tenants
        self._operators = operators
        self._platform_tenant = platform_tenant

    async def list(self) -> list[ClientRecord]:
        return await self._tenants.clients()

    async def create(self, content: ClientCreate) -> ClientInvite:
        content.name = _name(content.name)
        content.admin.name = _name(content.admin.name)
        content.admin.email = content.admin.email.lower()
        client = ClientInvite(id=uuid4(), name=content.name, admin_invite_pending=True)
        await self._invite(client, content)
        return client

    async def renew(self, tenant_id: UUID) -> ClientInvite:
        client = next((item for item in await self.list() if item.id == tenant_id and item.archived_at is None), None)
        if client is None:
            raise LookupError
        result = ClientInvite(id=client.id, name=client.name, admin_invite_pending=True)
        await self._invite(result, None)
        return result

    async def _invite(self, client: ClientInvite, content: ClientCreate | None) -> None:
        resend, origin = await self._operators.invitation_sender(client.id)
        token = f"{client.id}.{token_urlsafe(32)}"
        invite_hash = sha256(token.encode()).hexdigest()
        if content is not None:
            await self._tenants.create_client(client.id, content, invite_hash)
            email = content.admin.email
        else:
            pending_email = await self._tenants.renew_admin(client.id, invite_hash)
            if pending_email is None:
                raise LookupError
            email = pending_email
        try:
            await resend.invite(email, f"{origin}/convite#{token}", invite_hash)
        except ResendRejected as error:
            client.invite_error = str(error)

    async def update(self, tenant_id: UUID, content: ClientName | None) -> None:
        if content is None and tenant_id == self._platform_tenant:
            raise ValueError("A empresa principal da plataforma não pode ser arquivada.")
        if not await self._tenants.update_client(tenant_id, _name(content.name) if content is not None else None):
            raise LookupError


def _name(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Informe o nome.")
    return trimmed
