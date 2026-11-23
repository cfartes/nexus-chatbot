from asyncio import Semaphore, to_thread
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlsplit
from uuid import UUID

from src.repositories.operators import OperatorRepository
from src.schemas.operators import AcceptInvite, FunctionInput, OperatorCreate, OperatorFunction, OperatorRecord, OperatorUpdate
from src.services.integrations import IntegrationService, IntegrationUnavailable
from src.services.passwords import hash_password
from src.services.resend import ResendClient, ResendRejected


class OperatorService:
    def __init__(self, repository: OperatorRepository, integrations: IntegrationService, origin: str | None) -> None:
        self._repository = repository
        self._integrations = integrations
        self._origin = origin
        self._slots = Semaphore(2)

    async def list_operators(self, tenant_id: UUID, *, platform: bool = False) -> list[OperatorRecord]:
        return await self._repository.list(tenant_id, platform=platform)

    async def create(self, tenant_id: UUID, operator: OperatorCreate, *, platform: bool = False) -> OperatorRecord | None:
        name = operator.name.strip()
        if not name:
            raise ValueError("Informe o nome")
        resend, origin = await self.invitation_sender(tenant_id)
        token = f"{tenant_id}.{token_urlsafe(32)}"
        invite_hash = sha256(token.encode()).hexdigest()
        member = await self._repository.create(tenant_id, operator.model_copy(update={"name": name, "email": operator.email.lower()}),
                                               invite_hash, platform=platform)
        if member:
            await self._send_invitation(member, resend, f"{origin}/convite#{token}", invite_hash)
        return member

    async def invitation_sender(self, tenant_id: UUID) -> tuple[ResendClient, str]:
        origin = self._origin or ""
        parsed = urlsplit(origin)
        loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username is not None or parsed.path or parsed.query or parsed.fragment:
            raise IntegrationUnavailable
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise IntegrationUnavailable
        resend = await self._integrations.resend(tenant_id)
        if resend is None:
            raise IntegrationUnavailable
        return resend, origin

    async def renew(self, tenant_id: UUID, user_id: UUID, *, platform: bool = False) -> OperatorRecord | None:
        resend, origin = await self.invitation_sender(tenant_id)
        token = f"{tenant_id}.{token_urlsafe(32)}"
        invite_hash = sha256(token.encode()).hexdigest()
        member = await self._repository.renew(tenant_id, user_id, invite_hash, platform=platform)
        if member:
            await self._send_invitation(member, resend, f"{origin}/convite#{token}", invite_hash)
        return member

    async def _send_invitation(self, member: OperatorRecord, resend: ResendClient, url: str, invite_hash: str) -> None:
        try:
            await resend.invite(member.email, url, invite_hash)
        except ResendRejected as error:
            member.invite_sent = False
            member.invite_error = str(error)
        else:
            member.invite_sent = True

    async def accept(self, request: AcceptInvite) -> bool:
        token = request.token.get_secret_value()
        try:
            tenant_id = UUID(token[:36])
        except ValueError:
            return False
        invite_hash = sha256(token.encode()).hexdigest()
        async with self._slots:
            if not await self._repository.invite_valid(tenant_id, invite_hash):
                return False
            password_hash = await to_thread(hash_password, request.password.get_secret_value())
            return await self._repository.accept(tenant_id, invite_hash, password_hash)

    async def update(self, tenant_id: UUID, user_id: UUID, operator: OperatorUpdate) -> OperatorRecord | None:
        name = operator.name.strip()
        if not name:
            raise ValueError("Informe o nome")
        return await self._repository.update(tenant_id, user_id, operator.model_copy(
            update={"name": name, "email": operator.email.lower() if operator.email else None},
        ))

    async def delete(self, tenant_id: UUID, user_id: UUID) -> bool:
        return await self._repository.update(tenant_id, user_id, None) is not None

    async def functions(self, tenant_id: UUID) -> list[OperatorFunction]:
        return await self._repository.functions(tenant_id)

    async def save_function(self, tenant_id: UUID, content: FunctionInput, function_id: UUID | None = None) -> OperatorFunction | None:
        name = content.name.strip()
        if not name:
            raise ValueError("Informe o nome da função.")
        return await self._repository.save_function(tenant_id, content.model_copy(update={"name": name}), function_id)

    async def delete_function(self, tenant_id: UUID, function_id: UUID) -> bool:
        return await self._repository.delete_function(tenant_id, function_id)
