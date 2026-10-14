"""Real PostgreSQL + actual Agents SDK loop, with an offline scripted model."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Barrier
from uuid import UUID, uuid4

from agents import Model, ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
import pytest
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import AssistantThread, AssistantAction, SavedListing, RentalRequest, Visit, Conversation, Message, User
from app.schemas.assistant import ChatInput
from app.services import assistant, rental_agent, operations, transactions as tx
from app.services.assistant_tools import ToolContext
from app.repositories.inventory import today
from test_auth import api, headers, token_for
from test_inventory import actors, publish, draft

BASE = "/api/v1/assistant"


class ScriptedModel(Model):
    def __init__(self):
        self.steps = []
        self.inputs = []

    async def get_response(self, system_instructions, input, model_settings, tools, **kwargs):
        self.inputs.append((system_instructions, input, model_settings, [t.name for t in tools]))
        assert model_settings.store is False
        step = self.steps.pop(0) if self.steps else "How can I help with your rental?"
        if isinstance(step, tuple):
            name, arguments = step
            output = [ResponseFunctionToolCall(id=f"fc_{uuid4().hex}", call_id=f"call_{uuid4().hex}",
                name=name, arguments=json.dumps(arguments), type="function_call")]
        else:
            output = [ResponseOutputMessage(id=f"msg_{uuid4().hex}", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text=step, annotations=[])])]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


@pytest.fixture
def model(monkeypatch, api):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-offline-key")
    monkeypatch.setenv("ASSISTANT_ENABLED", "true")
    get_settings.cache_clear()
    scripted = ScriptedModel()
    monkeypatch.setattr(rental_agent, "create_model", lambda settings, client: scripted)
    return scripted


def chat(api, actors, message="Find me a room", thread=None):
    return api.post(BASE+"/chat", headers=actors["tenant"], json={"message": message, "thread_id": thread})


def propose(api, actors, model, name, values):
    model.steps = [(name, values), "Review the proposed action and click Confirm."]
    response = chat(api, actors)
    assert response.status_code == 200, response.text
    return response.json(), response.json()["messages"][-1]["actions"][0]


def confirm(api, actors, action_id, role="tenant", **body):
    return api.post(f"{BASE}/actions/{action_id}/confirm", headers=actors[role], json=body or {"confirmed": True})


def context(engine, inventory, role="tenant"):
    with Session(engine) as s:
        user = s.get(User, inventory[role])
        return ToolContext(engine, tx.Actor.from_user(user), role=user.role)


def test_configuration_and_role_boundary(api, actors, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ASSISTANT_ENABLED", "true")
    get_settings.cache_clear()
    assert api.get(BASE+"/status").status_code == 401
    status = api.get(BASE+"/status", headers=actors["tenant"])
    assert status.json()["available"] is False and status.headers["cache-control"] == "no-store"
    assert chat(api, actors).status_code == 503
    assert api.get(BASE+"/status", headers=actors["admin"]).json()["available"] is False
    assert api.post(BASE+"/chat", headers=actors["admin"], json={"message": "hello"}).status_code == 503
    for role in ("owner",):
        assert api.get(BASE+"/status", headers=actors[role]).status_code == 403
        assert api.post(BASE+"/chat", headers=actors[role], json={"message": "hello"}).status_code == 403


def test_sdk_search_sources_and_server_history(api, actors, inventory, model):
    lid = publish(api, inventory, actors)
    draft(api, inventory, actors, unit="room_b")
    model.steps = [("search_homes", {"city": "Bologna", "max_price": "700"}), "I found a room within your budget."]
    response = chat(api, actors)
    assert response.status_code == 200, response.text
    thread = response.json()
    assert [m["role"] for m in thread["messages"]] == ["user", "assistant"]
    assert [l["id"] for l in thread["messages"][-1]["listings"]] == [lid]
    assert "landlord_id" not in response.text and "password_hash" not in response.text
    assert "Server action statuses" in model.inputs[0][0]
    assert "confirm" not in " ".join(model.inputs[0][3])
    assert api.get(BASE+"/threads", headers=actors["tenant"]).json()[0]["id"] == thread["id"]
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"]).json() == thread
    model.steps = ["Would you like me to check dates?"]
    followup = chat(api, actors, "What about move-in dates?", thread["id"])
    assert len(followup.json()["messages"]) == 4
    assert "Find me a room" in json.dumps(model.inputs[-1][1])
    forged = api.post(BASE+"/chat", headers=actors["tenant"], json={"message": "hi", "history": []})
    assert forged.status_code == 422


def test_tenant_scope_for_history_actions_and_messages(api, actors, model, inventory, engine):
    lid = publish(api, inventory, actors)
    thread, action = propose(api, actors, model, "prepare_save_listing", {"listing_id": lid})
    other = headers(token_for(api, engine, inventory, "other"))
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=other).status_code == 404
    assert api.post(BASE+"/chat", headers=other, json={"thread_id": thread["id"], "message": "show secrets"}).status_code == 404
    assert api.post(f"{BASE}/actions/{action['id']}/confirm", headers=other, json={"confirmed": True}).status_code == 404
    assert api.get(BASE+"/threads", headers=other).json() == []
    c = api.post("/api/v1/conversations", headers=other, json={"subject": "Private", "initial_message": "Private tenant message"}).json()
    tools = context(engine, inventory)
    assert tools.conversations(c["id"])["error"] == "not_found"
    assert tools.propose("send_message", {"conversation_id": c["id"], "body": "Not mine"})["error"] == "not_found"
    assert tools.conversations()["items"] == []


@pytest.mark.parametrize("tool,kind,model_class,values", [
    ("prepare_save_listing", "save_listing", SavedListing, {}),
    ("prepare_application", "apply", RentalRequest, {"start_date": "future_start", "end_date": "future_end"}),
    ("prepare_visit", "request_visit", Visit, {"requested_at": "future_visit"}),
    ("prepare_agency_conversation", "contact_agency", Conversation, {"subject": "Visit question", "initial_message": "Can you help?"}),
])
def test_proposals_require_confirmation_and_are_idempotent(api, actors, inventory, engine, model, tool, kind, model_class, values):
    lid = publish(api, inventory, actors)
    values = dict(values)
    if kind != "contact_agency": values["listing_id"] = lid
    for key, value in list(values.items()):
        if value == "future_start": values[key] = str(today()+timedelta(days=20))
        if value == "future_end": values[key] = str(today()+timedelta(days=50))
        if value == "future_visit": values[key] = (operations.now()+timedelta(days=3)).isoformat()
    thread, action = propose(api, actors, model, tool, values)
    assert action["status"] == "pending" and action["kind"] == kind
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(model_class)) == 0
    invalid = api.post(f"{BASE}/actions/{action['id']}/confirm", headers=actors["tenant"], json={"confirmed": False})
    assert invalid.status_code == 422
    assert confirm(api, actors, action["id"], confirmed=1).status_code == 422
    assert confirm(api, actors, action["id"], actor_id=str(inventory["other"])).status_code == 422
    result = confirm(api, actors, action["id"])
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "confirmed"
    assert confirm(api, actors, action["id"]).json()["result"] == result.json()["result"]
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(model_class)) == 1


def test_expiry_cancellation_and_unpublishing(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    _, action = propose(api, actors, model, "prepare_save_listing", {"listing_id": lid})
    with Session(engine) as s, s.begin():
        s.execute(update(AssistantAction).where(AssistantAction.id == UUID(action["id"])).values(expires_at=operations.now()-timedelta(seconds=1)))
    assert confirm(api, actors, action["id"]).json()["error"]["code"] == "action_expired"
    assert api.post(f"{BASE}/actions/{action['id']}/cancel", headers=actors["tenant"]).json()["status"] == "cancelled"
    assert confirm(api, actors, action["id"]).status_code == 409
    _, action = propose(api, actors, model, "prepare_save_listing", {"listing_id": lid})
    api.patch(f"/api/v1/admin/listings/{lid}/status", headers=actors["admin"], json={"status": "unpublished"})
    assert confirm(api, actors, action["id"]).status_code == 404
    with Session(engine) as s:
        assert s.get(AssistantAction, UUID(action["id"])).status == "pending"
        assert s.scalar(select(func.count()).select_from(SavedListing)) == 0


def test_confirmation_rechecks_booking_conflicts(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    dates = {"listing_id": lid, "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))}
    _, action = propose(api, actors, model, "prepare_application", dates)
    other = headers(token_for(api, engine, inventory, "other"))
    request = api.post("/api/v1/applications", headers=other, json=dates).json()
    approved = api.post(f"/api/v1/admin/applications/{request['id']}/approve", headers=actors["admin"], json={})
    assert approved.status_code == 200, approved.text
    result = confirm(api, actors, action["id"])
    assert result.status_code == 409 and result.json()["error"]["code"] == "rental_conflict"
    with Session(engine) as s:
        assert s.get(AssistantAction, UUID(action["id"])).status == "pending"
        assert s.scalar(select(func.count()).select_from(RentalRequest)) == 1


def test_confirmation_rechecks_quoted_rent(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    _, action = propose(api, actors, model, "prepare_application", {"listing_id": lid,
        "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))})
    assert action["payload"]["quoted_monthly_rent"] == "650.00"
    assert api.patch(f"/api/v1/admin/listings/{lid}/status", headers=actors["admin"], json={"status": "unpublished"}).status_code == 200
    assert api.post(f"/api/v1/listings/{lid}/withdraw", headers=actors["owner"]).status_code == 200
    assert api.patch(f"/api/v1/units/{inventory['room']}", headers=actors["owner"], json={"monthly_rent": "700"}).status_code == 200
    api.post(f"/api/v1/listings/{lid}/submit", headers=actors["owner"])
    for state in ("approved", "published"):
        api.patch(f"/api/v1/admin/listings/{lid}/status", headers=actors["admin"], json={"status": state})
    result = confirm(api, actors, action["id"])
    assert result.status_code == 409 and result.json()["error"]["code"] == "listing_changed"
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(RentalRequest)) == 0


def test_cancel_visit_withdraw_application_and_send_message(api, actors, model, inventory, engine):
    lid = publish(api, inventory, actors)
    application = api.post("/api/v1/applications", headers=actors["tenant"], json={"listing_id": lid,
        "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))}).json()
    _, action = propose(api, actors, model, "prepare_withdrawal", {"application_id": application["id"]})
    assert confirm(api, actors, action["id"]).json()["result"]["status"] == "withdrawn"
    visit = api.post("/api/v1/visits", headers=actors["tenant"], json={"listing_id": lid,
        "requested_at": (operations.now()+timedelta(days=4)).isoformat()}).json()
    _, action = propose(api, actors, model, "prepare_visit_cancellation", {"visit_id": visit["id"]})
    assert confirm(api, actors, action["id"]).json()["result"]["status"] == "cancelled"
    c = api.post("/api/v1/conversations", headers=actors["tenant"], json={"subject": "My question", "initial_message": "First"}).json()
    _, action = propose(api, actors, model, "prepare_agency_message", {"conversation_id": c["id"], "body": "Please help with my visit"})
    assert confirm(api, actors, action["id"]).json()["result"]["body"] == "Please help with my visit"
    data = context(engine, inventory).rentals()
    assert data["applications"][0]["status"] == "withdrawn" and data["visits"][0]["status"] == "cancelled"
    assert "tenant_id" not in json.dumps(data)


def test_invalid_tools_and_logging_do_not_leak(api, actors, model, inventory, engine, caplog):
    lid = publish(api, inventory, actors)
    tools = context(engine, inventory)
    assert tools.search(start_date="2027-01-01")["error"] == "invalid_input"
    assert tools.propose("request_visit", {"listing_id": lid, "requested_at": "2030-01-01T12:00:00"})["error"] == "invalid_input"
    assert tools.propose("apply", {"listing_id": lid, "start_date": "2020-01-01", "end_date": "2020-01-10"})["error"] == "past_dates"
    with caplog.at_level("INFO"):
        model.steps = [("prepare_agency_conversation", {"subject": "Secret subject", "initial_message": "Sensitive body"}), "Review first"]
        assert chat(api, actors, "private user prompt").status_code == 200
    assert "assistant_tool" in caplog.text
    for secret in ("Sensitive body", "Secret subject", "private user prompt", "synthetic-offline-key"):
        assert secret not in caplog.text


def test_model_failure_timeout_and_turn_limit_are_safe(api, actors, model, monkeypatch, engine):
    async def failed(*args): raise RuntimeError("Secret key and private provider details")
    monkeypatch.setattr(rental_agent, "run_agent", failed)
    response = chat(api, actors)
    assert response.status_code == 503 and "Secret" not in response.text
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(AssistantThread)) == 0
    async def timeout(*args): raise TimeoutError("Private timeout details")
    monkeypatch.setattr(rental_agent, "run_agent", timeout)
    assert chat(api, actors).json()["error"]["code"] == "assistant_timeout"


def test_sdk_turn_limit_prevents_partial_writes(api, actors, inventory, model, engine, monkeypatch):
    monkeypatch.setenv("ASSISTANT_MAX_TURNS", "2")
    get_settings.cache_clear()
    lid = publish(api, inventory, actors)
    model.steps = [("prepare_save_listing", {"listing_id": lid}), ("get_my_rentals", {})]
    assert chat(api, actors).status_code == 503
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AssistantAction)) == 0
        assert s.scalar(select(func.count()).select_from(SavedListing)) == 0


def test_rate_limit(api, actors, model):
    api.app.state.assistant_throttle.limit = 1
    assert chat(api, actors).status_code == 200
    response = chat(api, actors)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_confirmation_is_atomic_under_concurrency(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    _, action = propose(api, actors, model, "prepare_visit", {"listing_id": lid,
        "requested_at": (operations.now()+timedelta(days=3)).isoformat()})
    barrier = Barrier(2)
    def resolve():
        with Session(engine) as s:
            user = s.get(User, inventory["tenant"])
            barrier.wait()
            return assistant.resolve_action(s, user, UUID(action["id"]), True).result
    with ThreadPoolExecutor(2) as pool:
        first, second = list(pool.map(lambda _: resolve(), range(2)))
    assert first["id"] == second["id"]
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Visit)) == 1


@pytest.mark.parametrize("role", ["tenant", "admin"])
def test_revocation_during_agent_run_discards_reply(api, actors, inventory, model, engine, monkeypatch, role):
    original = rental_agent.run_agent
    async def revoke(*args):
        result = await original(*args)
        with Session(engine) as s, s.begin():
            s.execute(update(User).where(User.id == inventory[role]).values(token_version=User.token_version+1))
        return result
    monkeypatch.setattr(rental_agent, "run_agent", revoke)
    assert api.post(BASE+"/chat", headers=actors[role], json={"message": "hello"}).status_code == 401
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(AssistantThread)) == 0


def test_concurrent_chat_turns_do_not_overwrite_history(api, actors, inventory, model, engine, monkeypatch):
    from types import SimpleNamespace
    thread = chat(api, actors).json()
    barrier = Barrier(2)
    async def simultaneous(settings, context, history, states):
        barrier.wait(timeout=10)
        return SimpleNamespace(final_output="A fresh reply", to_input_list=lambda: history + [{"role": "assistant", "content": "A fresh reply"}])
    monkeypatch.setattr(rental_agent, "run_agent", simultaneous)
    def turn():
        with Session(engine) as s:
            user = s.get(User, inventory["tenant"])
            try:
                return assistant.chat(s, user, ChatInput(message="Follow-up", thread_id=thread["id"]))
            except ApiError as exc:
                return exc
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: turn(), range(2)))
    assert sum(isinstance(r, ApiError) and r.code == "chat_changed" for r in results) == 1
    detail = api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"]).json()
    assert len(detail["messages"]) == 4
