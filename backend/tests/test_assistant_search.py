"""Tenant search cards and server-owned, live pagination; no provider calls."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import AssistantMessage, Listing, Property, RentalUnit
from app.repositories.inventory import today
from conftest import application, contract
from test_assistant import BASE, api, actors, model, chat, headers, token_for


@pytest.fixture
def search_inventory(engine, inventory):
    start, end = today()+timedelta(days=70), today()+timedelta(days=250)
    with Session(engine) as session, session.begin():
        units = []
        for index in range(8):
            unit = RentalUnit(property_id=inventory["property"], name=f"Search Room {index}",
                kind="room", monthly_rent=640+index)
            session.add(unit)
            units.append(unit)
        extra = [RentalUnit(property_id=inventory["property"], name=name, kind="room", monthly_rent=rent)
            for name, rent in (("Too expensive", 700), ("Partial dates", 650), ("Draft room", 650), ("Booked room", 650))]
        session.add_all(extra)
        rome = Property(landlord_id=inventory["owner"], title="Synthetic Rome home", description="Fixture",
            city="Rome", address="Synthetic Street 5", postal_code="00100")
        session.add(rome)
        session.flush()
        rome_unit = RentalUnit(property_id=rome.id, name="Rome room", kind="room", monthly_rent=650)
        session.add(rome_unit)
        apartment = session.get(RentalUnit, inventory["apartment"])
        apartment.monthly_rent = 650
        session.flush()
        for unit in units+extra+[rome_unit, apartment]:
            session.add(Listing(rental_unit_id=unit.id, status="draft" if unit.name == "Draft room" else "published",
                available_from=start+timedelta(days=1) if unit.name == "Partial dates" else today(),
                available_until=today()+timedelta(days=730)))
        blocked = {**inventory, "room": extra[-1].id}
        request_id = application(session, blocked, start=start, end=end)
        contract(session, blocked, request_id, start=start, end=end)
        session.flush()
        ids = [str(session.query(Listing).filter_by(rental_unit_id=unit.id).one().id) for unit in units]
    return {"ids": ids, "filters": {"city": "Bologna", "property_type": "room", "min_price": "640",
        "max_price": "660", "start_date": str(start), "end_date": str(end), "sort": "price_asc"}}


def search_chat(api, actors, model, filters):
    model.steps = [("search_homes", filters), "1. This text catalogue must be hidden by the cards-only UI."]
    response = chat(api, actors)
    assert response.status_code == 200, response.text
    return response.json()


def page_path(thread, message=None):
    return f"{BASE}/threads/{thread['id']}/messages/{(message or thread['messages'][-1])['id']}/listings"


def test_search_pages_preserve_all_filters_sort_and_private_history(api, actors, inventory, engine, model, search_inventory):
    thread = search_chat(api, actors, model, search_inventory["filters"])
    message = thread["messages"][-1]
    assert message["listing_search"] == {"page": 1, "page_size": 6, "total": 8, "cards_only": True}
    assert [item["id"] for item in message["listings"]] == search_inventory["ids"][:6]
    assert "filters" not in message["listing_search"]
    assert api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"]).json() == thread
    model_requests = len(model.inputs)
    second = api.get(page_path(thread), headers=actors["tenant"], params={"page": 2})
    assert second.status_code == 200, second.text
    assert second.json()["total"] == 8
    assert second.json()["page"] == 2 and second.json()["page_size"] == 6
    assert [item["id"] for item in second.json()["items"]] == search_inventory["ids"][6:]
    first = api.get(page_path(thread), headers=actors["tenant"], params={"page": 1})
    assert [item["id"] for item in first.json()["items"]] == search_inventory["ids"][:6]
    assert len(model.inputs) == model_requests
    assert second.headers["cache-control"] == "no-store"
    assert api.get(page_path(thread), params={"page": 2}).status_code == 401
    other = headers(token_for(api, engine, inventory, "other"))
    assert api.get(page_path(thread), headers=other).status_code == 404
    for role in ("admin", "owner"):
        assert api.get(page_path(thread), headers=actors[role]).status_code == 403
    for value in (0, -1, 10001):
        assert api.get(page_path(thread), headers=actors["tenant"], params={"page": value}).status_code == 422
    assert api.get(page_path(thread, thread["messages"][0]), headers=actors["tenant"]).status_code == 404
    assert api.get(page_path(thread).replace(message["id"], str(uuid4())), headers=actors["tenant"]).status_code == 404


def test_search_pagination_rechecks_current_publication_and_rent(api, actors, model, engine, search_inventory):
    thread = search_chat(api, actors, model, search_inventory["filters"])
    with Session(engine) as session, session.begin():
        listing = session.get(Listing, UUID(search_inventory["ids"][-1]))
        listing.status = "unpublished"
        unit_id = session.get(Listing, UUID(search_inventory["ids"][-2])).rental_unit_id
        session.get(RentalUnit, unit_id).monthly_rent = 900
    response = api.get(page_path(thread), headers=actors["tenant"], params={"page": 2})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 6
    assert response.json()["items"] == []


def test_last_search_page_replaces_previous_cards_and_empty_search_has_metadata(api, actors, model, search_inventory):
    model.steps = [("search_homes", search_inventory["filters"]),
        ("search_homes", {**search_inventory["filters"], "page": 2}), "Use these cards."]
    response = chat(api, actors)
    assert response.status_code == 200, response.text
    message = response.json()["messages"][-1]
    assert message["listing_search"]["page"] == 2
    assert [item["id"] for item in message["listings"]] == search_inventory["ids"][6:]
    empty = search_chat(api, actors, model, {"city": "No matching city"})
    assert empty["messages"][-1]["listings"] == []
    assert empty["messages"][-1]["listing_search"] == {"page": 1, "page_size": 6, "total": 0, "cards_only": True}


def test_nonsearch_actions_and_errors_keep_assistant_text(api, actors, model, search_inventory):
    for extra in [("get_home", {"listing_id": search_inventory["ids"][0]}),
                  ("prepare_save_listing", {"listing_id": search_inventory["ids"][0]}),
                  ("get_home", {"listing_id": []}),
                  ("search_homes", {"min_price": "800", "max_price": "600"})]:
        model.steps = [("search_homes", search_inventory["filters"]), extra, "Important explanation stays visible."]
        response = chat(api, actors)
        assert response.status_code == 200, response.text
        assert response.json()["messages"][-1]["listing_search"]["cards_only"] is False
    model.steps = ["How can I help?"]
    response = chat(api, actors)
    assert response.json()["messages"][-1]["listing_search"] is None


def test_legacy_messages_have_no_search_and_no_pagination(api, actors, engine, model, search_inventory):
    thread = search_chat(api, actors, model, search_inventory["filters"])
    with Session(engine) as session, session.begin():
        session.get(AssistantMessage, UUID(thread["messages"][-1]["id"])).listing_search = None
    detail = api.get(f"{BASE}/threads/{thread['id']}", headers=actors["tenant"])
    assert detail.status_code == 200
    assert detail.json()["messages"][-1]["listing_search"] is None
    assert api.get(page_path(thread), headers=actors["tenant"]).status_code == 404


def test_visible_page_context_is_server_owned_and_not_displayed(api, actors, inventory, engine, model, search_inventory):
    thread = search_chat(api, actors, model, search_inventory["filters"])
    context = {"message_id": thread["messages"][-1]["id"], "page": 2}
    model.steps = ["Which details would you like to know?"]
    response = api.post(BASE+"/chat", headers=actors["tenant"], json={"thread_id": thread["id"],
        "message": "Tell me about the first one.", "listing_search_context": context})
    assert response.status_code == 200, response.text
    instructions = model.inputs[-1][0]
    assert "Current tenant search page" in instructions
    assert instructions.index(search_inventory["ids"][6]) < instructions.index(search_inventory["ids"][7])
    assert response.json()["messages"][-2]["content"] == "Tell me about the first one."
    missing_thread = api.post(BASE+"/chat", headers=actors["tenant"],
        json={"message": "The first one", "listing_search_context": context})
    assert missing_thread.status_code == 422
    for invalid in ({**context, "message_id": str(uuid4())}, {**context, "message_id": thread["messages"][0]["id"]}):
        result = api.post(BASE+"/chat", headers=actors["tenant"], json={"thread_id": thread["id"],
            "message": "The first one", "listing_search_context": invalid})
        assert result.status_code == 404
    other = headers(token_for(api, engine, inventory, "other"))
    assert api.post(BASE+"/chat", headers=other, json={"thread_id": thread["id"],
        "message": "The first one", "listing_search_context": context}).status_code == 404
    forged = api.post(BASE+"/chat", headers=actors["tenant"], json={"thread_id": thread["id"],
        "message": "The first one", "listing_search_context": {**context, "filters": {"city": "Rome"}}})
    assert forged.status_code == 422
    model.steps = ["A separate conversation."]
    other_thread = chat(api, actors, "Start a different conversation").json()
    assert api.post(BASE+"/chat", headers=actors["tenant"], json={"thread_id": other_thread["id"],
        "message": "The first one", "listing_search_context": context}).status_code == 404
