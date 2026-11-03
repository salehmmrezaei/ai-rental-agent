from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.inventory import Input, Text, ListingStatus
from app.schemas.operations import VisitStatus

ActionKind = Literal['save_listing', 'apply', 'request_visit', 'contact_agency', 'send_message',
    'withdraw_application', 'cancel_visit', 'create_property', 'update_property', 'create_unit',
    'update_unit', 'create_listing', 'update_listing', 'change_listing_status', 'review_application',
    'approve_application', 'reject_application', 'update_visit', 'send_tenant_message']


class ListingSearchContext(Input):
    message_id: UUID
    page: int = Field(ge=1, le=10000)


class ChatInput(Input):
    message: Text = Field(max_length=2000)
    thread_id: UUID | None = None
    listing_search_context: ListingSearchContext | None = None
    visit_search_context: ListingSearchContext | None = None

    @model_validator(mode="after")
    def context_requires_thread(self):
        if (self.listing_search_context is not None or self.visit_search_context is not None) and self.thread_id is None:
            raise ValueError("Search context requires a conversation")
        return self


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
    available_now: bool = False
    status: ListingStatus | None = None
    available_from: date | None = None
    available_until: date | None = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: ActionKind
    summary: str
    payload: dict
    status: Literal['pending', 'confirmed', 'cancelled']
    expires_at: datetime
    result: dict | None


class ListingSearchRead(BaseModel):
    page: int
    page_size: int
    total: int
    cards_only: bool


class VisitReference(BaseModel):
    id: UUID
    property_title: str
    unit_name: str
    tenant_name: str
    status: VisitStatus
    requested_at: datetime
    scheduled_at: datetime | None = None
    duration_minutes: int
    note: str | None = None


class VisitSearchRead(BaseModel):
    items: list[VisitReference]
    page: int
    page_size: int
    total: int
    cards_only: bool


class MessageRead(BaseModel):
    id: UUID
    role: Literal['user', 'assistant']
    content: str
    listings: list[ListingReference] = Field(default_factory=list)
    listing_search: ListingSearchRead | None = None
    visit_search: VisitSearchRead | None = None
    actions: list[ActionRead] = Field(default_factory=list)
    created_at: datetime


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    updated_at: datetime


class ThreadDetail(ThreadRead):
    messages: list[MessageRead]
