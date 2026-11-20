from asyncio import Semaphore, to_thread
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
import logging
from math import ceil
from re import fullmatch, sub
from threading import Lock
from time import monotonic, time
from urllib.error import HTTPError, URLError
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from src.schemas.whatsapp import OpenWAQR, OpenWASession
from src.schemas.work import WhatsAppDispatch
from src.services.provider_http import request_json

_QR_PREFIX = "data:image/png;base64,"
logger = logging.getLogger(__name__)


class OpenWAUnavailable(Exception):
    pass


class OpenWARateLimited(OpenWAUnavailable):
    def __init__(self, retry_after: int, *, deadline: float | None = None) -> None:
        self.retry_after = retry_after
        self.deadline = deadline
        super().__init__("O OpenWA limitou temporariamente as chamadas (HTTP 429). A consulta será retomada automaticamente.")


def _retry_delay(value: str) -> int:
    try:
        if value.isascii() and value.isdecimal():
            return min(86400, max(1, int(value)))
        return max(1, ceil(parsedate_to_datetime(value).timestamp() - time()))
    except (ValueError, TypeError, OverflowError, OSError):
        return 60


def account_phone(payload: object, depth: int = 0) -> str | None:
    if not isinstance(payload, dict) or depth > 2:
        return None
    for field in ("phone", "phoneNumber", "phone_number", "number", "user", "_serialized", "id"):
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        if "@" in value:
            value, host = value.split("@", 1)
            if host not in {"c.us", "s.whatsapp.net"}:
                continue
            value = value.split(":", 1)[0]
        elif field in {"_serialized", "id"}:
            continue
        cleaned = sub(r"[ ().-]", "", value).removeprefix("+")
        if fullmatch(r"[1-9][0-9]{7,14}", cleaned):
            return f"+{cleaned}"
    for field in ("me", "wid", "account", "data", "session"):
        number = account_phone(payload.get(field), depth + 1)
        if number:
            return number
    return None


