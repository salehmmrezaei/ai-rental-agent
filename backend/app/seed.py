"""Opt-in, atomic local demo data: python -m app.seed --demo.

Stable IDs reserve one versioned dataset. Reruns preserve edits and credentials;
partial datasets are rejected rather than silently repairing or deleting records.
"""
import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from getpass import getpass
import json
import os
import secrets
import sys
from uuid import UUID, uuid5

from faker import Faker
from dotenv import dotenv_values
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import (
    Amenity, Conversation, Listing, Message, Property, PropertyAmenity,
    RentalContract, RentalRequest, RentalUnit, SavedListing, User, Visit,
)
from app.security import hash_password
from app.repositories.inventory import today

NAMESPACE = UUID("d6e39157-c440-4c6e-9959-c7201979895f")
DEMO_EMAILS = {
    "admin": "demo.agency@example.com",
    "landlord": "demo.landlord@example.com",
    "tenant": "demo.tenant@example.com",
}
CITIES = (("Bologna", "40121"), ("Milan", "20121"),
          ("Rome", "00186"), ("Florence", "50122"))
AMENITIES = ("wifi", "furnished", "balcony", "elevator", "air conditioning")


class SeedError(ValueError):
    pass


def record_id(kind: str, index: int = 0):
    return uuid5(NAMESPACE, f"v1:{kind}:{index}")


def email_for(role: str, index: int = 0):
    return DEMO_EMAILS[role] if index == 0 else f"demo.{role}.{index:03d}@example.com"


def footprint():
    """All reserved records, including histories and account IDs."""
    return {
        User: [record_id("admin")] + [record_id("landlord", i) for i in range(100)]
              + [record_id("tenant", i) for i in range(200)],
        Property: [record_id("property", i) for i in range(300)],
        RentalUnit: [record_id("unit", i) for i in range(900)],
        Listing: [record_id("listing", i) for i in range(900)],
        RentalRequest: [record_id("request", i) for i in range(750)],
        RentalContract: [record_id("contract", i) for i in range(550)],
        Visit: [record_id("visit", i) for i in range(100)],
        Conversation: [record_id("conversation", i) for i in range(50)],
        Message: [record_id("message", i) for i in range(150)],
        SavedListing: [record_id("saved", i) for i in range(200)],
    }


