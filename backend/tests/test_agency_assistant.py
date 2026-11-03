"""Agency requests run through the actual SDK loop and PostgreSQL transaction services."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import AssistantAction, Property, RentalUnit, Listing, RentalContract, User, Message
from app.repositories.inventory import today
from app.services import assistant, agency_assistant, operations
from test_auth import api, headers, token_for
from test_inventory import actors, publish, draft, prop_payload
from test_assistant import BASE, model, confirm, context, chat, propose


def agency_chat(api, actors, message="Show pending agency requests", thread=None):
    return api.post(BASE + "/chat", headers=actors["admin"], json={"message": message, "thread_id": thread})


def prepare(api, actors, model, tool, values):
    model.steps = [(tool, values), "Review the details and click Confirm action."]
    response = agency_chat(api, actors)
    assert response.status_code == 200, response.text
    result = response.json()
    actions = result["messages"][-1]["actions"]
    assert len(actions) == 1, result
    return result, actions[0]


def complete(api, actors, action):
    response = confirm(api, actors, action["id"], role="admin")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    return response.json()["result"]


def test_agency_tools_reads_and_private_history(api, actors, inventory, engine, model):
    lid = draft(api, inventory, actors)
    model.steps = [("get_agency_records", {"collection": "listings", "record_id": lid}),
                   ("get_agency_report", {"kind": "dashboard"}), "Here are the agency records."]
    response = agency_chat(api, actors)
    assert response.status_code == 200, response.text
    thread = response.json()
    instructions, inputs, settings, names = model.inputs[0]
    assert "agency administrator" in instructions
    assert "prepare_property_creation" in names and "prepare_application_approval" in names
    assert "prepare_application" not in names and "get_my_rentals" not in names
    assert "password_hash" not in str(model.inputs)
    assert api.get(BASE + "/threads", headers=actors["admin"]).json()[0]["id"] == thread["id"]
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"]).status_code == 404
    with Session(engine) as session, session.begin():
        other_admin = User(email="other.agent@example.com", password_hash=session.get(User, inventory["admin"]).password_hash,
                           full_name="Other agent", role="admin")
        session.add(other_admin); session.flush(); inventory["other_admin"] = other_admin.id
    other = headers(token_for(api, engine, inventory, "other_admin"))
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=other).status_code == 404
    assert api.get(BASE + "/threads", headers=other).json() == []
    _, action = prepare(api, actors, model, "prepare_listing_status", {"listing_id": lid, "status": "submitted"})
    assert api.post(f"{BASE}/actions/{action['id']}/confirm", headers=other, json={"confirmed": True}).status_code == 404
    assert api.post(f"{BASE}/actions/{action['id']}/cancel", headers=other).status_code == 404
    tools = context(engine, inventory, "admin")
    assert tools.agency_records(collection="listings", record_id=lid)["items"][0]["status"] == "draft"
    assert tools.agency_records(collection="properties", query="Bologna")["total"] == 1
    assert tools.agency_records(collection="units", query="Room A")["total"] == 1
    assert tools.agency_records(collection="landlords")["items"][0].keys() == {"id", "full_name", "role"}
    assert tools.agency_records(collection="agents", query="Synthetic Agent")["total"] == 1
    assert tools.agency_report(kind="occupancy")["summary"]["total_units"] == 2
    assert tools.agency_records(collection="properties", status="published")["error"] == "invalid_input"


def test_submitted_listing_cards_persist_in_tool_order_and_stay_private(api, actors, inventory, engine, model):
    first = draft(api, inventory, actors)
    newest = draft(api, inventory, actors, unit="room_b", available_until=None)
    for identifier in (first, newest):
        assert api.post(f"/api/v1/listings/{identifier}/submit", headers=actors["owner"]).status_code == 200
    model.steps = [("get_agency_records", {"collection": "listings", "status": "submitted"}),
                   "Open a listing card to review it."]
    response = agency_chat(api, actors, "Show me listings waiting for agency review, newest first.")
    assert response.status_code == 200, response.text
    thread = response.json()
    cards = thread["messages"][-1]["listings"]
    assert [card["id"] for card in cards] == [newest, first]
    assert cards[0] == {
        "id": newest, "title": "Synthetic Bologna apartment", "city": "Bologna",
        "kind": "room", "unit_name": "Room B", "monthly_rent": "600.00", "available_now": False,
        "status": "submitted", "available_from": str(today()), "available_until": None,
    }
    assert cards[1]["available_until"] == str(today()+timedelta(days=730))
    assert thread["messages"][-1]["actions"] == []
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["admin"]).json() == thread
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"]).status_code == 404
    assert api.get(f"/api/v1/listings/{newest}").status_code == 404
    tenant_tools = context(engine, inventory)
    with pytest.raises(ApiError) as error:
        tenant_tools.agency_records(collection="listings", status="submitted")
    assert error.value.status_code == 403
    assert tenant_tools.listings == {}
    assert tenant_tools.search(city="Bologna")["items"] == []
    model.steps = [("get_agency_records", {"collection": "listings", "record_id": first}),
                   "Here is the selected listing."]
    detail = agency_chat(api, actors, "Show the other listing", thread["id"])
    assert detail.status_code == 200, detail.text
    assert [card["id"] for card in detail.json()["messages"][-1]["listings"]] == [first]


def test_private_listing_review_detail_requires_agency_role(api, actors, inventory):
    identifier = draft(api, inventory, actors)
    path = f"/api/v1/admin/listings/{identifier}"
    response = api.get(path, headers=actors["admin"])
    assert response.status_code == 200, response.text
    assert response.json()["id"] == identifier
    assert response.json()["rental_unit_id"] == str(inventory["room"])
    assert response.json()["status"] == "draft"
    assert api.get(path).status_code == 401
    for role in ("tenant", "owner", "other_owner"):
        assert api.get(path, headers=actors[role]).status_code == 403
    assert api.get(f"/api/v1/admin/listings/{uuid4()}", headers=actors["admin"]).status_code == 404


def test_role_checks_on_tools_and_confirmation(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    _, tenant_action = propose(api, actors, model, "prepare_save_listing", {"listing_id": lid})
    assert confirm(api, actors, tenant_action["id"], role="admin").status_code == 404
    _, agency_action = prepare(api, actors, model, "prepare_listing_status", {"listing_id": lid, "status": "unpublished"})
    assert confirm(api, actors, agency_action["id"]).status_code == 404
    for tools, kind, values in [(context(engine, inventory), "change_listing_status", {"listing_id": lid, "status": "unpublished"}),
                               (context(engine, inventory, "admin"), "save_listing", {"listing_id": lid})]:
        with pytest.raises(ApiError) as error:
            tools.propose(kind, values)
        assert error.value.status_code == 403
    with pytest.raises(ApiError):
        context(engine, inventory).agency_report(kind="dashboard")


def test_property_unit_listing_creation_editing_and_publication(api, actors, inventory, model, engine):
    api.app.state.assistant_throttle.limit = 100
    payload = {**prop_payload(), "landlord_id": str(inventory["owner"])}
    thread, action = prepare(api, actors, model, "prepare_property_creation", payload)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Property)) == 1
    prop = complete(api, actors, action)
    assert prop["amenities"] == ["balcony", "wifi"]
    assert complete(api, actors, action)["id"] == prop["id"]
    model.steps = [("get_agency_records", {"collection": "properties", "record_id": prop["id"]}), "The new property is ready for a room."]
    followup = agency_chat(api, actors, "Continue with the new property", thread["id"])
    assert followup.status_code == 200, followup.text
    assert prop["id"] in model.inputs[-1][0] and "result_identifiers" in model.inputs[-1][0]
    _, action = prepare(api, actors, model, "prepare_property_update", {"property_id": prop["id"], "title": "Updated Florence home", "amenities": []})
    assert action["payload"]["amenities"] == []
    assert complete(api, actors, action)["title"] == "Updated Florence home"
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": prop["id"], "kind": "room", "name": "Study room", "monthly_rent": "700", "deposit": "0"})
    unit = complete(api, actors, action)
    assert unit["monthly_rent"] == "700.00"
    _, action = prepare(api, actors, model, "prepare_unit_update", {"unit_id": unit["id"], "monthly_rent": "725", "area_sqm": "18"})
    assert complete(api, actors, action)["monthly_rent"] == "725.00"
    _, action = prepare(api, actors, model, "prepare_listing_creation", {"unit_id": unit["id"], "available_from": str(today()), "available_until": str(today()+timedelta(days=365))})
    listing = complete(api, actors, action)
    assert listing["status"] == "draft"
    _, action = prepare(api, actors, model, "prepare_listing_update", {"unit_id": unit["id"], "clear_available_until": True})
    assert complete(api, actors, action)["available_until"] is None
    for status in ("submitted", "approved", "published", "unpublished", "draft"):
        _, action = prepare(api, actors, model, "prepare_listing_status", {"listing_id": listing["id"], "status": status})
        assert complete(api, actors, action)["status"] == status
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Property)) == 2
        assert session.scalar(select(func.count()).select_from(RentalUnit)) == 4
        assert session.scalar(select(func.count()).select_from(Listing)) == 1


def test_inventory_confirmation_atomicity_and_changed_record(api, actors, inventory, model, engine, monkeypatch):
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": str(inventory["property"]), "kind": "room", "name": "New room", "monthly_rent": "700"})
    original = agency_assistant.execute
    def fail_after_write(*args):
        original(*args)
        raise ApiError(409, "test_rollback", "Synthetic failure after inventory write")
    with monkeypatch.context() as patch:
        patch.setattr(agency_assistant, "execute", fail_after_write)
        assert confirm(api, actors, action["id"], role="admin").status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalUnit)) == 3
        assert session.get(AssistantAction, UUID(action["id"])).status == "pending"
    assert complete(api, actors, action)["name"] == "New room"
    _, action = prepare(api, actors, model, "prepare_property_update", {"property_id": str(inventory["property"]), "title": "Assistant title"})
    assert api.patch(f"/api/v1/properties/{inventory['property']}", headers=actors["owner"], json={"title": "Owner changed title"}).status_code == 200
    response = confirm(api, actors, action["id"], role="admin")
    assert response.status_code == 409 and response.json()["error"]["code"] == "record_changed"
    assert api.get(f"/api/v1/properties/{inventory['property']}", headers=actors["admin"]).json()["title"] == "Owner changed title"


def test_review_and_approval_create_one_contract(api, actors, inventory, engine, model):
    lid = publish(api, inventory, actors)
    application = api.post("/api/v1/applications", headers=actors["tenant"], json={"listing_id": lid,
        "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))}).json()
    _, action = prepare(api, actors, model, "prepare_application_review", {"application_id": application["id"]})
    assert complete(api, actors, action)["status"] == "reviewing"
    _, action = prepare(api, actors, model, "prepare_application_approval", {"application_id": application["id"]})
    assert action["payload"]["monthly_rent"] == "650.00"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalContract)) == 0
    result = complete(api, actors, action)
    assert result["status"] == "confirmed" and result["monthly_rent"] == "650.00"
    assert complete(api, actors, action)["id"] == result["id"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalContract)) == 1


def test_application_rejection_and_visit_schedule_and_agency_reply(api, actors, inventory, model, engine):
    lid = publish(api, inventory, actors)
    application = api.post("/api/v1/applications", headers=actors["tenant"], json={"listing_id": lid,
        "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))}).json()
    _, action = prepare(api, actors, model, "prepare_application_rejection", {"application_id": application["id"], "review_note": "Tenant requested another date"})
    assert complete(api, actors, action)["review_note"] == "Tenant requested another date"
    visit = api.post("/api/v1/visits", headers=actors["tenant"], json={"listing_id": lid,
        "requested_at": (operations.now()+timedelta(days=4)).isoformat()}).json()
    scheduled = (operations.now()+timedelta(days=5)).isoformat()
    _, action = prepare(api, actors, model, "prepare_visit_update", {"visit_id": visit["id"], "status": "scheduled", "scheduled_at": scheduled, "duration_minutes": 45})
    assert action["payload"]["assigned_admin_id"] == str(inventory["admin"])
    result = complete(api, actors, action)
    assert result["status"] == "scheduled" and result["duration_minutes"] == 45
    conversation = api.post("/api/v1/conversations", headers=actors["tenant"], json={"subject": "Visit", "initial_message": "When can I visit?"}).json()
    tools = context(engine, inventory, "admin")
    assert tools.agency_records(collection="conversations", query="Synthetic Tenant")["items"][0]["id"] == conversation["id"]
    assert tools.agency_records(collection="applications", query="Synthetic Tenant")["items"][0]["tenant_name"] == "Synthetic Tenant"
    assert tools.agency_records(collection="visits", query="Synthetic Tenant")["total"] == 1
    _, action = prepare(api, actors, model, "prepare_tenant_message", {"conversation_id": conversation["id"], "body": "Your visit is scheduled."})
    result = complete(api, actors, action)
    assert result["sender_type"] == "agency"
    assert complete(api, actors, action)["id"] == result["id"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 2


def test_inventory_confirmation_is_idempotent_under_concurrency(api, actors, inventory, model, engine):
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": str(inventory["property"]), "kind": "room", "name": "Concurrent room", "monthly_rent": "600"})
    barrier = Barrier(2)
    def resolve():
        with Session(engine) as session:
            user = session.get(User, inventory["admin"])
            barrier.wait()
            return assistant.resolve_action(session, user, UUID(action["id"]), True).result
    with ThreadPoolExecutor(2) as pool:
        first, second = list(pool.map(lambda _: resolve(), range(2)))
    assert first["id"] == second["id"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalUnit)) == 4


def test_invalid_agency_requests_and_locked_content(api, actors, inventory, engine, model):
    tools = context(engine, inventory, "admin")
    assert tools.propose("create_property", prop_payload())["error"] == "invalid_owner"
    assert tools.propose("update_property", {"property_id": str(inventory["property"]), "landlord_id": str(inventory["other_owner"])})["error"] == "invalid_input"
    lid = publish(api, inventory, actors)
    assert tools.propose("update_unit", {"unit_id": str(inventory["room"]), "monthly_rent": "900"})["error"] == "review_locked"
    assert tools.propose("change_listing_status", {"listing_id": lid, "status": "rejected"})["error"] == "invalid_input"
    assert tools.propose("create_unit", {"property_id": str(inventory["property"]), "kind": "room", "name": "Room C", "monthly_rent": "600"})["error"] == "review_locked"


def test_agency_approval_rechecks_conflicts(api, actors, inventory, engine, model):
    lid = publish(api, inventory, actors)
    dates = {"listing_id": lid, "start_date": str(today()+timedelta(days=20)), "end_date": str(today()+timedelta(days=50))}
    application = api.post("/api/v1/applications", headers=actors["tenant"], json=dates).json()
    _, action = prepare(api, actors, model, "prepare_application_approval", {"application_id": application["id"]})
    other = headers(token_for(api, engine, inventory, "other"))
    competitor = api.post("/api/v1/applications", headers=other, json=dates).json()
    assert api.post(f"/api/v1/admin/applications/{competitor['id']}/approve", headers=actors["admin"], json={}).status_code == 200
    response = confirm(api, actors, action["id"], role="admin")
    assert response.status_code == 409 and response.json()["error"]["code"] == "rental_conflict"
    with Session(engine) as session:
        assert session.get(AssistantAction, UUID(action["id"])).status == "pending"
        assert session.scalar(select(func.count()).select_from(RentalContract)) == 1
