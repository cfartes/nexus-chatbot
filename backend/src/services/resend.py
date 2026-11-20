from asyncio import to_thread
import logging
from urllib.error import HTTPError
from uuid import uuid4

from pydantic import SecretStr

from src.schemas.work import WorkItem, WorkStatus
from src.services.provider_http import request_json

logger = logging.getLogger(__name__)


class ResendRejected(Exception):
    pass


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
        except HTTPError as error:
            logger.warning("Resend rejected operator invitation: HTTP %s", error.code)
            return False
        except (OSError, ValueError) as error:
            logger.warning("Could not send operator invitation (%s)", type(error).__name__)
            return False

    async def send_test(self) -> None:
        if not self._recipient:
            raise ValueError("Salve o e-mail da equipe para receber o teste")
        try:
            accepted = await self._send(self._recipient, "Nexus Atende | Teste do Resend",
                "O Resend aceitou o envio de teste do Nexus Atende.", f"nexus-atende/test/{uuid4()}")
        except HTTPError as error:
            messages = {
                401: "Confira a chave da API",
                403: "Confira o domínio do remetente, a permissão da chave e os destinatários permitidos",
                422: "Confira os endereços do remetente e do destinatário",
                429: "O limite de envios foi atingido. Aguarde e tente novamente",
            }
            raise ResendRejected(f"Resend recusou o teste (HTTP {error.code}). {messages.get(error.code, 'Tente novamente mais tarde')}.") from None
        except (OSError, ValueError):
            raise ResendRejected("Não foi possível confirmar o envio no Resend. Confira a conexão e tente novamente.") from None
        if not accepted:
            raise ResendRejected("O Resend não retornou uma confirmação de envio")

    async def notify(self, work: WorkItem) -> WorkStatus:
        retry: WorkStatus = "pending" if work.attempts < 3 else "failed"
        try:
            accepted = await self._send(self._recipient, "Nexus Atende | Atendimento aguardando",
                f"Uma conversa precisa de atendimento humano. Abra a fila do Nexus Atende.\n\nReferência: {work.conversation_id}",
                f"nexus-atende/handoff/{work.id}")
        except HTTPError as error:
            logger.warning("Resend rejected handoff notification: HTTP %s", error.code)
            return retry if error.code in {408, 409, 429} or error.code >= 500 else "failed"
        except (OSError, ValueError):
            return retry
        return "sent" if accepted else retry
