"""The public simulator uses real scoped reads and never invokes a model or writes."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import current_user
from app.errors import ApiError, install_error_handlers
from app.models import Listing, Property, RentalRequest, RentalUnit, User, Visit
from app.repositories.inventory import today
from app.routers import assistant as router_module
from app.schemas.assistant import ChatInput
from app.services import rental_agent, simulated_assistant as simulator
from app.throttle import AuthThrottle

BASE = "/api/v1/assistant"


@pytest.fixture(autouse=True)
def disposable_history():
    simulator.reset_demo_state()
    yield
    simulator.reset_demo_state()


@pytest.fixture
def demo_api(engine, inventory, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The public demo must never construct or run a live model")

    monkeypatch.setattr(rental_agent, "run_agent", forbidden)
    monkeypatch.setattr(rental_agent, "AsyncOpenAI", forbidden)
    # A key may accidentally exist in the environment; simulation must take priority.
    monkeypatch.setattr(router_module, "get_settings", lambda: SimpleNamespace(
        public_demo_mode=True, openai_api_key="an-accidental-key", assistant_available=forbidden))
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1")
    app.state.assistant_throttle = AuthThrottle(100)
    install_error_handlers(app)

    def database():
        with Session(engine) as session:
            yield session

    def visitor(x_demo_visitor: str = Header(default="visitor-one"), x_demo_role: str = Header(default="tenant")):
        role = {"tenant": "tenant", "landlord": "owner", "admin": "admin"}[x_demo_role]
        with Session(engine) as session:
            user = session.get(User, inventory[role])
            user.demo_session_id = x_demo_visitor
            return user

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[current_user] = visitor
    with Session(engine) as session, session.begin():
        for index in range(8):
            unit = RentalUnit(property_id=inventory["property"], kind="room", name=f"Demo room {index}",
                              monthly_rent=500 + index * 10)
            session.add(unit)
            session.flush()
            session.add(Listing(rental_unit_id=unit.id, status="published", available_from=today() - timedelta(days=1)))
    with TestClient(app) as client:
        yield client


def send(client, message, *, thread_id=None, visitor="visitor-one", role="tenant", **extra):
    return client.post(BASE + "/chat", headers={"X-Demo-Visitor": visitor, "X-Demo-Role": role},
                       json={"message": message, "thread_id": thread_id, **extra})


def test_no_key_status_search_and_paging_use_only_reads(demo_api, engine):
    statements = []

    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement.strip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        status = demo_api.get(BASE + "/status")
        assert status.status_code == 200
        assert status.json()["available"] is True
        assert status.json()["mode"] == "simulated"
        response = send(demo_api, "Find rooms in Bologna under €600")
        assert response.status_code == 200, response.text
        thread = response.json()
        message = thread["messages"][-1]
        assert "Simulated AI Assistant" in message["content"]
        assert message["listing_search"]["total"] == 8
        assert message["listing_search"]["cards_only"] is False
        assert len(message["listings"]) == 6
        assert message["actions"] == []
        page = demo_api.get(f"{BASE}/threads/{thread['id']}/messages/{message['id']}/listings?page=2")
        assert page.status_code == 200
        assert len(page.json()["items"]) == 2
        assert not ({"INSERT", "UPDATE", "DELETE", "TRUNCATE"} & set(statements))
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_shared_persona_history_and_search_context_remain_visitor_private(demo_api):
    thread = send(demo_api, "Find rooms in Bologna").json()
    message = thread["messages"][-1]
    other = {"X-Demo-Visitor": "visitor-two"}
    assert demo_api.get(BASE + "/threads", headers=other).json() == []
    assert demo_api.get(f"{BASE}/threads/{thread['id']}", headers=other).status_code == 404
    assert demo_api.get(f"{BASE}/threads/{thread['id']}/messages/{message['id']}/listings", headers=other).status_code == 404
    assert send(demo_api, "Show my applications", thread_id=thread["id"], visitor="visitor-two").status_code == 404
    forged = send(demo_api, "Find rooms", thread_id=thread["id"],
        listing_search_context={"message_id": str(uuid4()), "page": 1})
    assert forged.status_code == 404
    assert demo_api.get(f"{BASE}/threads/{thread['id']}").json() == thread


@pytest.mark.parametrize("role,message", [
    ("tenant", "Apply for the first room and send a message"),
    ("landlord", "Create a property and publish its listing"),
    ("admin", "Approve the application and schedule the visit"),
])
def test_write_requests_have_explanations_without_actions(demo_api, role, message):
    response = send(demo_api, message, role=role)
    assert response.status_code == 200
    answer = response.json()["messages"][-1]
    assert "read-only" in answer["content"]
    assert "No action was prepared or performed" in answer["content"]
    assert answer["actions"] == []
    confirmation = demo_api.post(f"{BASE}/actions/{uuid4()}/confirm", json={"confirmed": True})
    assert confirmation.status_code == 403


def test_landlord_scope_and_agency_views(demo_api, engine, inventory):
    with Session(engine) as session, session.begin():
        stranger = User(email="unrelated.synthetic@example.com", full_name="Another Owner", role="landlord", password_hash="unusable")
        session.add(stranger)
        session.flush()
        session.add(Property(landlord_id=stranger.id, title="Private Other Portfolio", description="Synthetic",
                             city="Rome", address="Synthetic Via 1", postal_code="00186"))
    owner = send(demo_api, "Show my properties", role="landlord")
    assert owner.status_code == 200
    assert "Synthetic Bologna apartment" in owner.text
    assert "Private Other Portfolio" not in owner.text
    report = send(demo_api, "Give me an occupancy report", role="landlord")
    assert "Contracted monthly rent" in report.text
    agency = send(demo_api, "Show properties", role="admin")
    assert "Private Other Portfolio" in agency.text
    assert demo_api.get(BASE + "/threads", headers={"X-Demo-Role": "tenant"}).json() == []


def test_invalid_dates_and_unsupported_requests_explain_boundaries(demo_api):
    response = send(demo_api, "Find rooms in Bologna from 2027-05-01 to 2027-01-01")
    assert response.status_code == 200
    assert "two ISO dates" in response.text
    assert response.json()["messages"][-1]["listings"] == []
    unsupported = send(demo_api, "Write a legal opinion about my tenancy")
    assert "bounded set" in unsupported.text
    assert "Simulated AI Assistant" in unsupported.text


def test_pending_agency_applications_include_both_pending_states(demo_api, engine, inventory):
    with Session(engine) as db, db.begin():
        for state in ("submitted", "reviewing", "approved"):
            db.add(RentalRequest(tenant_id=inventory["tenant"], rental_unit_id=inventory["room"],
                status=state, start_date=today() + timedelta(days=30), end_date=today() + timedelta(days=90)))
    response = send(demo_api, "Show pending applications", role="admin")
    assert response.status_code == 200
    content = response.json()["messages"][-1]["content"]
    assert "2 matching records" in content
    assert "submitted" in content and "reviewing" in content
    assert "approved" not in content


def test_agency_visit_cards_and_pages_are_private(demo_api, engine, inventory):
    with Session(engine) as db, db.begin():
        db.add(Visit(tenant_id=inventory["tenant"], rental_unit_id=inventory["room"],
                     requested_at=datetime.now(timezone.utc) + timedelta(days=1), note="Synthetic visit note"))
    response = send(demo_api, "Show requested visits", role="admin")
    assert response.status_code == 200
    thread = response.json()
    message = thread["messages"][-1]
    assert message["visit_search"]["total"] == 1
    assert message["visit_search"]["items"][0]["tenant_name"] == "Synthetic Tenant"
    path = f"{BASE}/threads/{thread['id']}/messages/{message['id']}/visits"
    assert demo_api.get(path, headers={"X-Demo-Role": "admin"}).status_code == 200
    assert demo_api.get(path, headers={"X-Demo-Role": "admin", "X-Demo-Visitor": "other"}).status_code == 404
    assert demo_api.get(path).status_code == 403


def test_explanatory_workflows_remain_available_without_mutation():
    user = SimpleNamespace(id=uuid4(), role="landlord", demo_session_id="explain")
    thread = simulator.chat(None, user, ChatInput(message="Explain how to publish a listing"))
    assert "agency reviews and publishes" in thread.messages[-1].content
    assert thread.messages[-1].actions == []


def test_history_is_bounded_expiring_and_cleared_on_logout(monkeypatch):
    clock = [0]
    monkeypatch.setattr(simulator, "monotonic", lambda: clock[0])
    user = SimpleNamespace(id=uuid4(), role="tenant", demo_session_id="private-session")
    first = simulator.chat(None, user, ChatInput(message="Hello"))
    for _ in range(simulator.MAX_THREADS_PER_SESSION):
        simulator.chat(None, user, ChatInput(message="Hello again"))
    assert len(simulator.threads(None, user)) == simulator.MAX_THREADS_PER_SESSION
    with pytest.raises(ApiError) as evicted:
        simulator.thread_detail(None, user, first.id)
    assert evicted.value.status_code == 404
    simulator.discard_demo_session(user.demo_session_id)
    assert simulator.threads(None, user) == []
    last = simulator.chat(None, user, ChatInput(message="Hello"))
    clock[0] += simulator.TTL_SECONDS + 1
    with pytest.raises(ApiError) as expired:
        simulator.thread_detail(None, user, last.id)
    assert expired.value.status_code == 404
    assert not simulator._search_filters


def test_thread_turn_limit_and_missing_session_cannot_be_bypassed():
    user = SimpleNamespace(id=uuid4(), role="tenant", demo_session_id="one")
    thread = simulator.chat(None, user, ChatInput(message="Hello"))
    for _ in range(simulator.MAX_TURNS - 1):
        simulator.chat(None, user, ChatInput(message="Hello", thread_id=thread.id))
    with pytest.raises(ApiError) as limit:
        simulator.chat(None, user, ChatInput(message="Hello", thread_id=thread.id))
    assert limit.value.code == "chat_limit"
    with pytest.raises(ApiError) as unauthenticated:
        simulator.chat(None, SimpleNamespace(id=uuid4(), role="tenant"), ChatInput(message="Hello"))
    assert unauthenticated.value.status_code == 401


def test_concurrent_turns_preserve_one_complete_reply(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="tenant", demo_session_id="concurrent")
    thread = simulator.chat(None, user, ChatInput(message="Hello"))
    barrier = Barrier(2)
    original = simulator._respond

    def simultaneous(*args):
        barrier.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(simulator, "_respond", simultaneous)

    def send_turn():
        try:
            simulator.chat(None, user, ChatInput(message="Hello again", thread_id=thread.id))
            return 200
        except ApiError as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: send_turn(), range(2))) == [200, 409]
    assert len(simulator.thread_detail(None, user, thread.id).messages) == 4


def test_logout_during_reply_cannot_recreate_discarded_history(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="tenant", demo_session_id="logging-out")
    original = simulator._respond

    def discard_while_reading(*args):
        simulator.discard_demo_session(user.demo_session_id)
        return original(*args)

    monkeypatch.setattr(simulator, "_respond", discard_while_reading)
    with pytest.raises(ApiError) as discarded:
        simulator.chat(None, user, ChatInput(message="Hello"))
    assert discarded.value.code == "demo_history_reset"
    assert simulator.threads(None, user) == []
    assert not simulator._search_filters
