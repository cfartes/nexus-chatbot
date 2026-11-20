from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from src.schemas.operators import OperatorCreate


class TenantConnection(BaseModel):
    id: UUID
    phone_number: str | None
    openwa_session_id: UUID | None
    openwa_number_verified: bool


class ClientName(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")


class ClientDetails(BaseModel):
    address: str = Field(default="", max_length=400, pattern=r"^[^\x00]*$")
    document: str = Field(default="", max_length=24, pattern=r"^[0-9A-Za-z./ -]*$")
    contact_phone: str = Field(default="", max_length=32, pattern=r"^[0-9+ ().-]*$")
    contact_email: str = Field(default="", max_length=150, pattern=r"^([^\s\x00@]+@[^\s\x00@]+)?$")


class ClientCreate(ClientName):
    admin: OperatorCreate
    details: ClientDetails


class ClientUpdate(ClientName):
    details: ClientDetails | None = None


class ClientChoice(ClientName):
    id: UUID


class ClientRecord(ClientChoice):
    archived_at: datetime | None = None
    admin_invite_pending: bool = False
    details: ClientDetails = Field(default_factory=ClientDetails)


class ClientInvite(ClientRecord):
    invite_error: str | None = None
