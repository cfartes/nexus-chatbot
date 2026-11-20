from hashlib import sha256
from hmac import compare_digest, digest
from re import fullmatch
from uuid import UUID

from pydantic import SecretStr, ValidationError

from src.repositories.incoming_messages import IncomingMessageRepository
from src.schemas.openwa_events import IncomingText, OpenWAEvent, OpenWAReceivedEvent


class InvalidSignature(Exception):
    pass


class InvalidEvent(Exception):
    pass


class OpenWAWebhook:
    def __init__(self, messages: IncomingMessageRepository, tenant_id: UUID, secret: SecretStr, *, bot_enabled: bool = False) -> None:
        self._messages = messages
        self._tenant_id = tenant_id
        self._secret = secret.get_secret_value().encode()
        self._bot_enabled = bot_enabled

    async def receive(self, tenant_id: UUID, signature: str, raw: bytes) -> None:
        if tenant_id != self._tenant_id or len(signature) != 71 or not signature.isascii():
            raise InvalidSignature
        expected = "sha256=" + digest(self._secret, raw, sha256).hex()
        if not compare_digest(signature, expected):
            raise InvalidSignature
        try:
            if OpenWAEvent.model_validate_json(raw).event != "message.received":
                return
            event = OpenWAReceivedEvent.model_validate_json(raw)
        except ValidationError:
            raise InvalidEvent from None
        content = event.data.body
        if event.data.from_me or event.data.is_group or event.data.has_media or not content or not content.strip():
            return
        chat_id = event.data.sender
        if not fullmatch(r"[0-9]{5,30}@(c\.us|s\.whatsapp\.net|lid)", chat_id):
            return
        if chat_id.endswith("@s.whatsapp.net"):
            chat_id = chat_id.removesuffix("@s.whatsapp.net") + "@c.us"
        await self._messages.save(tenant_id, IncomingText(
            session_id=event.session_id, message_id=event.data.id, chat_id=chat_id, content=content,
            display_name=event.data.display_name.strip() or None if event.data.display_name else None,
        ), bot_enabled=self._bot_enabled)
