from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)]
Deposit = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False)]
Area = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2, allow_inf_nan=False)]
Kind = Literal['apartment', 'room']
ListingStatus = Literal['draft','submitted','approved','rejected','published','unpublished']
AmenityName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PropertyCreate(Input):
    title: Text = Field(max_length=200)
    description: Text = Field(max_length=10000)
    city: Text = Field(max_length=100)
    address: Text = Field(max_length=300)
    postal_code: str = Field(pattern=r'^\d{5}$')
    landlord_id: UUID | None = None
    is_synthetic: Literal[True] = True
    amenities: list[AmenityName] = Field(default_factory=list, max_length=20)

    @field_validator('amenities')
    @classmethod
    def normalize_amenities(cls, value): return sorted(set(v.lower() for v in value))


class Patch(Input):
    @model_validator(mode='after')
    def changes(self):
        if not self.model_fields_set: raise ValueError('Provide at least one changed field')
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in {'area_sqm', 'available_until'}:
                raise ValueError('Field cannot be null')
        return self


class PropertyPatch(Patch):
    title: Text | None = Field(default=None, max_length=200)
    description: Text | None = Field(default=None, max_length=10000)
    city: Text | None = Field(default=None, max_length=100)
    address: Text | None = Field(default=None, max_length=300)
    postal_code: str | None = Field(default=None, pattern=r'^\d{5}$')
    amenities: list[AmenityName] | None = Field(default=None, max_length=20)

    @field_validator('amenities')
    @classmethod
    def normalize_amenities(cls, value):
        return sorted(set(v.lower() for v in value)) if value is not None else value


class UnitCreate(Input):
    kind: Kind
    name: Text = Field(max_length=150)
    monthly_rent: Money
    deposit: Deposit = Decimal('0')
    bedrooms: int = Field(default=1, ge=1, le=30)
    area_sqm: Area | None = None


class UnitPatch(Patch):
    name: Text | None = Field(default=None, max_length=150)
    monthly_rent: Money | None = None
    deposit: Deposit | None = None
    bedrooms: int | None = Field(default=None, ge=1, le=30)
    area_sqm: Area | None = None


class ListingCreate(Input):
    available_from: date
    available_until: date | None = None

    @model_validator(mode='after')
    def interval(self):
        if self.available_until is not None and self.available_until <= self.available_from:
            raise ValueError('Availability end must follow start')
        return self


class ListingPatch(Patch):
    available_from: date | None = None
    available_until: date | None = None


class Moderation(Input):
    status: Literal['approved', 'rejected', 'published', 'unpublished']
    review_note: Text | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def rejection_reason(self):
        if self.status == 'rejected' and not self.review_note:
            raise ValueError('Rejection requires a review note')
        return self


class ImagePatch(Patch):
    alt_text: Text | None = Field(default=None, max_length=255)
    position: int | None = Field(default=None, ge=0, le=1000)


class ImageRead(BaseModel):
    id: UUID
    property_id: UUID
    rental_unit_id: UUID | None
    alt_text: str
    position: int
    url: str


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    rental_unit_id: UUID
    status: ListingStatus
    available_from: date
    available_until: date | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime


class UnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    property_id: UUID
    kind: Kind
    name: str
    monthly_rent: Decimal
    deposit: Decimal
    bedrooms: int
    area_sqm: Decimal | None
    occupancy_status: Literal['available', 'reserved', 'occupied']
    listing: ListingRead | None


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    landlord_id: UUID
    title: str
    description: str
    city: str
    address: str
    postal_code: str
    is_synthetic: bool
    amenities: list[str]
    created_at: datetime
    updated_at: datetime


class PropertyDetail(PropertyRead):
    units: list[UnitRead]
    images: list[ImageRead]


class PublicListing(BaseModel):
    id: UUID
    property_id: UUID
    rental_unit_id: UUID
    title: str
    description: str
    city: str
    address: str
    postal_code: str
    is_synthetic: bool
    kind: Kind
    unit_name: str
    monthly_rent: Decimal
    deposit: Decimal
    bedrooms: int
    area_sqm: Decimal | None
    amenities: list[str]
    images: list[ImageRead]
    available_from: date
    available_until: date | None
    available_now: bool


class Availability(BaseModel):
    listing_id: UUID
    start_date: date
    end_date: date
    available: bool
    reason: Literal['available', 'outside_listing_window', 'rental_conflict']


class Search(Input):
    city: Text | None = Field(default=None, max_length=100)
    property_type: Kind | None = None
    min_price: Deposit | None = None
    max_price: Deposit | None = None
    min_rooms: int | None = Field(default=None, ge=1, le=30)
    start_date: date | None = None
    end_date: date | None = None
    sort: Literal['newest','price_asc','price_desc'] = 'newest'
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode='after')
    def range_valid(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError('Provide both dates')
        if self.start_date and self.end_date <= self.start_date:
            raise ValueError('End must follow start')
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError('Minimum price exceeds maximum')
        return self


T = TypeVar('T')
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