class OpenWAClient:
    _cooldown: dict[str, float] = {}
    _cooldown_lock = Lock()

    def __init__(self, base_url: str, api_key: SecretStr, *, retry_until: float = 0,
                 defer: Callable[[float], Awaitable[None]] | None = None) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._retry_until = retry_until
        self._defer = defer
        self._requests = Semaphore(4)

    def retry_after(self) -> int:
        with self._cooldown_lock:
            remaining = self._cooldown.get(self._base_url, 0) - monotonic()
            if remaining <= 0:
                self._cooldown.pop(self._base_url, None)
            return max(0, ceil(max(remaining, self._retry_until - time())))

    async def _call(self, operation: Callable[..., object], *args: object) -> object:
        delay = self.retry_after()
        if delay:
            raise OpenWARateLimited(delay)
        try:
            return await to_thread(operation, *args)
        except OpenWARateLimited as error:
            if self._defer and error.deadline is not None:
                try:
                    await self._defer(error.deadline)
                except SQLAlchemyError as storage_error:
                    logger.warning("Could not share OpenWA cooldown (%s)", type(storage_error).__name__)
            raise

    def _request(self, path: str, payload: object = None) -> object:
        delay = self.retry_after()
        if delay:
            raise OpenWARateLimited(delay)
        headers = {"X-API-Key": self._api_key.get_secret_value()}
        try:
            return request_json(self._base_url + path, headers) if payload is None else request_json(self._base_url + path, headers, payload)
        except HTTPError as error:
            if error.code != 429:
                raise
            with error:
                delay = _retry_delay(error.headers.get("Retry-After", "") if error.headers else "")
            with self._cooldown_lock:
                deadline = monotonic() + delay
                self._cooldown[self._base_url] = max(deadline, self._cooldown.get(self._base_url, 0))
            raise OpenWARateLimited(delay, deadline=time() + delay) from None

    def _read(self, path: str) -> object:
        decoded = self._request(path)
        return decoded.get("data", decoded) if isinstance(decoded, dict) else decoded

    async def session_status(self, session_id: UUID) -> str:
        status, _ = await self.session_identity(session_id)
        return status

    async def session_identity(self, session_id: UUID) -> tuple[str, str | None]:
        try:
            async with self._requests:
                payload = await self._call(self._read, f"/sessions/{session_id}")
            return OpenWASession.model_validate(payload).status.upper(), account_phone(payload)
        except HTTPError as error:
            raise OpenWAUnavailable(f"Consulta da sessão recusada pelo OpenWA (HTTP {error.code}).") from None
        except (URLError, OSError, ValueError):
            raise OpenWAUnavailable("O OpenWA não retornou um status de sessão válido.") from None

    def _write(self, path: str, payload: object) -> object:
        result = self._request(path, payload)
        if isinstance(result, dict) and result.get("success") is False:
            raise ValueError("Operação recusada pelo OpenWA")
        return result.get("data", result) if isinstance(result, dict) else result

    async def ensure_session(self, name: str) -> UUID:
        try:
            for offset in range(0, 1000, 100):
                payload = await self._call(self._read, f"/sessions?limit=100&offset={offset}")
                sessions = payload.get("sessions") if isinstance(payload, dict) else payload
                if not isinstance(sessions, list):
                    raise ValueError("Resposta inválida ao listar sessões")
                matches = [item for item in sessions if isinstance(item, dict) and item.get("name") == name]
                if len(matches) > 1:
                    raise ValueError("Mais de uma sessão dedicada encontrada")
                if matches:
                    return UUID(str(matches[0].get("id", "")))
                if len(sessions) < 100:
                    created = await self._call(self._write, "/sessions", {"name": name})
                    return UUID(str(created.get("id", "")) if isinstance(created, dict) else "")
        except HTTPError as error:
            raise OpenWAUnavailable(f"OpenWA recusou a preparação da sessão (HTTP {error.code}). Confira a chave e suas permissões.") from None
        except (OSError, ValueError):
            raise OpenWAUnavailable("Não foi possível preparar a sessão no OpenWA. Verifique a conexão e tente novamente.") from None
        raise OpenWAUnavailable("A listagem de sessões do OpenWA não pôde ser concluída")

    async def start_session(self, session_id: UUID) -> None:
        try:
            await self._call(self._write, f"/sessions/{session_id}/start", {})
        except HTTPError as error:
            raise OpenWAUnavailable(f"OpenWA recusou o início da sessão (HTTP {error.code}). Confira a chave e suas permissões.") from None
        except (OSError, ValueError):
            raise OpenWAUnavailable("Não foi possível iniciar a sessão no OpenWA. Tente novamente.") from None

    async def qr_code(self, session_id: UUID) -> str | None:
        try:
            async with self._requests:
                payload = await self._call(self._read, f"/sessions/{session_id}/qr")
            value = OpenWAQR.model_validate(payload).qrCode
            if not value:
                return None
            encoded = value.removeprefix(_QR_PREFIX)
            if not b64decode(encoded, validate=True).startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("OpenWA QR is not PNG")
            return _QR_PREFIX + encoded
        except (URLError, OSError, ValueError, Base64Error):
            raise OpenWAUnavailable from None

    async def ensure_webhook(self, session_id: UUID, url: str, secret: SecretStr) -> None:
        path = f"/sessions/{session_id}/webhooks"
        try:
            for offset in range(0, 1000, 100):
                query = "?limit=100" if offset == 0 else f"?limit=100&offset={offset}"
                payload = await self._call(self._read, path + query)
                hooks = payload.get("webhooks") if isinstance(payload, dict) else payload
                if not isinstance(hooks, list):
                    raise OpenWAUnavailable("O OpenWA retornou uma lista de webhooks em formato inesperado.")
                matches = [hook for hook in hooks if isinstance(hook, dict) and hook.get("url") == url]
                if any(hook.get("active") is True and isinstance(hook.get("events"), list)
                       and "message.received" in hook["events"] for hook in matches):
                    return
                if matches:
                    raise OpenWAUnavailable("O webhook está inativo ou não inclui o evento de novas mensagens.")
                if len(hooks) < 100:
                    result = await self._call(self._request, path,
                        {"url": url, "events": ["message.received"], "secret": secret.get_secret_value()})
                    if isinstance(result, dict) and result.get("success") is False:
                        raise OpenWAUnavailable("O OpenWA recusou o cadastro do webhook de mensagens.")
                    return
        except HTTPError as error:
            raise OpenWAUnavailable(f"O OpenWA recusou a sincronização do webhook (HTTP {error.code}).") from None
        except (OSError, ValueError):
            raise OpenWAUnavailable("Falha ao consultar ou cadastrar o webhook no OpenWA.") from None
        raise OpenWAUnavailable("A listagem de webhooks do OpenWA não pôde ser concluída.")

    async def send_text(self, session_id: UUID, chat_id: str, content: str) -> WhatsAppDispatch:
        try:
            payload = await self._call(self._request, f"/sessions/{session_id}/messages/send-text",
                {"chatId": chat_id, "text": content, "linkPreview": False})
        except OpenWARateLimited as error:
            logger.warning("OpenWA deferred WhatsApp delivery for %s seconds (HTTP 429)", error.retry_after)
            return WhatsAppDispatch(status="pending", retry_after=error.retry_after)
        except HTTPError as error:
            return WhatsAppDispatch(status="failed" if 400 <= error.code < 500 and error.code != 408 else "uncertain")
        except (OSError, ValueError):
            return WhatsAppDispatch(status="uncertain")
        result = payload.get("data", payload) if isinstance(payload, dict) else payload
        provider_id = result.get("messageId") if isinstance(result, dict) else None
        if isinstance(provider_id, str) and 0 < len(provider_id) <= 250 and "\x00" not in provider_id:
            return WhatsAppDispatch(status="sent", provider_id=provider_id)
        return WhatsAppDispatch(status="uncertain")
