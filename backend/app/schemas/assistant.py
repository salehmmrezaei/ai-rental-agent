from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.inventory import Input, Text

ActionKind = Literal['save_listing', 'apply', 'request_visit', 'contact_agency', 'send_message', 'withdraw_application', 'cancel_visit']


class ChatInput(Input):
    message: Text = Field(max_length=2000)
    thread_id: UUID | None = None


class Confirmation(Input):
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if not value:
            raise ValueError("Explicit confirmation required")
        return value


class AssistantStatus(BaseModel):
    available: bool
    message: str


class ListingReference(BaseModel):
    id: UUID
    title: str
    city: str
    kind: str
    unit_name: str
    monthly_rent: str
    available_now: bool


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: ActionKind
    summary: str
    payload: dict
    status: Literal['pending', 'confirmed', 'cancelled']
    expires_at: datetime
    result: dict | None


class MessageRead(BaseModel):
    id: UUID
    role: Literal['user', 'assistant']
    content: str
    listings: list[ListingReference] = Field(default_factory=list)
    actions: list[ActionRead] = Field(default_factory=list)
    created_at: datetime


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    updated_at: datetime


class ThreadDetail(ThreadRead):
    messages: list[MessageRead]
