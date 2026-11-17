"""Deterministic, read-only public demonstration with disposable visitor history.

This module never constructs a model client, creates assistant database records,
or prepares actions. Database reads go through the application's existing scoped
queries. History is process-local, bounded and expires after thirty minutes.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from threading import RLock
from time import monotonic
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.errors import ApiError
from app.models import Property, RentalUnit, RentalRequest, RentalContract, Visit, SavedListing
from app.repositories import inventory as inventory_repo, operations as operations_repo
from app.schemas.assistant import ListingReference, MessageRead, ThreadDetail, ThreadRead, VisitReference
from app.schemas.inventory import Page, Search
from app.services import agency_assistant, inventory, landlord_assistant, reporting
from app.services.assistant_tools import listing_reference, visit_reference

LABEL = "Simulated AI Assistant — no external model is used. "
TTL_SECONDS = 30 * 60
MAX_SESSIONS = 512
MAX_THREADS_PER_SESSION = 3
MAX_TOTAL_THREADS = 768
MAX_TURNS = 12
WRITE_REQUEST = re.compile(
    r"\b(apply|save|delete|remove|create|add|edit|update|change|submit|approve|reject|"
    r"publish|unpublish|withdraw|cancel|schedule|reschedule|send|reply|contact|upload|register|"
    r"book|reserve|pay|terminate|activate|deactivate)\b",
    re.IGNORECASE,
)
IDENTIFIER = r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
CITIES = {"bologna": "Bologna", "milan": "Milan", "milano": "Milan",
          "rome": "Rome", "roma": "Rome", "florence": "Florence", "firenze": "Florence"}


@dataclass
class VisitorHistory:
    expires_at: float
    threads: OrderedDict = field(default_factory=OrderedDict)


class DemoAssistantStore:
    def __init__(self):
        self.lock = RLock()
        self.sessions = OrderedDict()

    def visitor(self, user, *, create=False):
        session_id = getattr(user, "demo_session_id", None)
        if not session_id:
            raise ApiError(401, "demo_session_required", "Choose a demo role to start a simulated conversation.")
        key = (session_id, str(user.id), user.role)
        current = monotonic()
        expired = [k for k, state in self.sessions.items() if state.expires_at <= current]
        for old_key in expired:
            del self.sessions[old_key]
        if expired:
            _prune_filters()
        state = self.sessions.get(key)
        if state is None and create:
            while len(self.sessions) >= MAX_SESSIONS:
                self.sessions.popitem(last=False)
            state = VisitorHistory(current + TTL_SECONDS)
            self.sessions[key] = state
        if state is not None:
            self.sessions.move_to_end(key)
        return state

    def reserve_thread(self, state):
        while len(state.threads) >= MAX_THREADS_PER_SESSION:
            state.threads.popitem(last=False)
        while sum(len(v.threads) for v in self.sessions.values()) >= MAX_TOTAL_THREADS:
            oldest = next(v for v in self.sessions.values() if v.threads)
            oldest.threads.popitem(last=False)


_store = DemoAssistantStore()


def reset_demo_state():
    with _store.lock:
        _store.sessions.clear()
        _search_filters.clear()


def discard_demo_session(session_id):
    with _store.lock:
        for key in [key for key in _store.sessions if key[0] == session_id]:
            del _store.sessions[key]
        _prune_filters()


def _owned(user, thread_id):
    state = _store.visitor(user)
    thread = state.threads.get(thread_id) if state else None
    if thread is None:
        raise ApiError(404, "not_found", "Simulated conversation expired or was not found.")
    return thread


def threads(db, user):
    with _store.lock:
        state = _store.visitor(user)
        return [ThreadRead(id=t.id, title=t.title, updated_at=t.updated_at)
                for t in reversed(list(state.threads.values()))] if state else []


def thread_detail(db, user, thread_id):
    with _store.lock:
        return _owned(user, thread_id).model_copy(deep=True)


def _message(user, thread_id, message_id, field_name):
    thread = _owned(user, thread_id)
    message = next((m for m in thread.messages if m.id == message_id and m.role == "assistant"), None)
    if message is None or getattr(message, field_name) is None:
        raise ApiError(404, "not_found", "Simulated search was not found.")
    return message


def _search(db, filters, page=1):
    parsed = Search(**filters, page=page, page_size=6)
    rows, total = inventory_repo.search(db, parsed)
    items = [ListingReference(**listing_reference(inventory.public_view(db, *row).model_dump(mode="json")))
             for row in rows]
    return Page[ListingReference](items=items, page=page, page_size=6, total=total)


def listing_search_page(db, user, thread_id, message_id, page):
    if user.role != "tenant":
        raise ApiError(403, "forbidden", "Tenant role required")
    with _store.lock:
        message = _message(user, thread_id, message_id, "listing_search")
        # Filters are private server state, never supplied by the browser.
        filters = dict(_search_filters[(user.demo_session_id, thread_id, message.id)])
    return _search(db, filters, page)


def visit_search_page(db, user, thread_id, message_id, page):
    agency_assistant.require_admin(user)
    with _store.lock:
        message = _message(user, thread_id, message_id, "visit_search")
        filters = dict(_search_filters[(user.demo_session_id, thread_id, message.id)])
    result = agency_assistant.records(db, user, **filters, page=page)
    return Page[VisitReference](items=[VisitReference(**visit_reference(item)) for item in result["items"]],
                                page=page, page_size=6, total=result["total"])


def _examples(role):
    return {
        "tenant": 'Try “Find rooms in Bologna under €700”, “Check my applications”, or “Show my visits”.',
        "landlord": 'Try “Show my properties”, “Show my draft listings”, or “Give me an occupancy report”.',
        "admin": 'Try “Show listings waiting for approval”, “Show requested visits”, or “Give me an agency overview”.',
    }[role]


def _summary(items, empty="There are no matching synthetic records."):
    if not items:
        return empty
    lines = []
    for item in items[:6]:
        name = item.get("property_title") or item.get("title") or item.get("subject") or item.get("name") or "Record"
        unit = item.get("unit_name")
        status = item.get("status")
        line = str(name)[:160] + (f" · {str(unit)[:80]}" if unit else "")
        if status:
            line += f" — {status}"
        if item.get("start_date"):
            line += f", {item['start_date']} to {item['end_date']}"
        if item.get("monthly_rent"):
            line += f", €{item['monthly_rent']}/month"
        lines.append(line)
    return "\n".join(lines)


def _filters(text):
    city = next((value for alias, value in CITIES.items() if re.search(rf"\b{alias}\b", text)), None)
    values = {"sort": "price_asc"}
    if city:
        values["city"] = city
    elif match := re.search(r"\bin\s+([a-z][a-z -]{1,40}?)(?=\s+(?:under|below|from|between|for|with|up to)|[,.!?]|$)", text):
        values["city"] = match.group(1).strip().title()
    if re.search(r"\brooms?\b", text):
        values["property_type"] = "room"
    elif re.search(r"\bapartments?\b", text):
        values["property_type"] = "apartment"
    amount = re.search(r"(?:under|below|up to|maximum|max|budget(?: of)?)\s*(?:€|eur\s*)?(\d+(?:[.,]\d{1,2})?)", text)
    if amount:
        values["max_price"] = amount.group(1).replace(",", ".")
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if dates:
        if len(dates) != 2:
            raise ValueError("Provide exactly two ISO dates")
        values.update(start_date=dates[0], end_date=dates[1])
    return Search(**values).model_dump(mode="json", exclude_none=True, exclude={"page", "page_size"})


def _tenant_records(db, user, collection):
    if collection == "applications":
        records = db.scalars(operations_repo.applications(user).order_by(RentalRequest.created_at.desc()).limit(6))
        return [operations_repo.application_view(db, row).model_dump(mode="json") for row in records]
    if collection == "contracts":
        records = db.execute(operations_repo.contracts(user).order_by(RentalContract.created_at.desc()).limit(6))
        return [operations_repo.contract_view(*row, user).model_dump(mode="json") for row in records]
    records = db.scalars(operations_repo.visits(user).order_by(Visit.created_at.desc()).limit(6))
    return [operations_repo.visit_view(row, user, db).model_dump(mode="json") for row in records]


def _respond(db, user, text):
    normalized = text.casefold()
    empty = {"listings": [], "listing_search": None, "visit_search": None, "filters": None}
    if re.search(r"\b(how|workflow|explain)\b", normalized):
        return {**empty, "content": LABEL + "Casa separates tenant rental requests, landlord inventory management and agency moderation. "
                "Landlords submit draft listings; the agency reviews and publishes them. Tenants request visits or apply; "
                "agency approval creates a contract after checking date conflicts. Every live agent change needs explicit confirmation. "
                "This demonstration only reads fictional data. " + _examples(user.role)}
    if WRITE_REQUEST.search(normalized):
        return {**empty, "content": LABEL + "This public demo keeps shared fictional records read-only. "
                "A normal Casa workflow prepares an exact review card, then checks authorization and availability again "
                "when the user confirms. No action was prepared or performed here. " + _examples(user.role)}
    if re.search(r"\b(occupancy|vacan\w*|contracted rent)\b", normalized) and user.role in {"admin", "landlord"}:
        report = reporting.occupancy(db, user)
        s = report.summary
        return {**empty, "content": LABEL + f"As of {s.as_of}: {s.properties} properties, {s.total_units} physical units, "
                f"{s.occupied_units} occupied, {s.reserved_units} reserved and {s.available_units} available. "
                f"Contracted monthly rent is €{s.contracted_monthly_rent}; this is not a payment or collection report."}
    if re.search(r"\b(overview|dashboard|statistics|summary)\b", normalized):
        stats = reporting.dashboard(db, user)
        counts = "; ".join(f"{name.replace('_', ' ')}: {value}" for name, value in stats.counts.items())
        return {**empty, "content": LABEL + "Current synthetic workspace: " + counts + "."}
    listing_match = re.search(r"(?:home listing|listing)\s+id\s*[: ]\s*" + IDENTIFIER, normalized)
    if user.role == "tenant" and listing_match:
        view = inventory.public_view(db, *inventory.public_listing(db, UUID(listing_match.group(1))))
        availability_text = "Check a complete rental interval before applying."
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", normalized)
        if dates:
            try:
                if len(dates) != 2:
                    raise ValueError("Two rental dates required")
                interval = Search(start_date=dates[0], end_date=dates[1])
            except (ValueError, ValidationError):
                return {**empty, "content": LABEL + "Provide two valid ISO rental dates with the end after the start."}
            listing, unit, _ = inventory.public_listing(db, view.id)
            available, reason = inventory.availability(db, listing, unit, interval.start_date, interval.end_date)
            availability_text = (f"For {interval.start_date} to {interval.end_date}: " +
                ("currently available. This read does not reserve the home." if available else
                 f"unavailable ({reason.replace('_', ' ')})."))
        return {**empty, "content": LABEL + f"{view.title} · {view.unit_name} in {view.city}: €{view.monthly_rent}/month, "
                f"deposit €{view.deposit}, available from {view.available_from}. " + availability_text,
                "listings": [listing_reference(view.model_dump(mode="json"))]}
    if user.role == "tenant":
        collection = next((name for pattern, name in [(r"applications?", "applications"), (r"contracts?|my rentals?", "contracts"),
                                                      (r"visits?", "visits")] if re.search(rf"\b(?:{pattern})\b", normalized)), None)
        if collection:
            return {**empty, "content": LABEL + f"Your synthetic {collection} (up to six recent records):\n" +
                    _summary(_tenant_records(db, user, collection))}
        if re.search(r"\b(saved|favourites?|favorites?)\b", normalized):
            saved = db.scalars(select(SavedListing).where(SavedListing.tenant_id == user.id)
                               .order_by(SavedListing.created_at.desc()).limit(6))
            cards = []
            for row in saved:
                try:
                    cards.append(listing_reference(inventory.public_view(db, *inventory.public_listing(db, row.listing_id)).model_dump(mode="json")))
                except ApiError as exc:
                    if exc.status_code != 404:
                        raise
            return {**empty, "content": LABEL + f"Here are {len(cards)} of your saved published synthetic homes.", "listings": cards}
        if re.search(r"\b(find|search|homes?|rooms?|apartments?|listings?)\b", normalized):
            try:
                filters = _filters(normalized)
            except (ValueError, ValidationError):
                return {**empty, "content": LABEL + "Use a valid EUR budget and, if needed, two ISO dates such as "
                        "2027-02-01 to 2027-05-01. The end date must follow the start date. " + _examples(user.role)}
            page = _search(db, filters)
            description = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in filters.items() if key != "sort") or "all published homes"
            return {**empty, "content": LABEL + f"Found {page.total} published synthetic homes ({description}). "
                    "These are database results. Availability for an entire stay needs both rental dates.",
                    "listings": page.items, "listing_search": {"page": 1, "page_size": 6, "total": page.total, "cards_only": False},
                    "filters": filters}
    else:
        collection = next((name for pattern, name in [(r"visits?", "visits"), (r"applications?", "applications"),
                (r"listings?", "listings"), (r"contracts?|rentals?", "contracts"), (r"units?|rooms?", "units"),
                (r"properties|portfolio|property", "properties"), (r"conversations?|messages?|inbox", "conversations")]
                if re.search(rf"\b(?:{pattern})\b", normalized)), None)
        allowed = {"properties", "units", "listings", "contracts"} if user.role == "landlord" else {
            "properties", "units", "listings", "contracts", "visits", "applications", "conversations"}
        if collection in allowed:
            filters = {"collection": collection}
            if collection == "listings":
                status = next((s for s in ["draft", "submitted", "approved", "rejected", "published", "unpublished"]
                               if re.search(rf"\b{s}\b", normalized)), None)
                if "waiting" in normalized or "approval" in normalized or "review queue" in normalized:
                    status = "submitted"
                if status:
                    filters["status"] = status
            if collection == "visits" and "requested" in normalized:
                filters["status"] = "requested"
            if collection == "applications" and "pending" in normalized:
                pending = [agency_assistant.records(db, user, collection="applications", status=status)
                           for status in ("submitted", "reviewing")]
                records = {"items": [item for page in pending for item in page["items"]][:6],
                           "total": sum(page["total"] for page in pending)}
            else:
                if collection == "applications":
                    status = next((s for s in ["submitted", "reviewing", "approved", "rejected", "withdrawn"]
                                   if re.search(rf"\b{s}\b", normalized)), None)
                    if status:
                        filters["status"] = status
                records = (landlord_assistant.records if user.role == "landlord" else agency_assistant.records)(db, user, **filters)
            result = {**empty, "content": LABEL + f"Your authorized synthetic {collection}: {records['total']} matching records.\n" + _summary(records["items"])}
            if user.role == "admin" and collection == "visits":
                result.update(visit_search={"items": [visit_reference(item) for item in records["items"]],
                    "page": 1, "page_size": 6, "total": records["total"], "cards_only": False}, filters=filters)
            if user.role == "admin" and collection == "listings":
                # Agency detail cards are built from authorized database rows, not supplied URLs.
                for item in records["items"]:
                    unit = db.get(RentalUnit, UUID(item["rental_unit_id"]))
                    prop = db.get(Property, unit.property_id)
                    result["listings"].append({"id": item["id"], "title": prop.title, "city": prop.city,
                        "kind": unit.kind, "unit_name": unit.name, "monthly_rent": str(unit.monthly_rent),
                        "status": item["status"], "available_from": item["available_from"],
                        "available_until": item["available_until"]})
            return result
    return {**empty, "content": LABEL + "I support a bounded set of guided rental searches and authorized workspace summaries. "
            "I cannot interpret every request or make changes to shared records. " + _examples(user.role)}


# Search filters live with the bounded message state and are pruned on each write.
_search_filters = {}


def _prune_filters():
    alive = {(key[0], t.id, m.id) for key, state in _store.sessions.items()
             for t in state.threads.values() for m in t.messages if m.role == "assistant"}
    for key in list(_search_filters):
        if key not in alive:
            del _search_filters[key]


def chat(db, user, data):
    with _store.lock:
        state = _store.visitor(user, create=True)
        initial_state = state
        thread = _owned(user, data.thread_id) if data.thread_id else None
        version = len(thread.messages) if thread else 0
        if version >= MAX_TURNS * 2:
            raise ApiError(422, "chat_limit", "This simulated conversation is full. Start a new chat.")
    message = data.message
    if data.listing_search_context:
        visible = listing_search_page(db, user, data.thread_id, data.listing_search_context.message_id, data.listing_search_context.page)
        ordinal = re.search(r"\b(first|second|third|fourth|fifth|sixth)\b", data.message.casefold())
        if ordinal:
            index = ["first", "second", "third", "fourth", "fifth", "sixth"].index(ordinal.group(1))
            if index < len(visible.items):
                message += f"\nCurrent home listing ID: {visible.items[index].id}"
    if data.visit_search_context:
        visit_search_page(db, user, data.thread_id, data.visit_search_context.message_id, data.visit_search_context.page)
    answer = _respond(db, user, message)
    with _store.lock:
        state = _store.visitor(user)
        if state is not initial_state:
            # Logout, reset, expiry or capacity eviction while a query was in
            # flight must never recreate a discarded visitor conversation.
            raise ApiError(409, "demo_history_reset", "This demo conversation was cleared. Start a new chat.")
        if data.thread_id:
            thread = _owned(user, data.thread_id)
            if len(thread.messages) != version:
                raise ApiError(409, "chat_changed", "This chat changed in another request. Reload and try again.")
        else:
            _store.reserve_thread(state)
            thread = ThreadDetail(id=uuid4(), title=data.message[:100], updated_at=datetime.now(timezone.utc), messages=[])
            state.threads[thread.id] = thread
        sent_at = datetime.now(timezone.utc)
        response = MessageRead(id=uuid4(), role="assistant", content=answer["content"], listings=answer["listings"],
            listing_search=answer["listing_search"], visit_search=answer["visit_search"], created_at=sent_at + timedelta(microseconds=1))
        thread.messages.extend([MessageRead(id=uuid4(), role="user", content=data.message, created_at=sent_at), response])
        thread.updated_at = response.created_at
        state.threads.move_to_end(thread.id)
        if answer["filters"] is not None:
            _search_filters[(user.demo_session_id, thread.id, response.id)] = answer["filters"]
        _prune_filters()
        return thread.model_copy(deep=True)
