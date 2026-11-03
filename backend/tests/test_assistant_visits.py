"""Agency visit queues have real cards and private pagination, without model page calls."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import AssistantMessage, User, Visit, Listing
from app.repositories.inventory import today
from app.services.operations import now
from test_assistant import BASE, api, actors, model, headers, token_for


@pytest.fixture
def visit_queue(engine, inventory):
    instant = now()
    with Session(engine) as session, session.begin():
        session.add(Listing(rental_unit_id=inventory["room"], status="published",
            available_from=today(), available_until=today()+timedelta(days=730)))
        visits = [Visit(tenant_id=inventory["tenant"], rental_unit_id=inventory["room"],
            requested_at=instant+timedelta(days=10, hours=index),
            created_at=instant+timedelta(microseconds=index), status="requested",
            note=f"Request note {index}") for index in range(21)]
        session.add_all(visits)
        session.flush()
        ids = [str(visit.id) for visit in reversed(visits)]
    return ids


def queue_chat(api, actors, model, **filters):
    model.steps = [("get_agency_records", {"collection": "visits", "status": "requested", **filters}),
        "There are 21 visit requests. I am showing the first six."]
    response = api.post(BASE+"/chat", headers=actors["admin"],
        json={"message": "Show me visit requests waiting to be scheduled."})
    assert response.status_code == 200, response.text
    return response.json()


def page_path(thread, message_id=None):
    return f"{BASE}/threads/{thread['id']}/messages/{message_id or thread['messages'][-1]['id']}/visits"


def test_visit_count_has_matching_cards_and_private_live_pages(api, actors, inventory, engine, model, visit_queue):
    thread = queue_chat(api, actors, model)
    search = thread["messages"][-1]["visit_search"]
    assert search["total"] == 21 and search["page"] == 1 and search["page_size"] == 6
    assert search["cards_only"] is True and len(search["items"]) == 6
    assert [item["id"] for item in search["items"]] == visit_queue[:6]
    assert search["items"][0]["property_title"] == "Synthetic Bologna apartment"
    assert search["items"][0]["unit_name"] == "Room A"
    assert search["items"][0]["tenant_name"] == "Synthetic Tenant"
    assert search["items"][0]["note"] == "Request note 20"
    assert search["items"][0]["status"] == "requested"
    assert "filters" not in search and "tenant_id" not in search["items"][0]
    assert thread["messages"][-1]["actions"] == []
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["admin"]).json() == thread
    calls = len(model.inputs)
    second = api.get(page_path(thread), headers=actors["admin"], params={"page": 2})
    assert second.status_code == 200, second.text
    assert second.json()["total"] == 21
    assert [item["id"] for item in second.json()["items"]] == visit_queue[6:12]
    assert second.headers["cache-control"] == "no-store"
    fourth = api.get(page_path(thread), headers=actors["admin"], params={"page": 4}).json()
    assert len(fourth["items"]) == 3
    assert fourth["total"] == 21 and fourth["page"] == 4
    outside = api.get(page_path(thread), headers=actors["admin"], params={"page": 5}).json()
    assert outside["items"] == [] and outside["total"] == 21
    assert len(model.inputs) == calls
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Visit).where(Visit.status == "requested")) == 21

    assert api.get(page_path(thread)).status_code == 401
    for role in ("tenant", "owner"):
        assert api.get(page_path(thread), headers=actors[role]).status_code == 403
    with Session(engine) as session, session.begin():
        other = User(email="visit.agent@example.com", full_name="Other Agent", role="admin",
            password_hash=session.get(User, inventory["admin"]).password_hash)
        session.add(other); session.flush(); inventory["visit_admin"] = other.id
    other_headers = headers(token_for(api, engine, inventory, "visit_admin"))
    assert api.get(page_path(thread), headers=other_headers).status_code == 404
    assert api.get(page_path(thread, thread["messages"][0]["id"]), headers=actors["admin"]).status_code == 404
    assert api.get(page_path(thread, str(uuid4())), headers=actors["admin"]).status_code == 404
    for value in (0, -1, 10001):
        assert api.get(page_path(thread), headers=actors["admin"], params={"page": value}).status_code == 422


def test_visit_pages_keep_filters_and_recheck_changed_status(api, actors, model, visit_queue):
    thread = queue_chat(api, actors, model, query="Synthetic Tenant")
    changed = api.patch(f"/api/v1/admin/visits/{visit_queue[0]}", headers=actors["admin"],
        json={"status": "scheduled", "scheduled_at": (now()+timedelta(days=12)).isoformat(), "duration_minutes": 30})
    assert changed.status_code == 200, changed.text
    result = api.get(page_path(thread), headers=actors["admin"]).json()
    assert result["total"] == 20
    assert [item["id"] for item in result["items"]] == visit_queue[1:7]
    assert all(item["status"] == "requested" for item in result["items"])
    empty = queue_chat(api, actors, model, query="No matching tenant")
    search = empty["messages"][-1]["visit_search"]
    assert search["total"] == 0 and search["items"] == [] and search["cards_only"] is True
    one = queue_chat(api, actors, model, record_id=visit_queue[1])
    assert one["messages"][-1]["visit_search"]["total"] == 1
    assert one["messages"][-1]["visit_search"]["items"][0]["id"] == visit_queue[1]


def test_visit_page_context_targets_visible_records_and_rejects_forgery(api, actors, model, visit_queue):
    thread = queue_chat(api, actors, model)
    context = {"message_id": thread["messages"][-1]["id"], "page": 2}
    model.steps = ["Which time would you like?"]
    result = api.post(BASE+"/chat", headers=actors["admin"], json={"thread_id": thread["id"],
        "message": "Schedule the first one.", "visit_search_context": context})
    assert result.status_code == 200, result.text
    instructions = model.inputs[-1][0]
    assert "Current agency visit page" in instructions
    assert instructions.index(visit_queue[6]) < instructions.index(visit_queue[7])
    assert result.json()["messages"][-2]["content"] == "Schedule the first one."
    assert result.json()["messages"][-1]["actions"] == []
    assert api.post(BASE+"/chat", headers=actors["admin"], json={"message": "First one", "visit_search_context": context}).status_code == 422
    for message_id in (str(uuid4()), thread["messages"][0]["id"]):
        response = api.post(BASE+"/chat", headers=actors["admin"], json={"thread_id": thread["id"],
            "message": "First one", "visit_search_context": {**context, "message_id": message_id}})
        assert response.status_code == 404
    forged = api.post(BASE+"/chat", headers=actors["admin"], json={"thread_id": thread["id"],
        "message": "First one", "visit_search_context": {**context, "filters": {"status": "scheduled"}}})
    assert forged.status_code == 422
    other = queue_chat(api, actors, model)
    assert api.post(BASE+"/chat", headers=actors["admin"], json={"thread_id": other["id"],
        "message": "First one", "visit_search_context": context}).status_code == 404
    assert api.post(BASE+"/chat", headers=actors["tenant"], json={"thread_id": thread["id"],
        "message": "First one", "visit_search_context": context}).status_code == 404


def test_visit_mixed_replies_keep_explanations_and_old_chats_have_no_visit_search(api, actors, engine, model, visit_queue):
    for extra in [("get_agency_report", {"kind": "dashboard"}),
                  ("get_agency_records", {"collection": "properties"}),
                  ("get_agency_records", {"collection": "visits", "status": "not_a_status"}),
                  ("prepare_visit_update", {"visit_id": visit_queue[0], "status": "cancelled"})]:
        model.steps = [("get_agency_records", {"collection": "visits", "status": "requested"}), extra,
            "An explanation that must stay visible."]
        result = api.post(BASE+"/chat", headers=actors["admin"], json={"message": "Show visits and help with the next step"})
        assert result.status_code == 200, result.text
        assert result.json()["messages"][-1]["visit_search"]["cards_only"] is False
    thread = queue_chat(api, actors, model)
    with Session(engine) as session, session.begin():
        session.get(AssistantMessage, UUID(thread["messages"][-1]["id"])).visit_search = None
    detail = api.get(f"{BASE}/threads/{thread['id']}", headers=actors["admin"]).json()
    assert detail["messages"][-1]["visit_search"] is None
    assert api.get(page_path(thread), headers=actors["admin"]).status_code == 404


def test_visit_detail_exposes_tenant_name_only_to_agency(api, actors, visit_queue):
    agency = api.get(f"/api/v1/visits/{visit_queue[0]}", headers=actors["admin"])
    assert agency.status_code == 200
    assert agency.json()["tenant_name"] == "Synthetic Tenant"
    tenant = api.get(f"/api/v1/visits/{visit_queue[0]}", headers=actors["tenant"])
    assert tenant.status_code == 200
    assert "tenant_name" not in tenant.json()
    assert api.get(f"/api/v1/visits/{visit_queue[0]}", headers=actors["other"] if "other" in actors else actors["owner"]).status_code in (403, 404)
