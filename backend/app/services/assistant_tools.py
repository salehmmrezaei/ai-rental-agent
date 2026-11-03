"""All agent capabilities are reads or proposals; only HTTP confirmation writes rentals."""
from dataclasses import dataclass, field
from decimal import Decimal
import logging
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import RentalRequest, RentalContract, Visit, Conversation, Message, SavedListing, User, Listing, RentalUnit, Property
from app.repositories import inventory as inventory_repo, operations as repo
from app.schemas.inventory import Search
from app.schemas.operations import ApplicationCreate, VisitCreate, SavedCreate, ConversationCreate, MessageCreate
from app.services import inventory, operations, reporting, transactions as tx
from app.services import agency_assistant, landlord_assistant

logger = logging.getLogger(__name__)


def listing_reference(data):
    return {key: data[key] for key in
            ("id", "title", "city", "kind", "unit_name", "monthly_rent", "available_now")}


def visit_reference(data):
    reference = {key: data[key] for key in ("id", "property_title", "unit_name", "tenant_name",
        "status", "requested_at", "scheduled_at", "duration_minutes", "note")}
    if reference["note"] is not None:
        reference["note"] = reference["note"][:1000]
    return reference


@dataclass
class Proposal:
    kind: str
    summary: str
    payload: dict
    id: UUID = field(default_factory=uuid4)


