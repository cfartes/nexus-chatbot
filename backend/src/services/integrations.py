from urllib.parse import urlsplit
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from src.repositories.integrations import IntegrationRepository, StoredIntegrations
from src.schemas.integrations import AISettings, IntegrationsView, ResendSettings
from src.services.openai import OpenAIClient
from src.services.openwa import OpenWAClient
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
        saved = await self._repository.get(tenant_id)
        return IntegrationsView(provider=saved.provider or "openai", model=saved.model or self._settings.openai_model,
            embedding_model=saved.embedding_model or "nomic-embed-text",
            ai_has_key=bool(saved.ai_key or (saved.provider in (None, "openai") and self._settings.openai_api_key)),
            embedding_has_key=bool(saved.embedding_key or self._settings.openai_api_key), ollama_url=self._ollama_url,
            resend_sender=saved.sender if saved.sender is not None else self._settings.resend_from or "",
            resend_recipient=saved.recipient if saved.recipient is not None else self._settings.resend_to or "",
            resend_has_key=bool(saved.resend_key or self._settings.resend_api_key), openwa_url=self._openwa_url,
            openwa_webhook_url=f"{self._settings.public_origin}/api/v1/webhooks/openwa/{tenant_id}"
                if self._settings.public_origin and self._settings.openwa_webhook_tenant_id == tenant_id else None,
            openwa_has_key=bool(saved.openwa_key or self._settings.openwa_api_key))

    async def save_ai(self, tenant_id: UUID, config: AISettings) -> IntegrationsView:
        saved = await self._repository.get(tenant_id)
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
        await self._repository.save(tenant_id, changes)
        return await self.view(tenant_id)

    async def save_resend(self, tenant_id: UUID, config: ResendSettings) -> IntegrationsView:
        saved = await self._repository.get(tenant_id)
        if not config.sender.strip() or not (config.api_key or saved.resend_key or self._settings.resend_api_key):
            raise ValueError("Informe o remetente verificado e a chave do Resend")
        changes: dict[str, str | None] = {"sender": config.sender.strip(), "recipient": config.recipient.strip()}
        if config.api_key:
            changes["resend_key"] = self._encrypt(config.api_key)
        await self._repository.save(tenant_id, changes)
        return await self.view(tenant_id)

    async def save_openwa(self, tenant_id: UUID, key: SecretStr) -> IntegrationsView:
        await self._repository.save(tenant_id, {"openwa_key": self._encrypt(key)})
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
            return self._ai(await self._repository.get(tenant_id))
        except IntegrationUnavailable:
            return None

    async def ai_enabled(self, tenant_id: UUID) -> bool:
        return await self.ai(tenant_id) is not None

    async def resend(self, tenant_id: UUID) -> ResendClient | None:
        saved = await self._repository.get(tenant_id)
        try:
            key = self._decrypt(saved.resend_key) or self._settings.resend_api_key
        except IntegrationUnavailable:
            return None
        sender = saved.sender if saved.sender is not None else self._settings.resend_from
        recipient = saved.recipient if saved.recipient is not None else self._settings.resend_to
        return ResendClient(key, sender, recipient or "") if key and sender else None

    async def openwa(self, tenant_id: UUID) -> OpenWAClient | None:
        saved = await self._repository.get(tenant_id)
        try:
            key = self._decrypt(saved.openwa_key) or self._settings.openwa_api_key
        except IntegrationUnavailable:
            return None
        return OpenWAClient(self._openwa_url, key) if self._openwa_url and key else None
