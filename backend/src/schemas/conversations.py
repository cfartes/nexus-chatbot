from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.schemas.work import WorkStatus

Queue = Literal["waiting", "bot", "mine", "assigned"]


class ConversationSummary(BaseModel):
    id: UUID
    chat_id: str
    customer_name: str | None
    state: Literal["waiting", "bot", "assigned"]
    assigned_user_id: UUID | None
    last_interaction: datetime
    origin_name: str | None = None


class HistoryMessage(BaseModel):
    id: UUID
    sender_type: Literal["customer", "bot", "operator"]
    sender_id: UUID | None
    content: str
    created_at: datetime
    delivery_status: WorkStatus | None = None


class TransferRequest(BaseModel):
    user_id: UUID


class SendTextRequest(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=4096, pattern=r"^[^\x00]+$")


class BotStateRequest(BaseModel):
    active: bool
