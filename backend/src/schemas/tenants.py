from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from src.schemas.operators import OperatorCreate


class TenantConnection(BaseModel):
    id: UUID
    phone_number: str | None
    openwa_session_id: UUID | None
    openwa_number_verified: bool


class ClientName(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")


PostalCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{5}-?[0-9]{3}$")]


class PostalAddress(BaseModel):
    postal_code: str = Field(default="", pattern=r"^([0-9]{5}-?[0-9]{3})?$")
    street: str = Field(default="", max_length=180, pattern=r"^[^\x00-\x1f]*$")
    neighborhood: str = Field(default="", max_length=120, pattern=r"^[^\x00-\x1f]*$")
    city: str = Field(default="", max_length=120, pattern=r"^[^\x00-\x1f]*$")
    state: str = Field(default="", pattern=r"^([A-Z]{2})?$")


class ClientDetails(PostalAddress):
    address: str = Field(default="", max_length=400, pattern=r"^[^\x00]*$")
    number: str = Field(default="", max_length=24, pattern=r"^[^\x00-\x1f]*$")
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
