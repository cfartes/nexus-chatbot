from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXUS_ATENDE_", hide_input_in_errors=True, env_ignore_empty=True)

    database_url: SecretStr | None = None
    public_origin: str | None = None
    openwa_base_url: str | None = None
    openwa_api_key: SecretStr | None = None
    openwa_webhook_tenant_id: UUID | None = None
    openwa_webhook_secret: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    resend_from: str | None = None
    resend_to: str | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    knowledge_url_origin: str | None = None

    def resend_credentials(self) -> tuple[SecretStr, str, str] | None:
        key, sender, recipient = self.resend_api_key, self.resend_from, self.resend_to
        if key is None and sender is None and recipient is None:
            return None
        if key is None or not key.get_secret_value() or not sender or not recipient:
            raise ValueError("Configure NEXUS_ATENDE_RESEND_API_KEY, RESEND_FROM and RESEND_TO together")
        return key, sender, recipient

    def webhook_credentials(self) -> tuple[UUID, SecretStr] | None:
        tenant_id, secret = self.openwa_webhook_tenant_id, self.openwa_webhook_secret
        if tenant_id is None and secret is None:
            return None
        if tenant_id is None or secret is None or len(secret.get_secret_value()) < 32:
            raise ValueError("Configure the OpenWA webhook tenant and a signing secret of at least 32 characters")
        return tenant_id, secret

    def openwa_credentials(self) -> tuple[str, SecretStr] | None:
        if self.openwa_base_url is None and self.openwa_api_key is None:
            return None
        if not self.openwa_base_url or not self.openwa_api_key or not self.openwa_api_key.get_secret_value():
            raise ValueError("Configure NEXUS_ATENDE_OPENWA_BASE_URL and NEXUS_ATENDE_OPENWA_API_KEY together")
        base_url = self.openwa_base_url.rstrip("/")
        url = urlsplit(base_url)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.path != "/api" or url.query or url.fragment):
            raise ValueError("NEXUS_ATENDE_OPENWA_BASE_URL must be an HTTPS URL ending in /api")
        return base_url, self.openwa_api_key

    def runtime_database_url(self) -> URL:
        if self.database_url is None:
            raise ValueError("NEXUS_ATENDE_DATABASE_URL is required")
        try:
            url = make_url(self.database_url.get_secret_value())
        except ArgumentError:
            raise ValueError("NEXUS_ATENDE_DATABASE_URL is invalid") from None
        if url.drivername != "postgresql+asyncpg":
            raise ValueError("NEXUS_ATENDE_DATABASE_URL must use postgresql+asyncpg")
        return url
