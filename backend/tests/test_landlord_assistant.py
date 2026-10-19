"""Landlord workflows use PostgreSQL, real authorization, and the offline Agents SDK loop."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import AssistantAction, Property, RentalUnit, User
from app.repositories.inventory import today
from app.services import assistant, agency_assistant
from test_auth import api
from test_inventory import actors, draft, publish, prop_payload
from test_assistant import BASE, model, context, confirm
from test_operations import apply


def landlord_chat(api, actors, message="Show my properties", thread=None):
    return api.post(BASE + "/chat", headers=actors["owner"], json={"message": message, "thread_id": thread})


def prepare(api, actors, model, tool, values):
    model.steps = [(tool, values), "Review the details and click Confirm action."]
    response = landlord_chat(api, actors)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["messages"][-1]["actions"]) == 1, result
    return result, result["messages"][-1]["actions"][0]


def complete(api, actors, action):
    response = confirm(api, actors, action["id"], role="owner")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    return response.json()["result"]


def test_landlord_tools_and_private_history(api, actors, inventory, engine, model):
    lid = draft(api, inventory, actors)
    model.steps = [("get_landlord_records", {"collection": "listings", "record_id": lid}),
                   ("get_landlord_report", {"kind": "dashboard"}), "Here are your properties."]
    response = landlord_chat(api, actors)
    assert response.status_code == 200, response.text
    thread = response.json()
    instructions, _, _, names = model.inputs[0]
    assert "landlord assistant" in instructions
    assert {"prepare_landlord_property_creation", "prepare_unit_update", "get_landlord_records",
            "get_landlord_report", "check_my_unit_availability", "prepare_landlord_listing_status"} <= set(names)
    assert not {"get_agency_records", "get_agency_conversations", "prepare_property_creation",
                "prepare_application_approval", "prepare_visit_update", "get_my_rentals",
                "prepare_listing_status", "prepare_tenant_message"} & set(names)
    assert api.get(BASE + "/status", headers=actors["owner"]).json()["available"] is True
    assert api.get(BASE + "/threads", headers=actors["owner"]).json()[0]["id"] == thread["id"]
    for role in ("tenant", "other_owner", "admin"):
        assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors[role]).status_code == 404
        assert api.post(BASE + "/chat", headers=actors[role], json={"message": "Read this", "thread_id": thread["id"]}).status_code == 404
    tools = context(engine, inventory, "owner")
    assert tools.landlord_records(collection="properties", query="Bologna")["total"] == 1
    assert tools.landlord_records(collection="units", property_id=str(inventory["property"]))["total"] == 3
    assert tools.landlord_records(collection="units", query="Room A")["total"] == 1
    assert tools.landlord_records(collection="listings", status="draft")["total"] == 1
    assert tools.landlord_records(collection="properties", query="%")["total"] == 0
    assert tools.landlord_report(kind="occupancy")["summary"]["total_units"] == 2
    assert tools.landlord_records(collection="applications")["error"] == "invalid_input"
    assert tools.landlord_records(collection="properties", status="published")["error"] == "invalid_input"
    assert tools.landlord_records(collection="properties", page=0)["error"] == "invalid_input"
    with pytest.raises(ApiError):
        tools.agency_records(collection="landlords")
    with pytest.raises(ApiError):
        tools.conversations()
    with pytest.raises(ApiError):
        context(engine, inventory).landlord_report(kind="dashboard")


def test_read_scope_and_contract_privacy(api, actors, inventory, engine):
    lid = publish(api, inventory, actors)
    request = apply(api, actors, lid)
    contract = api.post(f"/api/v1/admin/applications/{request['id']}/approve", headers=actors["admin"], json={}).json()
    tools = context(engine, inventory, "owner")
    view = tools.landlord_records(collection="contracts")["items"][0]
    assert view["id"] == contract["id"] and view["monthly_rent"] == "650.00"
    assert not {"tenant_id", "rental_request_id", "tenant_name", "email"} & view.keys()
    other = context(engine, inventory, "other_owner")
    for collection, identifier in (("properties", inventory["property"]), ("units", inventory["room"]),
                                   ("listings", lid), ("contracts", contract["id"])):
        assert other.landlord_records(collection=collection)["total"] == 0
        assert other.landlord_records(collection=collection, record_id=str(identifier))["error"] == "not_found"
    assert other.landlord_records(collection="units", property_id=str(inventory["property"]))["error"] == "not_found"
    assert other.landlord_report(kind="occupancy")["summary"]["properties"] == 0


def test_property_to_submitted_listing_workflow(api, actors, inventory, engine, model):
    api.app.state.assistant_throttle.limit = 100
    thread, action = prepare(api, actors, model, "prepare_landlord_property_creation", prop_payload())
    assert action["payload"]["landlord_id"] == str(inventory["owner"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Property)) == 1
    prop = complete(api, actors, action)
    assert prop["landlord_id"] == str(inventory["owner"])
    assert complete(api, actors, action)["id"] == prop["id"]
    model.steps = [("get_landlord_records", {"collection": "properties", "record_id": prop["id"]}), "Ready to add rooms."]
    response = landlord_chat(api, actors, "Continue with my new property", thread["id"])
    assert response.status_code == 200, response.text
    assert prop["id"] in model.inputs[-1][0] and "result_identifiers" in model.inputs[-1][0]
    _, action = prepare(api, actors, model, "prepare_property_update", {"property_id": prop["id"], "title": "My Florence home", "amenities": []})
    assert complete(api, actors, action)["title"] == "My Florence home"
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": prop["id"], "kind": "room", "name": "Study room", "monthly_rent": "700", "deposit": "0"})
    unit = complete(api, actors, action)
    _, action = prepare(api, actors, model, "prepare_unit_update", {"unit_id": unit["id"], "monthly_rent": "725", "area_sqm": "18"})
    assert complete(api, actors, action)["monthly_rent"] == "725.00"
    _, action = prepare(api, actors, model, "prepare_listing_creation", {"unit_id": unit["id"], "available_from": str(today()), "available_until": str(today()+timedelta(days=365))})
    listing = complete(api, actors, action)
    _, action = prepare(api, actors, model, "prepare_listing_update", {"unit_id": unit["id"], "clear_available_until": True})
    assert complete(api, actors, action)["available_until"] is None
    _, action = prepare(api, actors, model, "prepare_landlord_listing_status", {"listing_id": listing["id"], "status": "submitted"})
    assert complete(api, actors, action)["status"] == "submitted"
    _, action = prepare(api, actors, model, "prepare_landlord_listing_status", {"listing_id": listing["id"], "status": "draft"})
    assert complete(api, actors, action)["status"] == "draft"


@pytest.mark.parametrize("kind,values", [
    ("update_property", {"property_id": "property", "title": "Unauthorized"}),
    ("create_unit", {"property_id": "property", "kind": "room", "name": "New", "monthly_rent": "700"}),
    ("update_unit", {"unit_id": "room", "monthly_rent": "700"}),
    ("create_listing", {"unit_id": "room_b", "available_from": "today"}),
    ("update_listing", {"unit_id": "room", "available_from": "today"}),
    ("change_listing_status", {"listing_id": "listing", "status": "submitted"}),
])
def test_proposal_and_execution_deny_other_owners(api, actors, inventory, engine, kind, values):
    inventory["listing"] = draft(api, inventory, actors)
    payload = {key: str(today()) if value == "today" else str(inventory[value]) if value in inventory else value
               for key, value in values.items()}
    assert context(engine, inventory, "other_owner").propose(kind, payload)["error"] == "not_found"
    with Session(engine) as session, pytest.raises(ApiError) as error:
        agency_assistant.execute(session, session.get(User, inventory["other_owner"]), kind, payload)
    assert error.value.status_code == 404


@pytest.mark.parametrize("status", ["approved", "rejected", "published", "unpublished"])
def test_landlord_cannot_moderate_even_with_forged_action(api, actors, inventory, engine, status):
    lid = draft(api, inventory, actors)
    tools = context(engine, inventory, "owner")
    payload = {"listing_id": lid, "status": status, "review_note": "A reason"}
    with pytest.raises(ApiError) as error:
        tools.propose("change_listing_status", payload)
    assert error.value.status_code == 403
    with Session(engine) as session, pytest.raises(ApiError) as error:
        agency_assistant.execute(session, session.get(User, inventory["owner"]), "change_listing_status", payload)
    assert error.value.status_code == 403


def test_forbidden_capabilities_and_owner_injection(api, actors, inventory, engine):
    tools = context(engine, inventory, "owner")
    for kind in ("review_application", "approve_application", "reject_application", "update_visit", "send_tenant_message", "apply", "contact_agency"):
        with pytest.raises(ApiError) as error:
            tools.propose(kind, {})
        assert error.value.status_code == 403
    with pytest.raises(ApiError) as error:
        tools.propose("create_property", {**prop_payload(), "landlord_id": str(inventory["other_owner"])})
    assert error.value.status_code == 403


def test_confirmation_scope_staleness_and_atomicity(api, actors, inventory, engine, model, monkeypatch):
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": str(inventory["property"]), "kind": "room", "name": "New room", "monthly_rent": "700"})
    for role in ("other_owner", "tenant", "admin"):
        assert confirm(api, actors, action["id"], role=role).status_code == 404
        assert api.post(f"{BASE}/actions/{action['id']}/cancel", headers=actors[role]).status_code == 404
    original = agency_assistant.execute
    def fail_after_write(*args):
        original(*args)
        raise ApiError(409, "test_rollback", "Synthetic failure")
    with monkeypatch.context() as patch:
        patch.setattr(agency_assistant, "execute", fail_after_write)
        assert confirm(api, actors, action["id"], role="owner").status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalUnit)) == 3
        assert session.get(AssistantAction, UUID(action["id"])).status == "pending"
    assert complete(api, actors, action)["name"] == "New room"
    _, action = prepare(api, actors, model, "prepare_property_update", {"property_id": str(inventory["property"]), "title": "Assistant title"})
    api.patch(f"/api/v1/properties/{inventory['property']}", headers=actors["owner"], json={"title": "Changed in workspace"})
    response = confirm(api, actors, action["id"], role="owner")
    assert response.status_code == 409 and response.json()["error"]["code"] == "record_changed"


def test_confirmation_rechecks_inventory_lock(api, actors, inventory, engine, model):
    _, action = prepare(api, actors, model, "prepare_unit_update", {"unit_id": str(inventory["room"]), "monthly_rent": "900"})
    publish(api, inventory, actors)
    response = confirm(api, actors, action["id"], role="owner")
    assert response.status_code == 409 and response.json()["error"]["code"] == "review_locked"
    assert context(engine, inventory, "owner").propose("update_property", {"property_id": str(inventory["property"]), "title": "Locked"})["error"] == "review_locked"


def test_availability_scope_windows_and_apartment_conflicts(api, actors, inventory, engine):
    lid = publish(api, inventory, actors)
    draft(api, inventory, actors, unit="apartment")
    tools = context(engine, inventory, "owner")
    start, end = today()+timedelta(days=20), today()+timedelta(days=50)
    values = {"unit_id": str(inventory["room"]), "start_date": str(start), "end_date": str(end)}
    assert tools.landlord_availability(**values)["can_accept_applications"] is True
    request = apply(api, actors, lid, offset=20, length=30)
    assert api.post(f"/api/v1/admin/applications/{request['id']}/approve", headers=actors["admin"], json={}).status_code == 200
    result = tools.landlord_availability(**{**values, "unit_id": str(inventory["apartment"])})
    assert result["reason"] == "rental_conflict" and result["available"] is False
    assert tools.landlord_availability(**{**values, "start_date": str(end), "end_date": str(end+timedelta(days=10))})["available"] is True
    assert tools.landlord_availability(**{**values, "end_date": str(today()+timedelta(days=800))})["reason"] == "outside_listing_window"
    assert context(engine, inventory, "other_owner").landlord_availability(**values)["error"] == "not_found"


def test_concurrent_landlord_confirmation_creates_one_unit(api, actors, inventory, engine, model):
    _, action = prepare(api, actors, model, "prepare_unit_creation", {"property_id": str(inventory["property"]), "kind": "room", "name": "Concurrent room", "monthly_rent": "700"})
    barrier = Barrier(2)
    def resolve():
        with Session(engine) as session:
            user = session.get(User, inventory["owner"])
            barrier.wait()
            return assistant.resolve_action(session, user, UUID(action["id"]), True).result
    with ThreadPoolExecutor(2) as pool:
        first, second = list(pool.map(lambda _: resolve(), range(2)))
    assert first["id"] == second["id"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RentalUnit)) == 4
