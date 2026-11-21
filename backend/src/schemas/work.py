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
    recipient_user_id: UUID | None = None


class WorkReceipt(BaseModel):
    id: UUID
    status: WorkStatus


class EmailNotice(BaseModel):
    customer_name: str
    started_local: str
    recipient: str | None


class WhatsAppDispatch(BaseModel):
    status: Literal["sent", "failed", "uncertain", "pending"]
    provider_id: str | None = None
    retry_after: int | None = None
