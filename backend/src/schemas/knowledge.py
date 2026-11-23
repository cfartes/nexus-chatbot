from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from src.schemas.operators import Department


OriginSlug = Annotated[str, StringConstraints(max_length=50, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class ContactOrigin(BaseModel):
    slug: OriginSlug
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f\[\]]+$")]


class KnowledgeInput(BaseModel):
    source: str = Field(min_length=1, max_length=200, pattern=r"^[^\x00]+$")
    text: str = Field(min_length=1, max_length=40_000, pattern=r"^[^\x00]+$")


class KnowledgeSource(BaseModel):
    source: str
    chunks: int


class WelcomeMessage(BaseModel):
    message: str = Field(max_length=500, pattern=r"^[^\x00]*$")
    assistant_name: str | None = Field(default=None, max_length=80, pattern=r"^[^\x00-\x1f\x7f]*$")


class AssistantProfile(WelcomeMessage):
    company_name: str


class PreviewRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, pattern=r"^[^\x00]+$")


class PreviewResult(BaseModel):
    status: Literal["answered", "clarify", "handoff", "unavailable"]
    message: str
    sources: list[str]
    reason: str | None = None
    excerpts: list["KnowledgeMatch"] = Field(default_factory=list)
    department: Department | None = None


class KnowledgeMatch(BaseModel):
    source: str
    content: str


class KnowledgeURL(BaseModel):
    source: str = Field(min_length=1, max_length=200, pattern=r"^[^\x00]+$")
    url: str = Field(min_length=1, max_length=2000)


class Answer(BaseModel):
    needs_human: bool
    answer: str
    needs_clarification: bool = False


class BotContext(BaseModel):
    welcome_message: str
    question: str
    name: str | None
    previous_summary: str | None
    recent: list[str]
    previous: list[str]
    opening_pending: bool = False
    opening_question: str | None = None
    origin_slug: str | None = None
    origin_name: str | None = None
    local_hour: int = 0
    awaiting_department: bool = False
    company_name: str = ""
    assistant_name: str = ""


class OpeningUpdate(BaseModel):
    origin_slug: str | None
    pending_question: str | None = None
    customer_name: str | None = None
