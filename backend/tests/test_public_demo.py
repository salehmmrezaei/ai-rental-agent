"""Public demo safety through the real application boundary and PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.main import create_app
from app.models import User, Property, AssistantThread
from app.public_demo import get_demo_store, validate_demo_dataset
from app.seed import seed_demo, record_id
from app.demo_images import seed_demo_images
from app.security import create_token
from app.services.simulated_assistant import reset_demo_state


@pytest.fixture(scope="module")
def public_dataset(engine):
    with Session(engine) as db, db.begin():
        db.execute(text("TRUNCATE users, properties, rental_units, listings, rental_requests, rental_contracts, conversations, messages, visits, property_images, amenities, property_amenities, saved_listings CASCADE"))
        seed_demo(db, "Public-demo-tests-only-password")
        seed_demo_images(db)


@pytest.fixture
def public_api(engine, public_dataset, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(engine.url))
    monkeypatch.setenv("JWT_SECRET", "public-demo-test-signing-key-at-least-32-bytes")
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_ACCESS_RATE_LIMIT", "100")
    monkeypatch.setenv("ASSISTANT_RATE_LIMIT", "100")
    # Even an accidentally injected provider key must never enable live inference.
    monkeypatch.setenv("OPENAI_API_KEY", "accidental-key-must-never-be-used")
    get_settings.cache_clear()
    get_demo_store().clear()
    reset_demo_state()
    app = create_app()
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_session] = session
    @app.post("/api/v1/future-write")
    def future_write():
        pytest.fail("Default-deny policy must protect future write routes")
    with TestClient(app) as client:
        yield client
    get_demo_store().clear()
    reset_demo_state()
    get_settings.cache_clear()


def enter(client, role="tenant"):
    response = client.post("/api/v1/demo/access", json={"role": role})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_personas_and_role_isolation(public_api):
    status = public_api.get("/api/v1/demo/status").json()
    assert status["enabled"] and status["read_only"] and status["assistant_mode"] == "simulated"
    for role in ("tenant", "landlord", "admin"):
        headers = enter(public_api, role)
        assert public_api.get("/api/v1/users/me", headers=headers).json()["role"] == role
        assert public_api.get("/api/v1/dashboard/statistics", headers=headers).status_code == 200
        directory = public_api.get("/api/v1/admin/users", headers=headers)
        assert directory.status_code == (200 if role == "admin" else 403)
    assert public_api.post("/api/v1/demo/access", json={"role": "superadmin"}).status_code == 422
    assert public_api.post("/api/v1/demo/access", json={"role": "admin", "user_id": str(uuid4())}).status_code == 422


def test_every_registered_write_route_is_blocked_before_validation(public_api):
    headers = enter(public_api, "admin")
    checked = set()
    allowed = {"/api/v1/demo/access", "/api/v1/auth/logout", "/api/v1/assistant/chat"}
    for template, operations in public_api.app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", str(uuid4()), template)
        if path in allowed:
            continue
        for method in {name.upper() for name in operations} & {"POST", "PUT", "PATCH", "DELETE"}:
            response = public_api.request(method, path, headers=headers, content=b"not even valid json")
            assert response.status_code == 403, (method, path, response.text)
            assert response.json()["error"]["code"] == "demo_read_only"
            checked.add((method, path))
    assert len(checked) >= 35
    assert public_api.post("/api/v1/auth/register/").status_code == 403
    assert public_api.post("/api/v1/properties/anything/images", content=b"x" * 200000).status_code == 403
    assert public_api.request("TRACE", "/api/v1/listings").status_code == 403


def test_public_browsing_images_and_private_history(public_api, engine, monkeypatch):
    from app.services import rental_agent
    def no_provider(*args, **kwargs):
        pytest.fail("Public demo must never invoke external inference")
    monkeypatch.setattr(rental_agent, "run_agent", no_provider)
    monkeypatch.setattr(rental_agent, "AsyncOpenAI", no_provider)
    listing = public_api.get("/api/v1/listings", params={"city": "Bologna", "page_size": 1})
    assert listing.status_code == 200 and listing.json()["total"] > 0
    detail = public_api.get("/api/v1/listings/" + listing.json()["items"][0]["id"]).json()
    assert detail["images"]
    image = public_api.get(detail["images"][0]["url"])
    assert image.status_code == 200 and image.headers["content-type"].startswith("image/")
    one, two = enter(public_api), enter(public_api)
    chat = public_api.post("/api/v1/assistant/chat", headers=one, json={"message": "Find rooms in Bologna under €700"})
    assert chat.status_code == 200, chat.text
    thread = chat.json()
    assert "Simulated" in thread["messages"][-1]["content"]
    assert public_api.get("/api/v1/assistant/threads/" + thread["id"], headers=two).status_code == 404
    assert public_api.get("/api/v1/assistant/threads", headers=two).json() == []
    assert public_api.post("/api/v1/assistant/chat", headers=two,
                           json={"message": "show more", "thread_id": thread["id"]}).status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AssistantThread)) == 0


def test_logout_and_reset_only_discard_disposable_state(public_api, engine):
    one, two = enter(public_api), enter(public_api)
    with Session(engine) as db:
        original = db.get(User, record_id("tenant")).token_version
        count = db.scalar(select(func.count()).select_from(Property))
    assert public_api.post("/api/v1/auth/logout", headers=one).status_code == 204
    assert public_api.get("/api/v1/users/me", headers=one).status_code == 401
    assert public_api.get("/api/v1/users/me", headers=two).status_code == 200
    get_demo_store().clear()  # Equivalent to a backend restart; no SQL deletion.
    assert public_api.get("/api/v1/users/me", headers=two).status_code == 401
    with Session(engine) as db:
        assert db.get(User, record_id("tenant")).token_version == original
        assert db.scalar(select(func.count()).select_from(Property)) == count


def test_regular_tokens_are_rejected_in_public_mode(public_api, engine):
    with Session(engine) as db:
        token, _ = create_token(db.get(User, record_id("admin")))
    assert public_api.get("/api/v1/admin/users", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert public_api.get("/docs").status_code == 404
    assert public_api.get("/openapi.json").status_code == 404
    assert public_api.post("/api/v1/assistant/chat", content=b"x" * 16385).status_code == 413


def test_dataset_check_refuses_unrelated_data_without_deleting_it(public_api, engine):
    from app.errors import ApiError
    with Session(engine) as db, db.begin():
        user = User(email="unrelated@example.com", full_name="Unrelated", role="tenant", password_hash="unusable")
        db.add(user)
        db.flush()
        with pytest.raises(ApiError, match="dedicated synthetic"):
            validate_demo_dataset(db)
        assert db.get(User, user.id) is user
        db.rollback()


def test_repeated_concurrent_visitors_cannot_mutate_shared_data(public_api, engine):
    def visit(index):
        headers = enter(public_api, ("tenant", "landlord", "admin")[index % 3])
        assert public_api.post("/api/v1/properties", headers=headers, json={}).status_code == 403
        response = public_api.post("/api/v1/assistant/chat", headers=headers, json={"message": "Give me an overview"})
        assert response.status_code == 200, response.text
        return response.json()["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(visit, range(8)))
    assert len(set(ids)) == 8
    with Session(engine) as db:
        validate_demo_dataset(db)
        assert db.scalar(select(func.count()).select_from(AssistantThread)) == 0


def test_demo_tokens_and_access_are_disabled_in_normal_mode(public_api, monkeypatch):
    headers = enter(public_api)
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "false")
    get_settings.cache_clear()
    app = create_app()
    # Reuse only the database override; real authentication remains enabled.
    app.dependency_overrides[get_session] = public_api.app.dependency_overrides[get_session]
    with TestClient(app) as client:
        assert client.get("/api/v1/demo/status").json()["enabled"] is False
        assert client.post("/api/v1/demo/access", json={"role": "tenant"}).status_code == 404
        assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_demo_access_is_rate_limited(public_api):
    public_api.app.state.demo_access_throttle.limit = 1
    enter(public_api)
    response = public_api.post("/api/v1/demo/access", json={"role": "tenant"})
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0


def test_anonymous_browsing_fails_closed_for_mixed_database(public_api, engine, monkeypatch):
    import app.database
    monkeypatch.setattr(app.database, "get_engine", lambda: engine)
    with Session(engine) as db, db.begin():
        outsider = User(email="synthetic.unrelated@example.com", full_name="Unrelated record",
                        role="tenant", password_hash="unusable")
        db.add(outsider)
        db.flush()
        outsider_id = outsider.id
    try:
        with TestClient(create_app()) as strict:
            response = strict.get("/api/v1/listings")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "demo_dataset_required"
        with Session(engine) as db:
            assert db.get(User, outsider_id) is not None
    finally:
        with Session(engine) as db, db.begin():
            db.delete(db.get(User, outsider_id))


def test_read_limits_cover_readiness_and_blocked_ips_do_not_consume_global_capacity(public_api):
    from fastapi import FastAPI
    from app.public_demo import PublicDemoPolicy
    app = FastAPI()
    @app.get("/api/v1/health/ready")
    def ready():
        return {"status": "ok"}
    @app.get("/api/v1/health/live")
    def live():
        return {"status": "ok"}
    policy = PublicDemoPolicy(app)
    policy.by_ip.limit = 1
    policy.global_requests.limit = 2
    with TestClient(policy, client=("one", 1234)) as one:
        assert one.get("/api/v1/health/ready").status_code == 200
        for _ in range(5):
            assert one.get("/api/v1/health/ready").status_code == 429
        assert one.get("/api/v1/health/live").status_code == 200
    with TestClient(policy, client=("two", 1234)) as two:
        assert two.get("/api/v1/health/ready").status_code == 200
    with TestClient(policy, client=("three", 1234)) as three:
        assert three.get("/api/v1/health/ready").status_code == 429
