from asyncio import Semaphore, to_thread
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from uuid import UUID

from src.repositories.auth import AuthRepository
from src.schemas.auth import LoginRequest, Operator
from src.services.passwords import verify_password

SESSION_SECONDS = 8 * 60 * 60
_DUMMY_HASH = f"scrypt${'00' * 16}${'00' * 64}"


class InvalidLogin(Exception):
    pass


class LoginLimited(Exception):
    pass


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def csrf_token(session: str) -> str:
    return _digest(f"csrf:{session}")


def valid_csrf(session: str, csrf: str) -> bool:
    return csrf.isascii() and compare_digest(csrf_token(session), csrf)


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository
        self._password_slots = Semaphore(2)

    async def login(self, credentials: LoginRequest, ip: str) -> tuple[Operator, str]:
        email = credentials.email.strip().lower()
        identity_key = _digest(f"identity:{credentials.tenant_id}:{email}")
        if not await self._repository.record_attempt(_digest(f"ip:{ip}"), identity_key):
            raise LoginLimited
        identity = await self._repository.find_identity(credentials.tenant_id, email)
        stored = identity.password_hash.get_secret_value() if identity else _DUMMY_HASH
        async with self._password_slots:
            valid = await to_thread(verify_password, credentials.password.get_secret_value(), stored)
        if not valid or identity is None:
            raise InvalidLogin
        operator = Operator.model_validate(identity.model_dump())
        session = f"{operator.tenant_id}.{token_urlsafe(32)}"
        if not await self._repository.create_session(operator, _digest(session), stored):
            raise InvalidLogin
        return operator, session

    async def authenticate(self, session: str) -> Operator:
        if len(session) != 80 or session[36] != ".":
            raise InvalidLogin
        try:
            tenant_id = UUID(session[:36])
        except ValueError:
            raise InvalidLogin from None
        operator = await self._repository.find_session(tenant_id, _digest(session))
        if operator is None:
            raise InvalidLogin
        return operator

    async def logout(self, session: str, csrf: str) -> None:
        operator = await self.authenticate(session)
        if not valid_csrf(session, csrf):
            raise PermissionError
        await self._repository.revoke_session(operator.tenant_id, _digest(session))
