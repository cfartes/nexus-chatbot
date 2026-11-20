from asyncio import to_thread
from http.client import HTTPException
from json import loads
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
            "User-Agent": "Nexus-Atende",
        }, {"from": self._sender, "to": [recipient], "subject": subject, "text": content})
        return isinstance(response, dict) and bool(response.get("id"))

    async def invite(self, recipient: str, url: str, key: str) -> None:
        await self._send_checked(recipient, "Nexus Atende | Defina sua senha",
            f"Você recebeu um convite para operar o Nexus Atende. Defina sua senha neste link, válido por 24 horas:\n\n{url}",
            f"nexus-atende/invite/{key}")

    async def send_test(self) -> None:
        if not self._recipient:
            raise ValueError("Salve o destinatário do e-mail de teste")
        await self._send_checked(self._recipient, "Nexus Atende | Teste do Resend",
            "O Resend aceitou o envio de teste do Nexus Atende.", f"nexus-atende/test/{uuid4()}")

    async def _send_checked(self, recipient: str, subject: str, content: str, key: str) -> None:
        try:
            accepted = await self._send(recipient, subject, content, key)
        except HTTPError as error:
            logger.warning("Resend rejected email: HTTP %s", error.code)
            message = await to_thread(_rejection_hint, error)
            raise ResendRejected(f"Resend recusou o envio (HTTP {error.code}). {message}") from None
        except (OSError, HTTPException, ValueError) as error:
            logger.warning("Resend email confirmation unavailable (%s)", type(getattr(error, "reason", error)).__name__)
            raise ResendRejected("O Nexus Atende não recebeu uma confirmação do Resend. Confira a conexão da VPS com api.resend.com.") from None
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
        except (OSError, HTTPException, ValueError) as error:
            logger.warning("Resend notification confirmation unavailable (%s)", type(getattr(error, "reason", error)).__name__)
            return retry
        return "sent" if accepted else retry


def _rejection_hint(error: HTTPError) -> str:
    with error:
        try:
            payload: object = loads(error.read(8192))
        except (OSError, HTTPException, ValueError):
            payload = None
    reason = str(payload.get("message", "")).lower() if isinstance(payload, dict) else ""
    if error.code == 403 and "only send testing emails" in reason:
        return "O remetente de teste só pode enviar para o e-mail da conta Resend. Use um remetente de domínio verificado."
    if error.code == 403 and "domain is not verified" in reason:
        return "Verifique o domínio do remetente no Resend e confira o endereço salvo no painel."
    if "api key is invalid" in reason:
        return "Confira a chave da API."
    return {
        400: "Confira os endereços e a chave do Resend.",
        401: "Confira a chave da API.",
        403: "Confira o domínio do remetente, a permissão da chave e os destinatários permitidos.",
        422: "Confira os endereços do remetente e do destinatário.",
        429: "O limite de envios foi atingido. Aguarde e tente novamente.",
    }.get(error.code, "Tente novamente mais tarde.")
