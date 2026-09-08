from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


ConversationMessageRole = Literal[
    "user",
    "assistant",
]


class ConversationCreate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=200,
    )

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class ConversationMessageResponse(BaseModel):
    id: StrictInt
    role: ConversationMessageRole
    content: StrictStr
    created_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class ConversationSummary(BaseModel):
    id: StrictInt
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class ConversationDetail(BaseModel):
    id: StrictInt
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageResponse]

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    total: StrictInt
    limit: StrictInt
    offset: StrictInt

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )
