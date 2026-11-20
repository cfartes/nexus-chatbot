from urllib.parse import urlsplit
from functools import partial
from hmac import digest
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from src.repositories.integrations import IntegrationRepository, StoredIntegrations
from src.schemas.integrations import AISettings, IntegrationsView, OpenWASettings, ResendSettings, WebhookStatus
from src.services.openai import OpenAIClient
from src.services.openwa import OpenWAClient, remaining_cooldown
from src.services.resend import ResendClient
from src.settings import Settings


class IntegrationUnavailable(Exception):
    pass


class IntegrationService:
    def __init__(self, repository: IntegrationRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._cipher = Fernet(settings.config_key.get_secret_value()) if settings.config_key else None
        self._openwa_url = settings.openwa_endpoint()
        self._openwa_allowed = {settings.normalize_openwa_url(value) for value in settings.openwa_allowed_urls.split(",") if value.strip()}
        if self._openwa_url:
            self._openwa_allowed.add(self._openwa_url)
        self._ollama_url = settings.ollama_url.rstrip("/") if settings.ollama_url else None
        if self._ollama_url:
            url = urlsplit(self._ollama_url)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or url.query or url.fragment or url.path:
                raise ValueError("NEXUS_ATENDE_OLLAMA_URL must be an HTTP(S) server origin")

    def _encrypt(self, value: SecretStr) -> str:
        secret = value.get_secret_value().strip()
        if not secret or any(character in secret for character in "\r\n\x00"):
            raise ValueError("Informe uma chave válida")
        if self._cipher is None:
            raise IntegrationUnavailable
        return self._cipher.encrypt(secret.encode()).decode()

    def _decrypt(self, value: str | None) -> SecretStr | None:
        if value is None:
            return None
        if self._cipher is None:
            raise IntegrationUnavailable
        try:
            return SecretStr(self._cipher.decrypt(value.encode()).decode())
        except InvalidToken:
            raise IntegrationUnavailable from None

    async def view(self, tenant_id: UUID) -> IntegrationsView:
        local = await self._repository.get(tenant_id)
        shared_id = self._shared_tenant(tenant_id)
        saved = local if shared_id == tenant_id else await self._repository.get(shared_id)
        endpoint = saved.openwa_url or self._openwa_url
        has_openwa_key = bool(saved.openwa_key or self._settings.openwa_api_key)
        webhook_configured = endpoint in self._openwa_allowed and has_openwa_key and self.webhook_url(tenant_id) is not None
        retry_after = remaining_cooldown(saved.openwa_cooldowns.get(endpoint, 0)) if endpoint and webhook_configured else 0
        status: WebhookStatus = local.openwa_webhook_status if webhook_configured else "not_configured"
        detail = local.openwa_webhook_error if webhook_configured else None
        if retry_after:
            status = "rate_limited"
        elif status == "rate_limited":
            status = "pending"
            detail = "O intervalo do OpenWA terminou. Aguardando a confirmação do recebimento."
        return IntegrationsView(provider=saved.provider or "openai", model=saved.model or self._settings.openai_model,
            embedding_model=saved.embedding_model or "nomic-embed-text",
            ai_has_key=bool(saved.ai_key or (saved.provider in (None, "openai") and self._settings.openai_api_key)),
            embedding_has_key=bool(saved.embedding_key or self._settings.openai_api_key), ollama_url=self._ollama_url,
            resend_sender=saved.sender if saved.sender is not None else self._settings.resend_from or "",
            resend_recipient=self._test_recipient(saved),
            resend_has_key=bool(saved.resend_key or self._settings.resend_api_key), openwa_url=endpoint,
            openwa_webhook_status=status, openwa_webhook_error=detail, openwa_retry_after=retry_after,
            openwa_has_key=has_openwa_key)

    def webhook_url(self, tenant_id: UUID) -> str | None:
        origin = self._settings.public_origin
        if not origin or not self._settings.openwa_webhook_secret:
            return None
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        return f"{origin.rstrip('/')}/api/v1/webhooks/openwa/{tenant_id}"

    def _shared_tenant(self, tenant_id: UUID) -> UUID:
        return self._settings.openwa_webhook_tenant_id or tenant_id

    async def save_ai(self, tenant_id: UUID, config: AISettings) -> IntegrationsView:
        shared_id = self._shared_tenant(tenant_id)
        saved = await self._repository.get(shared_id)
        changes: dict[str, str | None] = {"provider": config.provider, "model": config.model, "embedding_model": config.embedding_model}
        if config.provider == "ollama":
            if not self._ollama_url:
                raise ValueError("Configure o endereço do Ollama no servidor")
            changes["ai_key"] = None
        elif config.api_key:
            changes["ai_key"] = self._encrypt(config.api_key)
        elif saved.provider != config.provider or not saved.ai_key:
            if config.provider != "openai" or not self._settings.openai_api_key:
                raise ValueError("Informe a chave do provedor de IA")
            changes["ai_key"] = None
        if config.provider == "anthropic" and not (config.embedding_key or saved.embedding_key or self._settings.openai_api_key):
            raise ValueError("Informe uma chave OpenAI para os embeddings do RAG")
        if config.embedding_key:
            changes["embedding_key"] = self._encrypt(config.embedding_key)
        await self._repository.save(shared_id, changes)
        return await self.view(tenant_id)

    async def save_resend(self, tenant_id: UUID, config: ResendSettings) -> IntegrationsView:
        shared_id = self._shared_tenant(tenant_id)
        saved = await self._repository.get(shared_id)
        if not config.sender.strip() or not (config.api_key or saved.resend_key or self._settings.resend_api_key):
            raise ValueError("Informe o remetente verificado e a chave do Resend")
        changes: dict[str, str | None] = {"sender": config.sender.strip(), "test_recipient": config.recipient.strip()}
        if config.api_key:
            changes["resend_key"] = self._encrypt(config.api_key)
        await self._repository.save(shared_id, changes)
        return await self.view(tenant_id)

    async def save_openwa(self, tenant_id: UUID, config: OpenWASettings) -> IntegrationsView:
        shared_id = self._shared_tenant(tenant_id)
        saved = await self._repository.get(shared_id)
        current_url = saved.openwa_url or self._openwa_url
        endpoint = self._settings.normalize_openwa_url(config.base_url) if config.base_url else current_url
        if endpoint and endpoint not in self._openwa_allowed:
            raise ValueError("Este endereço OpenWA ainda não foi autorizado na implantação")
        if config.api_key:
            await self._repository.save(shared_id, {"openwa_url": endpoint, "openwa_key": self._encrypt(config.api_key),
                                                  "openwa_webhook_status": "pending", "openwa_webhook_error": None},
                                        reset_openwa_verification=True)
        elif endpoint != current_url or not (saved.openwa_key or self._settings.openwa_api_key):
            raise ValueError("Informe a chave do servidor OpenWA")
        return await self.view(tenant_id)

    def _ai(self, saved: StoredIntegrations) -> OpenAIClient | None:
        provider = saved.provider or "openai"
        key = self._decrypt(saved.ai_key) or (self._settings.openai_api_key if provider == "openai" else None)
        if (provider == "ollama" and not self._ollama_url) or (provider != "ollama" and not key):
            return None
        embedding_key = (self._decrypt(saved.embedding_key) or self._settings.openai_api_key) if provider == "anthropic" else None
        if provider == "anthropic" and embedding_key is None:
            return None
        return OpenAIClient(key, saved.model or self._settings.openai_model, provider=provider,
            embedding_key=embedding_key, embedding_model=saved.embedding_model or "nomic-embed-text", ollama_url=self._ollama_url)

    async def ai(self, tenant_id: UUID) -> OpenAIClient | None:
        try:
            return self._ai(await self._repository.get(self._shared_tenant(tenant_id)))
        except IntegrationUnavailable:
            return None

    async def ai_enabled(self, tenant_id: UUID) -> bool:
        return await self.ai(tenant_id) is not None

    async def handoff_email(self, tenant_id: UUID) -> str:
        local = await self._repository.get(tenant_id)
        return self._alert_recipient(tenant_id, local)

    async def save_handoff_email(self, tenant_id: UUID, email: str) -> None:
        await self._repository.save(tenant_id, {"alert_recipient": email})

    def _alert_recipient(self, tenant_id: UUID, local: StoredIntegrations) -> str:
        if local.alert_recipient is not None:
            return local.alert_recipient
        if tenant_id == self._shared_tenant(tenant_id):
            return (local.recipient if local.recipient is not None else self._settings.resend_to) or ""
        return ""

    def _test_recipient(self, saved: StoredIntegrations) -> str:
        if saved.test_recipient is not None:
            return saved.test_recipient
        return (saved.recipient if saved.recipient is not None else self._settings.resend_to) or ""

    async def resend(self, tenant_id: UUID, *, for_test: bool = False) -> ResendClient | None:
        shared_id = self._shared_tenant(tenant_id)
        saved = await self._repository.get(shared_id)
        try:
            key = self._decrypt(saved.resend_key) or self._settings.resend_api_key
        except IntegrationUnavailable:
            return None
        sender = saved.sender if saved.sender is not None else self._settings.resend_from
        if for_test:
            recipient = self._test_recipient(saved)
        else:
            local = saved if shared_id == tenant_id else await self._repository.get(tenant_id)
            recipient = self._alert_recipient(tenant_id, local)
        return ResendClient(key, sender, recipient or "") if key and sender else None

    async def openwa(self, tenant_id: UUID) -> OpenWAClient | None:
        shared_id = self._shared_tenant(tenant_id)
        saved = await self._repository.get(shared_id)
        endpoint = saved.openwa_url or self._openwa_url
        if endpoint is None or endpoint not in self._openwa_allowed:
            return None
        try:
            key = self._decrypt(saved.openwa_key) or (self._settings.openwa_api_key if endpoint == self._openwa_url else None)
        except IntegrationUnavailable:
            return None
        return OpenWAClient(endpoint, key, retry_until=saved.openwa_cooldowns.get(endpoint, 0),
                            defer=partial(self._repository.defer_openwa, shared_id, endpoint)) if key else None


def tenant_webhook_secret(root_tenant: UUID, tenant_id: UUID, secret: SecretStr) -> SecretStr:
    if tenant_id == root_tenant:
        return secret
    return SecretStr(digest(secret.get_secret_value().encode(), f"openwa:{tenant_id}".encode(), "sha256").hex())
