from uuid import UUID

from pydantic import BaseModel


class TenantConnection(BaseModel):
    id: UUID
    phone_number: str | None
    openwa_session_id: UUID | None
