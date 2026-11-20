from asyncio import Semaphore, to_thread
from base64 import b64decode
from binascii import Error as Base64Error
from urllib.error import HTTPError, URLError
from uuid import UUID

from pydantic import SecretStr

from src.schemas.whatsapp import OpenWAQR, OpenWASession
from src.schemas.work import WhatsAppDispatch
from src.services.provider_http import request_json

_QR_PREFIX = "data:image/png;base64,"


class OpenWAUnavailable(Exception):
    pass


class OpenWAClient:
    def __init__(self, base_url: str, api_key: SecretStr) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._requests = Semaphore(4)

    def _read(self, path: str) -> object:
        decoded = request_json(self._base_url + path, {"X-API-Key": self._api_key.get_secret_value()})
        return decoded.get("data", decoded) if isinstance(decoded, dict) else decoded

    async def session_status(self, session_id: UUID) -> str:
        try:
            async with self._requests:
                payload = await to_thread(self._read, f"/sessions/{session_id}")
            return OpenWASession.model_validate(payload).status.upper()
        except (URLError, OSError, ValueError):
            raise OpenWAUnavailable from None

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
