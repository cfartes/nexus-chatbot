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


class ClientCreate(ClientName):
    admin: OperatorCreate


class ClientChoice(ClientName):
    id: UUID


class ClientRecord(ClientChoice):
    archived_at: datetime | None = None
    admin_invite_pending: bool = False


class ClientInvite(ClientRecord):
    invite_error: str | None = None