def seed_demo(session: Session, password: str, *, as_of: date | None = None):
    """Caller owns the transaction. No commits, deletes or external side effects."""
    if not 12 <= len(password) <= 128:
        raise SeedError("Demo password must contain 12–128 characters")
    if session.get_bind().dialect.name != "postgresql":
        raise SeedError("Demo data requires migrated PostgreSQL")
    # Serialize concurrent invocations, including the existence check.
    session.execute(text("SELECT pg_advisory_xact_lock(6006001)"))
    expected = footprint()
    counts = {model.__tablename__: session.scalar(
        select(func.count()).select_from(model).where(model.id.in_(ids)))
        for model, ids in expected.items()}
    if any(counts.values()):
        if any(counts[model.__tablename__] != len(ids) for model, ids in expected.items()):
            raise SeedError("Incomplete demo dataset; use a fresh demo database. No records were changed")
        return {"created": False, "counts": counts}
    emails = [email_for("admin")] + [email_for("landlord", i) for i in range(100)] + [
        email_for("tenant", i) for i in range(200)]
    if session.scalar(select(User.id).where(User.email.in_(emails)).limit(1)):
        raise SeedError("Reserved demo email already exists; no records were changed")

    anchor = as_of or today()
    fake = Faker("it_IT")
    fake.seed_instance(6006)
    for role, size in (("admin", 1), ("landlord", 100), ("tenant", 200)):
        for i in range(size):
            # Only three documented accounts share the operator-selected password.
            # Bulk accounts have independent, discarded random credentials/salts.
            session.add(User(id=record_id(role, i), email=email_for(role, i), role=role,
                full_name=f"Demo {fake.name()}",
                password_hash=hash_password(password if i == 0 else secrets.token_urlsafe(32))))
    session.flush()
    amenities = []
    for i, name in enumerate(AMENITIES):
        item = session.scalar(select(Amenity).where(Amenity.name == name))
        if item is None:
            item = Amenity(id=record_id("amenity", i), name=name)
            session.add(item)
        amenities.append(item)
    session.flush()

    for i in range(300):
        city, postal = CITIES[i % 4]
        session.add(Property(id=record_id("property", i), landlord_id=record_id("landlord", i % 100),
            title=f"Demo {city} home {i + 1:03d}", city=city, postal_code=postal,
            address=f"Synthetic {fake.street_name()} {i + 1}", is_synthetic=True,
            description="Synthetic demonstration property. " + fake.random_element((
                "A furnished home with bright shared spaces and room to study.",
                "Comfortable rooms with a shared kitchen and a quiet workspace.",
                "A spacious apartment with a balcony and convenient amenities."))))
    session.flush()
    for i in range(300):
        for amenity in fake.random_elements(elements=amenities, length=3, unique=True):
            session.add(PropertyAmenity(property_id=record_id("property", i), amenity_id=amenity.id))
        room_rent = Decimal(fake.random_int(400, 950))
        for j, (kind, name) in enumerate((("apartment", "Entire apartment"), ("room", "Room A"), ("room", "Room B"))):
            rent = room_rent * 2 if j == 0 else room_rent + Decimal(j * 25)
            session.add(RentalUnit(id=record_id("unit", i * 3 + j), property_id=record_id("property", i),
                kind=kind, name=name, monthly_rent=rent, deposit=rent * 2,
                bedrooms=2 if j == 0 else 1, area_sqm=Decimal(80 if j == 0 else 18 + j)))
    session.flush()
    for i in range(300):
        status = "published" if i < 180 else ("draft", "submitted", "approved", "rejected", "unpublished")[i % 5]
        for j in range(3):
            session.add(Listing(id=record_id("listing", i * 3 + j), rental_unit_id=record_id("unit", i * 3 + j),
                status=status, available_from=anchor - timedelta(days=400),
                available_until=anchor + timedelta(days=730),
                review_note="Demo: please complete the property description." if status == "rejected" else None))
    session.flush()

    request_index = contract_index = 0
    for i in range(100):
        # Nonoverlapping whole-home/room histories, including back-to-back leases.
        histories = [(0, -360, -240, "completed", None), (1, -240, -120, "terminated", -180),
                     (0 if i % 2 == 0 else 1, -30, 30, "active", None),
                     (0, 30, 120, "confirmed", None), (0, 10, 60, "cancelled", None)]
        if i % 2:
            histories.append((2, -30, 30, "active", None))
        for j, start, end, status, terminated in histories:
            unit = session.get(RentalUnit, record_id("unit", i * 3 + j))
            tenant_index = i + 100 if j == 2 else i
            req = RentalRequest(id=record_id("request", request_index), tenant_id=record_id("tenant", tenant_index),
                rental_unit_id=unit.id, start_date=anchor + timedelta(days=start),
                end_date=anchor + timedelta(days=end), status="approved", note="Synthetic demo rental history")
            session.add(req)
            session.flush()  # The contract trigger requires the approved application.
            session.add(RentalContract(id=record_id("contract", contract_index), rental_request_id=req.id,
                tenant_id=req.tenant_id, rental_unit_id=unit.id, start_date=req.start_date,
                end_date=req.end_date, status=status, monthly_rent=unit.monthly_rent,
                terminated_on=anchor + timedelta(days=terminated) if terminated is not None else None))
            session.flush()  # Keep all existing conflict/identity triggers enabled.
            request_index += 1
            contract_index += 1
    for i in range(200):
        status = ("submitted", "reviewing", "rejected", "withdrawn")[i % 4]
        session.add(RentalRequest(id=record_id("request", request_index + i),
            tenant_id=record_id("tenant", i), rental_unit_id=record_id("unit", (i % 180) * 3 + 1),
            start_date=anchor + timedelta(days=150), end_date=anchor + timedelta(days=240),
            status=status, note="Synthetic request for a future stay",
            review_note="Demo: requested documents were missing." if status == "rejected" else None))

    midnight = datetime.combine(anchor, time(10), tzinfo=timezone.utc)
    for i in range(100):
        status = ("requested", "scheduled", "completed", "cancelled", "rejected")[i % 5]
        slot = midnight + timedelta(days=-7 if status == "completed" else 7, hours=i)
        scheduled = status in {"scheduled", "completed"}
        session.add(Visit(id=record_id("visit", i), tenant_id=record_id("tenant", i),
            rental_unit_id=record_id("unit", i * 3 + 1), requested_at=slot, status=status,
            scheduled_at=slot if scheduled else None,
            scheduled_end_at=slot + timedelta(minutes=30) if scheduled else None,
            assigned_admin_id=record_id("admin") if scheduled else None,
            note="Synthetic viewing request", agency_note="Demo schedule" if scheduled else None))
    for i in range(50):
        session.add(Conversation(id=record_id("conversation", i), tenant_id=record_id("tenant", i),
            subject=f"Demo viewing arrangements {i + 1:03d}"))
    session.flush()
    for i in range(50):
        for j, body in enumerate(("Hello, could you help arrange a viewing?",
                                  "The agency can help. Which day suits you?", "Thank you, next week works for me.")):
            session.add(Message(id=record_id("message", i * 3 + j), conversation_id=record_id("conversation", i),
                sender_id=record_id("admin") if j == 1 else record_id("tenant", i), body=body,
                created_at=midnight - timedelta(days=2) + timedelta(minutes=i * 3 + j),
                read_at=midnight - timedelta(days=1) if j == 0 else None))
    for i in range(200):
        session.add(SavedListing(id=record_id("saved", i), tenant_id=record_id("tenant", i),
            listing_id=record_id("listing", (i % 180) * 3 + 2)))
    session.flush()
    return {"created": True, "as_of": anchor.isoformat(),
            "counts": {model.__tablename__: len(ids) for model, ids in expected.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create synthetic rental demo data in a local development database")
    parser.add_argument("--demo", required=True, action="store_true", help="Explicitly opt into development demo accounts")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Anchor date; defaults to today's Europe/Rome date")
    parser.add_argument("--non-interactive", action="store_true", help="Require DEMO_PASSWORD rather than prompting")
    args = parser.parse_args()
    password = os.environ.get("DEMO_PASSWORD") or dotenv_values(".env").get("DEMO_PASSWORD")
    if not password:
        if args.non_interactive:
            print("Set DEMO_PASSWORD to a local demo password (12–128 characters)", file=sys.stderr)
            return 1
        password = getpass("Local demo password (12–128 characters): ")
        if password != getpass("Confirm demo password: "):
            print("Passwords do not match", file=sys.stderr)
            return 1
    try:
        with Session(get_engine()) as session, session.begin():
            result = seed_demo(session, password, as_of=args.as_of)
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Demo seed failed; transaction rolled back. Check migrations and database access", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    from app.demo_images import seed_demo_images
    try:
        with Session(get_engine()) as session, session.begin():
            photos = seed_demo_images(session)
    except (SeedError, SQLAlchemyError):
        print("Demo data is ready, but photo import failed. Rerun the demo seed to retry", file=sys.stderr)
        return 1
    print("Demo photos: " + json.dumps(photos))
    print("Demo accounts: " + ", ".join(DEMO_EMAILS.values()))
    if not result["created"]:
        print("Existing demo data preserved, including edits and original passwords")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
