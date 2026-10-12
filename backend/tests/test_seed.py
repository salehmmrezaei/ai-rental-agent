"""Verify the complete dataset with real PostgreSQL constraints and API reads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import threading

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.main import create_app
from app.models import (
    Conversation, Listing, Message, Property, PropertyAmenity, RentalContract,
    RentalRequest, RentalUnit, SavedListing, User, Visit,
)
from app.repositories.inventory import today
from app.security import verify_password
from app.seed import DEMO_EMAILS, SeedError, email_for, record_id, seed_demo

PASSWORD = "Phase6-local-test-password"
TRUNCATE = "TRUNCATE users, properties, rental_units, listings, rental_requests, rental_contracts, conversations, messages, visits, property_images, amenities, property_amenities, saved_listings CASCADE"


@pytest.fixture(scope="module")
def seeded(engine):
    anchor = today()
    with Session(engine) as session, session.begin():
        session.execute(text(TRUNCATE))
        # An unrelated user must survive and shared amenities may already exist.
        session.add(User(email="unrelated@example.com", full_name="Unrelated User",
                         role="tenant", password_hash="unusable-test-hash"))
        result = seed_demo(session, PASSWORD, as_of=anchor)
    return anchor, result


def test_full_dataset_and_valid_histories(engine, seeded):
    anchor, result = seeded
    assert result["created"] and result["as_of"] == anchor.isoformat()
    with Session(engine) as s:
        assert dict(s.execute(select(User.role, func.count()).group_by(User.role)).all()) == {
            "admin": 1, "landlord": 100, "tenant": 201}
        assert dict(s.execute(select(Property.city, func.count()).group_by(Property.city)).all()) == {
            "Bologna": 75, "Milan": 75, "Rome": 75, "Florence": 75}
        assert s.scalar(select(func.count()).select_from(Property).where(Property.is_synthetic.is_(False))) == 0
        assert all(p.address.startswith("Synthetic ") for p in s.scalars(select(Property)))
        assert all(u.email.endswith("@example.com") for u in s.scalars(select(User)))
        assert s.scalar(select(func.count()).select_from(RentalUnit)) == 900
        assert s.scalar(select(func.count()).select_from(Listing).where(Listing.status == "published")) == 540
        assert s.scalar(select(func.count()).select_from(PropertyAmenity)) == 900
        assert s.scalar(select(func.count()).select_from(RentalRequest)) == 750
        assert dict(s.execute(select(RentalContract.status, func.count()).group_by(RentalContract.status)).all()) == {
            "active": 150, "completed": 100, "terminated": 100, "confirmed": 100, "cancelled": 100}
        assert s.scalar(select(func.count()).select_from(Visit)) == 100
        assert s.scalar(select(func.count()).select_from(SavedListing)) == 200
        assert s.scalar(select(func.count()).select_from(Conversation)) == 50
        assert s.scalar(select(func.count()).select_from(Message)) == 150
        # Independently query the physical property conflict invariant, including
        # effective termination, historical intervals and whole-apartment bookings.
        assert s.scalar(text("""SELECT count(*) FROM rental_contracts a
            JOIN rental_units ua ON ua.id=a.rental_unit_id
            JOIN rental_units ub ON ub.property_id=ua.property_id
            JOIN rental_contracts b ON b.rental_unit_id=ub.id
            WHERE a.id < b.id AND a.status <> 'cancelled' AND b.status <> 'cancelled'
            AND daterange(a.start_date,coalesce(a.terminated_on,a.end_date),'[)')
             && daterange(b.start_date,coalesce(b.terminated_on,b.end_date),'[)')
            AND (ua.id=ub.id OR ua.kind='apartment' OR ub.kind='apartment')""")) == 0
        assert s.scalar(text("""SELECT count(*) FROM rental_contracts c
            JOIN rental_requests r ON r.id=c.rental_request_id
            WHERE r.status <> 'approved' OR (c.tenant_id,c.rental_unit_id,c.start_date,c.end_date)
                IS DISTINCT FROM (r.tenant_id,r.rental_unit_id,r.start_date,r.end_date)""")) == 0
        assert s.scalar(select(func.count()).select_from(RentalContract).where(
            RentalContract.status == "active", RentalContract.start_date <= anchor,
            RentalContract.end_date > anchor)) == 150


def test_demo_passwords_and_private_bulk_credentials(engine, seeded):
    with Session(engine) as s:
        hashes = []
        for role, email in DEMO_EMAILS.items():
            user = s.scalar(select(User).where(User.email == email))
            assert user.role == role and user.is_active
            assert verify_password(PASSWORD, user.password_hash)
            hashes.append(user.password_hash)
        assert len(set(hashes)) == 3
        bulk = s.scalar(select(User).where(User.email == email_for("tenant", 1)))
        assert bulk.password_hash.startswith("$argon2id$")
        assert not verify_password(PASSWORD, bulk.password_hash)


def test_rerun_preserves_edits_and_does_not_rotate_passwords(engine, seeded):
    with Session(engine) as s, s.begin():
        owner = s.get(User, record_id("landlord"))
        original_hash = owner.password_hash
        owner.full_name = "Edited Demo Owner"
        result = seed_demo(s, "A-different-local-password", as_of=date(2030, 1, 1))
        assert result["created"] is False
        assert owner.full_name == "Edited Demo Owner" and owner.password_hash == original_hash
        assert s.get(Listing, record_id("listing")).available_from == seeded[0] - timedelta(days=400)
        s.rollback()


def test_partial_dataset_refuses_repair(engine, seeded):
    with Session(engine) as s, s.begin():
        s.delete(s.get(SavedListing, record_id("saved")))
        s.flush()
        with pytest.raises(SeedError, match="Incomplete"):
            seed_demo(s, PASSWORD)
        assert s.get(SavedListing, record_id("saved")) is None
        s.rollback()


def test_reserved_email_collision_preserves_existing_user(engine, seeded):
    with Session(engine) as s, s.begin():
        # PostgreSQL TRUNCATE is transactional; rollback restores the shared fixture.
        s.execute(text(TRUNCATE))
        existing = User(email=DEMO_EMAILS["admin"], full_name="Existing Tenant",
                        role="tenant", password_hash="original")
        s.add(existing)
        s.flush()
        with pytest.raises(SeedError, match="Reserved demo email"):
            seed_demo(s, PASSWORD)
        assert existing.role == "tenant" and existing.password_hash == "original"
        assert s.scalar(select(func.count()).select_from(User)) == 1
        s.rollback()


@pytest.mark.parametrize("password", ["", "short", "x" * 129])
def test_invalid_password_changes_nothing(engine, seeded, password):
    with Session(engine) as s, s.begin():
        with pytest.raises(SeedError, match="12–128"):
            seed_demo(s, password)
        assert s.scalar(select(func.count()).select_from(User)) == 302


def test_seed_failure_is_atomic(engine, seeded, monkeypatch):
    import app.seed as module
    class InjectedFailure(RuntimeError):
        pass
    def fail_after_users(*args, **kwargs):
        raise InjectedFailure()
    # Fault injection skips expensive hashes and fails after users were flushed.
    monkeypatch.setattr(module, "hash_password", lambda _: "fault-injection-only")
    monkeypatch.setattr(module.Faker, "street_name", fail_after_users, raising=False)
    with Session(engine) as s:
        with pytest.raises(InjectedFailure), s.begin():
            s.execute(text(TRUNCATE))
            seed_demo(s, PASSWORD)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 302
        assert s.scalar(select(func.count()).select_from(Property)) == 300


def test_concurrent_invocations_wait_then_preserve_dataset(engine, seeded):
    started = threading.Event()
    def rerun():
        with Session(engine) as s, s.begin():
            started.set()
            return seed_demo(s, PASSWORD)
    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as lock:
        lock.begin()
        lock.execute(text("SELECT pg_advisory_xact_lock(6006001)"))
        future = pool.submit(rerun)
        assert started.wait(5)
        # Confirm actual lock contention via PostgreSQL rather than a timing guess.
        blocked = False
        for _ in range(100):
            if lock.scalar(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND objid = 6006001")):
                blocked = True
                break
            lock.execute(text("SELECT pg_sleep(0.02)"))
        lock.commit()
        result = future.result(timeout=10)
        assert blocked and result["created"] is False


def test_seeded_accounts_search_and_scoped_dashboards(engine, seeded, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")
    monkeypatch.setenv("JWT_SECRET", "phase6-test-signing-key-at-least-32-bytes")
    monkeypatch.setenv("AUTH_RATE_LIMIT", "100")
    get_settings.cache_clear()
    app = create_app()
    def database():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = database
    try:
        with TestClient(app) as client:
            public = client.get("/api/v1/listings?city=Milan&page_size=100")
            assert public.status_code == 200 and public.json()["total"] == 135
            assert "password" not in public.text and "landlord_id" not in public.text
            for role, email in DEMO_EMAILS.items():
                login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
                assert login.status_code == 200 and login.json()["user"]["role"] == role
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                assert client.get("/api/v1/dashboard/statistics", headers=headers).status_code == 200
                if role == "landlord":
                    properties = client.get("/api/v1/properties", headers=headers).json()
                    assert properties["total"] == 3
                    contracts = client.get("/api/v1/contracts", headers=headers)
                    assert contracts.status_code == 200 and "tenant_id" not in contracts.text
                if role == "tenant":
                    for route in ("applications", "contracts", "visits", "conversations", "saved-listings"):
                        response = client.get(f"/api/v1/{route}", headers=headers)
                        assert response.status_code == 200 and response.json()["total"] > 0
                    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    finally:
        get_settings.cache_clear()