def json_value(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


@dataclass
class ToolContext:
    bind: object
    actor: tx.Actor
    role: str = "tenant"
    proposals: list[Proposal] = field(default_factory=list)
    listings: dict = field(default_factory=dict)
    listing_search: dict | None = None
    visit_search: dict | None = None
    agency_record_collections: list[str] = field(default_factory=list)
    search_listings: list = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    tool_errors: bool = False
    calls: int = 0

    def call(self, name, operation, roles=None):
        self.calls += 1
        self.tool_names.append(name)
        if self.calls > 16:
            self.tool_errors = True
            return {"error": "tool_limit", "message": "Tool limit reached. Ask a narrower question."}
        try:
            with Session(self.bind) as session:
                user = tx.authenticate(session, self.actor, roles or ({self.role} & {"tenant", "landlord", "admin"}))
                result = operation(session, user)
            logger.info("assistant_tool name=%s outcome=ok", name)
            return json_value(result)
        except ApiError as exc:
            self.tool_errors = True
            if exc.status_code in (401, 403):
                raise
            logger.info("assistant_tool name=%s outcome=%s", name, exc.code)
            return {"error": exc.code, "message": exc.detail}
        except (ValidationError, ValueError):
            self.tool_errors = True
            logger.info("assistant_tool name=%s outcome=invalid_input", name)
            return {"error": "invalid_input", "message": "Check the identifiers, dates, and required fields."}

    def listing(self, session, lid):
        view = inventory.public_view(session, *inventory.public_listing(session, UUID(str(lid))))
        data = view.model_dump(mode="json", exclude={"property_id", "rental_unit_id", "images"})
        data["description"] = data["description"][:500]
        # References are generated from database results, never model-supplied URLs.
        if len(self.listings) < 8 or data["id"] in self.listings:
            self.listings[data["id"]] = listing_reference(data)
        return data

    def search(self, **values):
        def read(session, user):
            filters = Search(**values, page_size=6)
            rows, total = inventory_repo.search(session, filters)
            items = [self.listing(session, row[0].id) for row in rows]
            if self.role == "tenant":
                self.search_listings = [listing_reference(item) for item in items]
                self.listings = {item["id"]: item for item in self.search_listings}
                self.listing_search = {
                    "filters": filters.model_dump(mode="json", exclude={"page", "page_size"}),
                    "page": filters.page, "page_size": filters.page_size, "total": total,
                }
            return {"total": total, "items": items, "page": filters.page, "page_size": filters.page_size}
        return self.call("search_homes", read)

    def detail(self, listing_id):
        return self.call("get_home", lambda s, u: self.listing(s, listing_id))

    def availability(self, listing_id, start_date, end_date):
        def read(session, user):
            dates = Search(start_date=start_date, end_date=end_date)
            listing, unit, _ = inventory.public_listing(session, UUID(listing_id))
            available, reason = inventory.availability(session, listing, unit, dates.start_date, dates.end_date)
            self.listing(session, listing.id)
            return {"listing_id": str(listing.id), "start_date": start_date, "end_date": end_date,
                    "available": available, "reason": reason}
        return self.call("check_availability", read)

    def rentals(self):
        def read(session, user):
            applications = session.scalars(repo.applications(user).order_by(RentalRequest.created_at.desc()).limit(10)).all()
            contracts = session.execute(repo.contracts(user).order_by(RentalContract.created_at.desc()).limit(10)).all()
            visits = session.scalars(repo.visits(user).order_by(Visit.created_at.desc()).limit(10)).all()
            saved = session.scalars(select(SavedListing).where(SavedListing.tenant_id == user.id)
                                    .order_by(SavedListing.created_at.desc()).limit(6)).all()
            saved_homes = []
            for item in saved:
                try:
                    saved_homes.append(self.listing(session, item.listing_id))
                except ApiError:
                    saved_homes.append({"id": str(item.listing_id), "status": "unpublished"})
            # Free-text notes and personal profile data are unnecessary for these tools.
            return {"statistics": reporting.dashboard(session, user).model_dump(mode="json"),
                "applications": [repo.application_view(session, r).model_dump(mode="json", exclude={"tenant_id", "note", "review_note"}) for r in applications],
                "contracts": [repo.contract_view(*r, user).model_dump(mode="json", exclude={"tenant_id"}) for r in contracts],
                "visits": [repo.visit_view(r, user, session).model_dump(mode="json", exclude={"tenant_id", "note", "agency_note"}) for r in visits],
                "saved_homes": saved_homes, "limit_per_collection": 10}
        return self.call("get_my_rentals", read, {"tenant"})

    def agency_records(self, **values):
        self.agency_record_collections.append(values.get("collection"))
        def read(session, user):
            result = agency_assistant.records(session, user, **values)
            if values.get("collection") == "visits":
                self.visit_search = {
                    "items": [visit_reference(item) for item in result["items"]],
                    "filters": {key: value for key, value in values.items() if key != "page"},
                    "page": result["page"], "page_size": result["page_size"], "total": result["total"],
                }
            if values.get("collection") == "listings" and result["items"]:
                identifiers = [UUID(item["id"]) for item in result["items"]]
                rows = session.execute(select(Listing, RentalUnit, Property).select_from(Listing)
                    .join(RentalUnit, RentalUnit.id == Listing.rental_unit_id)
                    .join(Property, Property.id == RentalUnit.property_id)
                    .where(Listing.id.in_(identifiers))).all()
                references = {str(listing.id): {
                    "id": str(listing.id), "title": prop.title, "city": prop.city,
                    "kind": unit.kind, "unit_name": unit.name, "monthly_rent": str(unit.monthly_rent),
                    "status": listing.status, "available_from": listing.available_from.isoformat(),
                    "available_until": listing.available_until.isoformat() if listing.available_until else None,
                } for listing, unit, prop in rows}
                # Preserve the tool's ordering and derive private links only from authorized database rows.
                for identifier in identifiers:
                    key = str(identifier)
                    if len(self.listings) < 8 or key in self.listings:
                        self.listings[key] = references[key]
            return result
        return self.call("get_agency_records", read, {"admin"})

    def agency_report(self, **values):
        return self.call("get_agency_report", lambda s, u: agency_assistant.report(s, u, **values), {"admin"})

    def landlord_records(self, **values):
        return self.call("get_landlord_records", lambda s, u: landlord_assistant.records(s, u, **values), {"landlord"})

    def landlord_report(self, **values):
        return self.call("get_landlord_report", lambda s, u: landlord_assistant.report(s, u, **values), {"landlord"})

    def landlord_availability(self, **values):
        return self.call("check_my_unit_availability", lambda s, u: landlord_assistant.availability(s, u, **values), {"landlord"})

    def conversations(self, conversation_id=None):
        def read(session, user):
            if conversation_id:
                c = operations.owned_conversation(session, user, UUID(conversation_id))
                rows = session.execute(select(Message, User.role).join(User, User.id == Message.sender_id)
                    .where(Message.conversation_id == c.id).order_by(Message.created_at.desc(), Message.id).limit(10)).all()
                messages = [repo.message_view(m, role).model_dump(mode="json") for m, role in reversed(rows)]
                for message in messages:
                    message["truncated"] = len(message["body"]) > 2000
                    message["body"] = message["body"][:2000]
                return {"id": str(c.id), "subject": c.subject, "messages": messages}
            rows = session.scalars(repo.conversations(user).order_by(Conversation.updated_at.desc()).limit(10)).all()
            return {"items": [{"id": str(c.id), "subject": c.subject} for c in rows]}
        return self.call("get_agency_conversations", read, {"tenant", "admin"})

    def propose(self, kind, values):
        def prepare(session, user):
            data, summary = validate_proposal(session, user, kind, values)
            payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
            if kind == "apply":
                _, unit, _ = inventory.public_listing(session, data.listing_id)
                payload["quoted_monthly_rent"] = str(unit.monthly_rent)
            for existing in self.proposals:
                if existing.kind == kind and existing.payload == payload:
                    return {"action_id": str(existing.id), "status": "requires_confirmation", "summary": existing.summary}
            if len(self.proposals) >= 3:
                raise ApiError(422, "action_limit", "Prepare at most three actions per reply")
            proposal = Proposal(kind, summary, payload)
            self.proposals.append(proposal)
            if kind in {"save_listing", "apply", "request_visit"}:
                self.listing(session, payload["listing_id"])
            return {"action_id": str(proposal.id), "status": "requires_confirmation", "summary": summary}
        return self.call("prepare_" + kind, prepare)


def validate_proposal(session, user, kind, values):
    if kind in agency_assistant.KINDS:
        return agency_assistant.validate(session, user, kind, values)
    if user.role != "tenant":
        raise ApiError(403, "forbidden", "Tenant role required for this action")
    if kind in {"save_listing", "apply", "request_visit"}:
        cls = {"save_listing": SavedCreate, "apply": ApplicationCreate, "request_visit": VisitCreate}[kind]
        data = cls.model_validate(values)
        listing, unit, prop = inventory.public_listing(session, data.listing_id)
        name = f"{prop.title} · {unit.name} ({prop.city})"
        if kind == "apply":
            operations.check_dates(listing, unit, session, data.start_date, data.end_date)
            summary = f"Submit an application for {name}, {data.start_date} to {data.end_date}. Current rent €{unit.monthly_rent}/month. Agency approval is required."
        elif kind == "request_visit":
            if data.requested_at <= operations.now():
                raise ApiError(422, "past_visit", "Requested visit must be in the future")
            summary = f"Request a visit to {name} at {data.requested_at.isoformat()}. The agency will confirm the schedule."
        else:
            summary = f"Save {name} to your saved homes."
        return data, summary
    if kind == "contact_agency":
        data = ConversationCreate.model_validate(values)
        return data, f"Open an agency conversation: {data.subject}"
    if kind == "send_message":
        cid = UUID(values["conversation_id"])
        conversation = operations.owned_conversation(session, user, cid)
        data = MessageCreate.model_validate({"body": values["body"]})
        return {"conversation_id": str(cid), "body": data.body}, f"Send a message to the agency in: {conversation.subject}"
    if kind == "withdraw_application":
        rid = UUID(values["application_id"])
        request = session.scalar(repo.applications(user).where(RentalRequest.id == rid))
        if request is None:
            raise ApiError(404, "not_found", "Application not found")
        if request.status not in {"submitted", "reviewing"}:
            raise ApiError(409, "invalid_transition", "Only pending applications can be withdrawn")
        context = repo.rental_context(session, request.rental_unit_id)
        return {"application_id": str(rid)}, f"Withdraw your application for {context['property_title']} · {context['unit_name']}, {request.start_date} to {request.end_date}."
    if kind == "cancel_visit":
        vid = UUID(values["visit_id"])
        visit = session.scalar(repo.visits(user).where(Visit.id == vid))
        if visit is None:
            raise ApiError(404, "not_found", "Visit not found")
        if visit.status not in {"requested", "scheduled"}:
            raise ApiError(409, "invalid_transition", "Only upcoming visits can be cancelled")
        context = repo.rental_context(session, visit.rental_unit_id)
        return {"visit_id": str(vid)}, f"Cancel your visit to {context['property_title']} · {context['unit_name']} at {(visit.scheduled_at or visit.requested_at).isoformat()}."
    raise ApiError(422, "unknown_action", "Unsupported assistant action")


def execute_action(session, user, kind, payload):
    if kind in agency_assistant.KINDS:
        return agency_assistant.execute(session, user, kind, payload)
    if user.role != "tenant":
        raise ApiError(403, "forbidden", "Tenant role required for this action")
    # Call the existing services so locks, publication, dates and ownership are rechecked.
    if kind == "save_listing":
        return operations.save_listing(session, user, SavedCreate.model_validate(payload).listing_id)
    if kind == "apply":
        data = ApplicationCreate.model_validate({k: v for k, v in payload.items() if k != "quoted_monthly_rent"})
        _, unit, _ = operations.lock_published(session, data.listing_id)
        if unit.monthly_rent != Decimal(payload["quoted_monthly_rent"]):
            raise ApiError(409, "listing_changed", "The listing rent changed. Ask the assistant to prepare a new application.")
        return operations.create_application(session, user, data)
    if kind == "request_visit":
        return operations.create_visit(session, user, VisitCreate.model_validate(payload))
    if kind == "contact_agency":
        return operations.create_conversation(session, user, ConversationCreate.model_validate(payload))
    if kind == "send_message":
        return operations.send_message(session, user, UUID(payload["conversation_id"]), MessageCreate(body=payload["body"]))
    if kind == "withdraw_application":
        return operations.application_action(session, user, UUID(payload["application_id"]), "withdrawn")
    if kind == "cancel_visit":
        return operations.cancel_visit(session, user, UUID(payload["visit_id"]))
    raise ApiError(422, "unknown_action", "Unsupported assistant action")
