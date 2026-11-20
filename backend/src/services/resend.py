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

    async def notify(self, work: WorkItem) -> WorkStatus:
        retry: WorkStatus = "pending" if work.attempts < 3 else "failed"
        try:
            response = await to_thread(request_json, "https://api.resend.com/emails", {
                "Authorization": f"Bearer {self._key.get_secret_value()}",
                "Idempotency-Key": f"nexus-atende/handoff/{work.id}",
            }, {
                "from": self._sender, "to": [self._recipient], "subject": "Nexus Atende | Atendimento aguardando",
                "text": f"Uma conversa precisa de atendimento humano. Abra a fila do Nexus Atende.\n\nReferência: {work.conversation_id}",
            })
        except HTTPError as error:
            return retry if error.code in {408, 409, 429} or error.code >= 500 else "failed"
        except (OSError, ValueError):
            return retry
        return "sent" if isinstance(response, dict) and response.get("id") else retry
