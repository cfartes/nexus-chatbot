from typing import Literal

from pydantic import BaseModel, Field, SecretStr

Provider = Literal["openai", "gemini", "anthropic", "ollama"]


class AISettings(BaseModel):
    provider: Provider = "openai"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:/-]+$")
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=1000)
    embedding_key: SecretStr | None = Field(default=None, min_length=1, max_length=1000)
    embedding_model: str = Field(default="nomic-embed-text", min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:/-]+$")


class ResendSettings(BaseModel):
    sender: str = Field(max_length=200, pattern=r"^[^\r\n\x00]*$")
    recipient: str = Field(default="", max_length=150, pattern=r"^([^\s\x00@]+@[^\s\x00@]+)?$")
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=1000)


class OpenWASettings(BaseModel):
    api_key: SecretStr = Field(min_length=1, max_length=1000)


class IntegrationsView(BaseModel):
    provider: Provider
    model: str
    embedding_model: str
    ai_has_key: bool
    embedding_has_key: bool
    ollama_url: str | None
    resend_sender: str
    resend_recipient: str
    resend_has_key: bool
    openwa_url: str | None
    openwa_webhook_url: str | None
    openwa_has_key: bool
