from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.schemas.work import WorkStatus
from src.schemas.operators import Department

Queue = Literal["waiting", "bot", "mine", "assigned", "closed"]


class QueueCounts(BaseModel):
    waiting: int
    bot: int
    mine: int
    assigned: int | None
    closed: int | None


class SupportTicketInput(BaseModel):
    product: str | None
    details: str


class SupportTicket(SupportTicketInput):
    id: UUID
    closed_at: datetime | None


class ConversationSummary(BaseModel):
    id: UUID
    chat_id: str
    customer_name: str | None
    state: Literal["waiting", "bot", "assigned", "closed"]
    assigned_user_id: UUID | None
    last_interaction: datetime
    origin_name: str | None = None
    department: Department | None = None
    support_ticket: SupportTicket | None = None


class HistoryMessage(BaseModel):
    id: UUID
    sender_type: Literal["customer", "bot", "operator"]
    sender_id: UUID | None
    content: str
    created_at: datetime
    delivery_status: WorkStatus | None = None


class TransferRequest(BaseModel):
    user_id: UUID


class TransferNotice(BaseModel):
    id: UUID
    conversation_id: UUID


class SendTextRequest(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=4096, pattern=r"^[^\x00]+$")


class BotStateRequest(BaseModel):
    active: bool
