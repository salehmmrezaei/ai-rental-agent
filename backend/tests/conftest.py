import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.models.entities import User, Property, RentalUnit, RentalRequest, RentalContract


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a migrated, disposable PostgreSQL database ending in _test")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
        pytest.fail("Database tests require a disposable PostgreSQL database ending in _test")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def inventory(engine):
    # The suffix check above protects ordinary databases; this database is disposable.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users, properties, rental_units, listings, rental_requests, rental_contracts, conversations, messages, visits, property_images, amenities, property_amenities, saved_listings CASCADE"))
    with Session(engine) as s, s.begin():
        owner = User(email="landlord@example.test", password_hash="test-only-unusable-hash", full_name="Synthetic Owner", role="landlord")
        tenant = User(email="tenant@example.test", password_hash="test-only-unusable-hash", full_name="Synthetic Tenant", role="tenant")
        admin = User(email="admin@example.test", password_hash="test-only-unusable-hash", full_name="Synthetic Agent", role="admin")
        other = User(email="other@example.test", password_hash="test-only-unusable-hash", full_name="Synthetic Other Tenant", role="tenant")
        s.add_all([owner, tenant, admin, other]); s.flush()
        p = Property(landlord_id=owner.id, title="Synthetic Bologna apartment", description="Development fixture", city="Bologna", address="Synthetic Via Esempio 10", postal_code="40121")
        s.add(p); s.flush()
        units = [RentalUnit(property_id=p.id, kind=k, name=n, monthly_rent=Decimal(r)) for k,n,r in [('apartment','Entire apartment','1500'),('room','Room A','650'),('room','Room B','600')]]
        s.add_all(units); s.flush()
        return dict(owner=owner.id, tenant=tenant.id, other=other.id, admin=admin.id, property=p.id, apartment=units[0].id, room=units[1].id, room_b=units[2].id)


def application(s, data, unit="room", start=date(2027,1,1), end=date(2027,3,1), status="approved"):
    req = RentalRequest(tenant_id=data['tenant'], rental_unit_id=data[unit], start_date=start, end_date=end, status=status)
    s.add(req); s.flush()
    return req.id


def contract(s, data, request_id, unit="room", start=date(2027,1,1), end=date(2027,3,1), status="confirmed"):
    c = RentalContract(rental_request_id=request_id, tenant_id=data['tenant'], rental_unit_id=data[unit], start_date=start, end_date=end, monthly_rent=650, status=status)
    s.add(c); s.flush()
    return c.id
