from uuid import UUID

from pydantic import BaseModel, Field


class WhatsAppConnection(BaseModel):
    session_id: UUID | None = None
    status: str
    phone_number: str | None = None


class WhatsAppQR(BaseModel):
    qr_code: str | None = None


class OpenWASession(BaseModel):
    status: str = Field(min_length=1, max_length=32)


class OpenWAQR(BaseModel):
    qrCode: str | None = Field(default=None, max_length=800_000)
