from asyncio import to_thread
from urllib.error import HTTPError

from pydantic import SecretStr

from src.schemas.work import WorkItem, WorkStatus
from src.services.provider_http import request_json


class ResendClient:
    def __init__(self, api_key: SecretStr, sender: str, recipient: str) -> None:
        self._key = api_key
        self._sender = sender
        self._recipient = recipient

    @property
    def notifications_enabled(self) -> bool:
        return bool(self._recipient)

    async def _send(self, recipient: str, subject: str, content: str, key: str) -> bool:
        response = await to_thread(request_json, "https://api.resend.com/emails", {
            "Authorization": f"Bearer {self._key.get_secret_value()}", "Idempotency-Key": key,
        }, {"from": self._sender, "to": [recipient], "subject": subject, "text": content})
        return isinstance(response, dict) and bool(response.get("id"))

    async def invite(self, recipient: str, url: str, key: str) -> bool:
        try:
            return await self._send(recipient, "Nexus Atende | Defina sua senha",
                f"Você recebeu um convite para operar o Nexus Atende. Defina sua senha neste link, válido por 24 horas:\n\n{url}",
                f"nexus-atende/invite/{key}")
        except (OSError, ValueError):
            return False

    async def notify(self, work: WorkItem) -> WorkStatus:
        retry: WorkStatus = "pending" if work.attempts < 3 else "failed"
        try:
            accepted = await self._send(self._recipient, "Nexus Atende | Atendimento aguardando",
                f"Uma conversa precisa de atendimento humano. Abra a fila do Nexus Atende.\n\nReferência: {work.conversation_id}",
                f"nexus-atende/handoff/{work.id}")
        except HTTPError as error:
            return retry if error.code in {408, 409, 429} or error.code >= 500 else "failed"
        except (OSError, ValueError):
            return retry
        return "sent" if accepted else retry
