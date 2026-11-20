from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class OperatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")
    email: str = Field(min_length=3, max_length=150, pattern=r"^[^\s\x00@]+@[^\s\x00@]+$")


class OperatorUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")
    is_active: bool


class OperatorRecord(BaseModel):
    id: UUID
    name: str
    email: str
    is_active: bool
    invite_pending: bool = False
    invite_sent: bool | None = None
    invite_error: str | None = None


class AcceptInvite(BaseModel):
    token: SecretStr = Field(min_length=80, max_length=80)
    password: SecretStr = Field(min_length=12, max_length=128)
