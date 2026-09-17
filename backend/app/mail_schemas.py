from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, field_validator


class SendInput(BaseModel):
    mailbox_id: str
    draft_id: str
    revision: int = Field(ge=1)
    confirmed: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    mode: Literal["send", "test", "schedule"] = "send"
    scheduled_at: datetime | None = None
    reply_message_id: str | None = None
    attachments: list[dict] = Field(default_factory=list, max_length=5)

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Include a timezone in the scheduled time.")
        return value


class ConfirmInput(BaseModel):
    confirmed: Literal[True]


class MailboxUpdate(BaseModel):
    signature_html: str | None = Field(default=None, max_length=10000)
    timezone: str | None = Field(default=None, max_length=100)
    send_window_start: int | None = Field(default=None, ge=0, le=23)
    send_window_end: int | None = Field(default=None, ge=1, le=24)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Choose a valid IANA timezone, such as Asia/Shanghai.")
        return value


class MessageUpdate(BaseModel):
    is_unread: bool | None = None
    is_archived: bool | None = None


class ThreadUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=10000)
    intent: Literal["none", "interested", "not_now", "not_interested"] | None = None


class TaskInput(BaseModel):
    contact_id: str
    mailbox_id: str | None = None
    thread_id: str | None = None
    title: str = Field(min_length=1, max_length=250)
    notes: str = Field(default="", max_length=10000)
    due_at: datetime
    status: Literal["pending", "completed", "cancelled"] = "pending"

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Include a timezone in the due time.")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    notes: str | None = Field(default=None, max_length=10000)
    due_at: datetime | None = None
    status: Literal["pending", "completed", "cancelled"] | None = None

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Include a timezone in the due time.")
        return value


class SuppressionInput(BaseModel):
    contact_id: str
    reason: Literal["unsubscribe", "rejection", "hard_bounce", "manual"] = "manual"
    notes: str = Field(default="", max_length=10000)
