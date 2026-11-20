from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, StrictBool


class OpenWAEvent(BaseModel):
    event: str


class OpenWAMessage(BaseModel):
    id: str = Field(min_length=1, max_length=250, pattern=r"^[^\x00]+$")
    sender: str = Field(alias="from", max_length=100)
    from_me: StrictBool = Field(alias="fromMe")
    is_group: StrictBool = Field(default=False, alias="isGroup")
    has_media: StrictBool = Field(default=False, alias="hasMedia")
    body: str | None = Field(default=None, max_length=65_536, pattern=r"^[^\x00]*$")
    display_name: str | None = Field(default=None, max_length=150, pattern=r"^[^\x00]*$",
                                     validation_alias=AliasChoices("pushName", "notifyName"))


class OpenWAReceivedEvent(OpenWAEvent):
    session_id: UUID = Field(alias="sessionId")
    data: OpenWAMessage


class IncomingText(BaseModel):
    session_id: UUID
    message_id: str
    chat_id: str
    content: str
    display_name: str | None = None
