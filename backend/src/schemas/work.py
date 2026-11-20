from typing import Literal
from uuid import UUID

from pydantic import BaseModel

WorkKind = Literal["whatsapp", "notify", "rag"]
WorkStatus = Literal["pending", "processing", "sent", "failed", "uncertain", "cancelled"]


class WorkItem(BaseModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID | None
    kind: WorkKind
    attempts: int


class WorkReceipt(BaseModel):
    id: UUID
    status: WorkStatus


class WhatsAppDispatch(BaseModel):
    status: Literal["sent", "failed", "uncertain", "pending"]
    provider_id: str | None = None
