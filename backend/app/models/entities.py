from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, Numeric, String, Text, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, Record


def status_check(name, choices):
    return CheckConstraint("status IN (" + ",".join(repr(c) for c in choices.split()) + ")", name=name)


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20))
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    __table_args__ = (
        CheckConstraint("token_version >= 0", name="token_version"),
        CheckConstraint("role IN ('tenant','landlord','admin')", name="role"),
        CheckConstraint("email = lower(email)", name="email_normalized"),
        UniqueConstraint("id", "role"),
    )


class Property(Record, Base):
    __tablename__ = "properties"
    landlord_id: Mapped[UUID] = mapped_column(index=True)
    owner_role: Mapped[str] = mapped_column(String(20), default="landlord", server_default="landlord")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[str] = mapped_column(String(300))
    postal_code: Mapped[str] = mapped_column(String(10))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    booking_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    __table_args__ = (
        ForeignKeyConstraint(["landlord_id", "owner_role"], ["users.id", "users.role"], ondelete="RESTRICT"),
        CheckConstraint("owner_role = 'landlord'", name="owner_role"),
    )


class RentalUnit(Record, Base):
    __tablename__ = "rental_units"
    property_id: Mapped[UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(150))
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    bedrooms: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    __table_args__ = (
        CheckConstraint("kind IN ('apartment','room')", name="kind"),
        CheckConstraint("monthly_rent > 0 AND deposit >= 0", name="prices"),
        CheckConstraint("bedrooms > 0 AND (area_sqm IS NULL OR area_sqm > 0)", name="size"),
        UniqueConstraint("property_id", "name"), UniqueConstraint("id", "property_id"),
        Index("uq_one_apartment_per_property", "property_id", unique=True, postgresql_where=text("kind = 'apartment'")),
    )


class Listing(Record, Base):
    __tablename__ = "listings"
    rental_unit_id: Mapped[UUID] = mapped_column(ForeignKey("rental_units.id", ondelete="RESTRICT"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    available_from: Mapped[date] = mapped_column(Date)
    available_until: Mapped[date | None] = mapped_column(Date)
    review_note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (status_check("status", "draft submitted approved rejected published unpublished"),
        CheckConstraint("available_until IS NULL OR available_until > available_from", name="dates"))


class RentalRequest(Record, Base):
    __tablename__ = "rental_requests"
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    tenant_role: Mapped[str] = mapped_column(String(20), default="tenant", server_default="tenant")
    rental_unit_id: Mapped[UUID] = mapped_column(ForeignKey("rental_units.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="submitted", server_default="submitted", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tenant_role"], ["users.id", "users.role"], ondelete="RESTRICT"),
        CheckConstraint("tenant_role = 'tenant'", name="tenant_role"),
        CheckConstraint("end_date > start_date", name="dates"),
        status_check("status", "submitted reviewing approved rejected withdrawn"),
        UniqueConstraint("id", "tenant_id", "rental_unit_id", "start_date", "end_date"),
    )


class RentalContract(Record, Base):
    __tablename__ = "rental_contracts"
    rental_request_id: Mapped[UUID] = mapped_column(unique=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    rental_unit_id: Mapped[UUID] = mapped_column(ForeignKey("rental_units.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="confirmed", server_default="confirmed", index=True)
    __table_args__ = (
        ForeignKeyConstraint(["rental_request_id", "tenant_id", "rental_unit_id", "start_date", "end_date"],
            ["rental_requests.id", "rental_requests.tenant_id", "rental_requests.rental_unit_id", "rental_requests.start_date", "rental_requests.end_date"], ondelete="RESTRICT"),
        CheckConstraint("end_date > start_date", name="dates"),
        CheckConstraint("monthly_rent > 0", name="rent"),
        status_check("status", "confirmed active completed terminated cancelled"),
        Index("ix_contract_unit_dates", "rental_unit_id", "start_date", "end_date"),
    )


class Conversation(Record, Base):
    __tablename__ = "conversations"
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    tenant_role: Mapped[str] = mapped_column(String(20), default="tenant", server_default="tenant")
    subject: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tenant_role"], ["users.id", "users.role"], ondelete="RESTRICT"),
        CheckConstraint("tenant_role = 'tenant'", name="tenant_role"),
    )


class Message(Record, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="RESTRICT"), index=True)
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("length(trim(body)) BETWEEN 1 AND 10000", name="body"),)


class Visit(Record, Base):
    __tablename__ = "visits"
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    tenant_role: Mapped[str] = mapped_column(String(20), default="tenant", server_default="tenant")
    rental_unit_id: Mapped[UUID] = mapped_column(ForeignKey("rental_units.id", ondelete="RESTRICT"), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="requested", server_default="requested", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tenant_role"], ["users.id", "users.role"], ondelete="RESTRICT"),
        CheckConstraint("tenant_role = 'tenant'", name="tenant_role"),
        status_check("status", "requested scheduled completed cancelled rejected"),
        CheckConstraint("status NOT IN ('scheduled','completed') OR scheduled_at IS NOT NULL", name="schedule"),
    )


class PropertyImage(Record, Base):
    __tablename__ = "property_images"
    property_id: Mapped[UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    rental_unit_id: Mapped[UUID | None]
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    alt_text: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    __table_args__ = (
        ForeignKeyConstraint(["rental_unit_id", "property_id"], ["rental_units.id", "rental_units.property_id"], ondelete="RESTRICT"),
        CheckConstraint("position >= 0", name="position"),
    )


class Amenity(Record, Base):
    __tablename__ = "amenities"
    name: Mapped[str] = mapped_column(String(80), unique=True)


class PropertyAmenity(Base):
    __tablename__ = "property_amenities"
    property_id: Mapped[UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True)
    amenity_id: Mapped[UUID] = mapped_column(ForeignKey("amenities.id", ondelete="RESTRICT"), primary_key=True)


class SavedListing(Record, Base):
    __tablename__ = "saved_listings"
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    tenant_role: Mapped[str] = mapped_column(String(20), default="tenant", server_default="tenant")
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tenant_role"], ["users.id", "users.role"], ondelete="RESTRICT"),
        CheckConstraint("tenant_role = 'tenant'", name="tenant_role"),
        UniqueConstraint("tenant_id", "listing_id"),
    )
