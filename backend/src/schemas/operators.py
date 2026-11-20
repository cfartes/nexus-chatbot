from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class OperatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")
    email: str = Field(min_length=3, max_length=150, pattern=r"^[^\s\x00@]+@[^\s\x00@]+$")
    password: SecretStr = Field(min_length=12, max_length=128)


class OperatorUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$")
    is_active: bool
    password: SecretStr | None = Field(default=None, min_length=12, max_length=128)


class OperatorRecord(BaseModel):
    id: UUID
    name: str
    email: str
    is_active: bool
