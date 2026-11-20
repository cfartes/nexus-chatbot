from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class LoginRequest(BaseModel):
    tenant_id: UUID
    email: str = Field(min_length=1, max_length=150)
    password: SecretStr = Field(min_length=1, max_length=128)


class Operator(BaseModel):
    tenant_id: UUID
    id: UUID
    name: str
    role: Literal["admin", "operator"]


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=12, max_length=128)


class LoginIdentity(Operator):
    password_hash: SecretStr
