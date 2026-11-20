from pydantic import BaseModel, Field


class KnowledgeInput(BaseModel):
    source: str = Field(min_length=1, max_length=200, pattern=r"^[^\x00]+$")
    text: str = Field(min_length=1, max_length=40_000, pattern=r"^[^\x00]+$")


class KnowledgeSource(BaseModel):
    source: str
    chunks: int


class KnowledgeURL(BaseModel):
    source: str = Field(min_length=1, max_length=200, pattern=r"^[^\x00]+$")
    url: str = Field(min_length=1, max_length=2000)


class Answer(BaseModel):
    needs_human: bool
    answer: str


class BotContext(BaseModel):
    question: str
    name: str | None
    previous_summary: str | None
    recent: list[str]
    previous: list[str]
