from asyncio import Semaphore, to_thread
from base64 import b64decode
from binascii import Error as Base64Error
from re import fullmatch, sub
from urllib.error import HTTPError, URLError
from uuid import UUID

from pydantic import SecretStr

from src.schemas.whatsapp import OpenWAQR, OpenWASession
from src.schemas.work import WhatsAppDispatch
from src.services.provider_http import request_json

_QR_PREFIX = "data:image/png;base64,"


class OpenWAUnavailable(Exception):
    pass


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
    def __init__(self, base_url: str, api_key: SecretStr) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._requests = Semaphore(4)

    def _read(self, path: str) -> object:
        decoded = request_json(self._base_url + path, {"X-API-Key": self._api_key.get_secret_value()})
        return decoded.get("data", decoded) if isinstance(decoded, dict) else decoded

    async def session_status(self, session_id: UUID) -> str:
        status, _ = await self.session_identity(session_id)
        return status

    async def session_identity(self, session_id: UUID) -> tuple[str, str | None]:
        try:
            async with self._requests:
                payload = await to_thread(self._read, f"/sessions/{session_id}")
            return OpenWASession.model_validate(payload).status.upper(), account_phone(payload)
        except (URLError, OSError, ValueError):
            raise OpenWAUnavailable from None

    def _write(self, path: str, payload: object) -> object:
        result = request_json(self._base_url + path, {"X-API-Key": self._api_key.get_secret_value()}, payload)
        if isinstance(result, dict) and result.get("success") is False:
            raise ValueError("Operação recusada pelo OpenWA")
        return result.get("data", result) if isinstance(result, dict) else result

    async def ensure_session(self, name: str) -> UUID:
        try:
            for offset in range(0, 1000, 100):
                payload = await to_thread(self._read, f"/sessions?limit=100&offset={offset}")
                sessions = payload.get("sessions") if isinstance(payload, dict) else payload
                if not isinstance(sessions, list):
                    raise ValueError("Resposta inválida ao listar sessões")
                matches = [item for item in sessions if isinstance(item, dict) and item.get("name") == name]
                if len(matches) > 1:
                    raise ValueError("Mais de uma sessão dedicada encontrada")
                if matches:
                    return UUID(str(matches[0].get("id", "")))
                if len(sessions) < 100:
                    created = await to_thread(self._write, "/sessions", {"name": name})
                    return UUID(str(created.get("id", "")) if isinstance(created, dict) else "")
        except HTTPError as error:
            raise OpenWAUnavailable(f"OpenWA recusou a preparação da sessão (HTTP {error.code}). Confira a chave e suas permissões.") from None
        except (OSError, ValueError):
            raise OpenWAUnavailable("Não foi possível preparar a sessão no OpenWA. Verifique a conexão e tente novamente.") from None
        raise OpenWAUnavailable("A listagem de sessões do OpenWA não pôde ser concluída")

    async def start_session(self, session_id: UUID) -> None:
        try:
            await to_thread(self._write, f"/sessions/{session_id}/start", {})
        except HTTPError as error:
            raise OpenWAUnavailable(f"OpenWA recusou o início da sessão (HTTP {error.code}). Confira a chave e suas permissões.") from None
        except (OSError, ValueError):
            raise OpenWAUnavailable("Não foi possível iniciar a sessão no OpenWA. Tente novamente.") from None

    async def qr_code(self, session_id: UUID) -> str | None:
        try:
            async with self._requests:
                payload = await to_thread(self._read, f"/sessions/{session_id}/qr")
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
                hooks = await to_thread(self._read, f"{path}?limit=100&offset={offset}")
                if not isinstance(hooks, list):
                    raise ValueError("Resposta inválida ao listar webhooks")
                matches = [hook for hook in hooks if isinstance(hook, dict) and hook.get("url") == url]
                if any(hook.get("active") is True and isinstance(hook.get("events"), list)
                       and "message.received" in hook["events"] for hook in matches):
                    return
                if matches:
                    raise ValueError("Webhook existente inativo ou sem o evento de recebimento")
                if len(hooks) < 100:
                    result = await to_thread(request_json, self._base_url + path,
                        {"X-API-Key": self._api_key.get_secret_value()},
                        {"url": url, "events": ["message.received"], "secret": secret.get_secret_value()})
                    if isinstance(result, dict) and result.get("success") is False:
                        raise ValueError("Cadastro do webhook recusado")
                    return
        except (OSError, ValueError):
            raise OpenWAUnavailable from None
        raise OpenWAUnavailable

    async def send_text(self, session_id: UUID, chat_id: str, content: str) -> WhatsAppDispatch:
        try:
            payload = await to_thread(request_json, f"{self._base_url}/sessions/{session_id}/messages/send-text",
                {"X-API-Key": self._api_key.get_secret_value()}, {"chatId": chat_id, "text": content, "linkPreview": False})
        except HTTPError as error:
            return WhatsAppDispatch(status="failed" if 400 <= error.code < 500 and error.code != 408 else "uncertain")
        except (OSError, ValueError):
            return WhatsAppDispatch(status="uncertain")
        result = payload.get("data", payload) if isinstance(payload, dict) else payload
        provider_id = result.get("messageId") if isinstance(result, dict) else None
        if isinstance(provider_id, str) and 0 < len(provider_id) <= 250 and "\x00" not in provider_id:
            return WhatsAppDispatch(status="sent", provider_id=provider_id)
        return WhatsAppDispatch(status="uncertain")
