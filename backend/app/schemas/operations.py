from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.inventory import Input, Text, Money, PublicListing

ApplicationStatus = Literal['submitted','reviewing','approved','rejected','withdrawn']
ContractStatus = Literal['confirmed','active','completed','terminated','cancelled']
VisitStatus = Literal['requested','scheduled','completed','cancelled','rejected']


class ApplicationCreate(Input):
    listing_id: UUID
    start_date: date
    end_date: date
    note: Text | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def dates(self):
        if self.end_date <= self.start_date: raise ValueError('End must follow start')
        return self


class Approval(Input):
    monthly_rent: Money | None = None


class ContractCreate(Approval):
    application_id: UUID


class Decision(Input):
    review_note: Text = Field(max_length=2000)


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    rental_unit_id: UUID
    start_date: date
    end_date: date
    status: ApplicationStatus
    note: str | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime


class ContractUpdate(Input):
    status: ContractStatus | None = None
    monthly_rent: Money | None = None
    terminated_on: date | None = None

    @model_validator(mode='after')
    def changes(self):
        if not self.model_fields_set: raise ValueError('Provide a change')
        if any(getattr(self,k) is None for k in self.model_fields_set): raise ValueError('Changes cannot be null')
        if self.status == 'terminated' and self.terminated_on is None: raise ValueError('Termination date required')
        if self.terminated_on is not None and self.status != 'terminated': raise ValueError('Termination requires terminated status')
        if self.monthly_rent is not None and self.status not in {None,'confirmed'}: raise ValueError('Change rent separately before activation')
        return self


class ContractOwner(BaseModel):
    id: UUID
    rental_unit_id: UUID
    property_id: UUID
    property_title: str
    unit_name: str
    start_date: date
    end_date: date
    terminated_on: date | None
    effective_end_date: date
    monthly_rent: Decimal
    status: ContractStatus
    created_at: datetime
    updated_at: datetime


class ContractPrivate(ContractOwner):
    tenant_id: UUID
    rental_request_id: UUID


class VisitCreate(Input):
    listing_id: UUID
    requested_at: AwareDatetime
    note: Text | None = Field(default=None,max_length=2000)

    @field_validator('requested_at')
    @classmethod
    def utc(cls,value): return value.astimezone(timezone.utc)


class VisitUpdate(Input):
    status: Literal['scheduled','completed','cancelled','rejected']
    scheduled_at: AwareDatetime | None = None
    duration_minutes: int | None = Field(default=None,ge=1,le=180)
    assigned_admin_id: UUID | None = None
    agency_note: Text | None = Field(default=None,max_length=2000)

    @field_validator('scheduled_at')
    @classmethod
    def utc(cls,value): return value.astimezone(timezone.utc) if value else value

    @model_validator(mode='after')
    def fields(self):
        if any(getattr(self,k) is None for k in self.model_fields_set): raise ValueError('Fields cannot be null')
        if self.status != 'scheduled' and {'scheduled_at','duration_minutes','assigned_admin_id'} & self.model_fields_set:
            raise ValueError('Scheduling fields require scheduled status')
        if self.status == 'rejected' and not self.agency_note: raise ValueError('Rejection note required')
        return self


class VisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    rental_unit_id: UUID
    requested_at: datetime
    scheduled_at: datetime | None
    scheduled_end_at: datetime | None
    duration_minutes: int
    status: VisitStatus
    note: str | None
    agency_note: str | None
    created_at: datetime
    updated_at: datetime


class AgencyVisitRead(VisitRead):
    assigned_admin_id: UUID | None


class ConversationCreate(Input):
    subject: Text = Field(max_length=200)
    initial_message: Text = Field(max_length=10000)


class MessageCreate(Input):
    body: Text = Field(max_length=10000)


class MessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_type: Literal['tenant','agency']
    body: str
    read_at: datetime | None
    created_at: datetime


class ConversationRead(BaseModel):
    id: UUID
    tenant_id: UUID
    subject: str
    unread_count: int
    created_at: datetime
    updated_at: datetime


class ReadResult(BaseModel):
    updated: int


class AdminUserUpdate(Input):
    full_name: Text | None = Field(default=None,max_length=150)
    email: str | None = Field(default=None,max_length=254)
    is_active: bool | None = Field(default=None,strict=True)

    @model_validator(mode='after')
    def changes(self):
        if not self.model_fields_set or any(getattr(self,k) is None for k in self.model_fields_set):
            raise ValueError('Provide nonnull changes')
        return self

    @field_validator('email')
    @classmethod
    def email_valid(cls,value):
        from pydantic import TypeAdapter, EmailStr
        return str(TypeAdapter(EmailStr).validate_python(value.strip().lower())) if value else value


class OccupancyProperty(BaseModel):
    property_id: UUID
    title: str
    city: str
    total_units: int
    occupied_units: int
    reserved_units: int
    available_units: int
    occupancy_percent: Decimal
    contracted_monthly_rent: Decimal


class OccupancySummary(BaseModel):
    as_of: date
    properties: int
    total_units: int
    occupied_units: int
    reserved_units: int
    available_units: int
    occupancy_percent: Decimal
    contracted_monthly_rent: Decimal


class OccupancyReport(BaseModel):
    summary: OccupancySummary
    items: list[OccupancyProperty]
    total: int
    page: int
    page_size: int


class DashboardStatistics(BaseModel):
    role: Literal['tenant','landlord','admin']
    counts: dict[str,int]
    occupancy: OccupancySummary | None = None


class SavedCreate(Input):
    listing_id: UUID


class SavedRead(BaseModel):
    id: UUID
    listing_id: UUID
    created_at: datetime

class SavedDetail(SavedRead):
    listing: PublicListing | None
