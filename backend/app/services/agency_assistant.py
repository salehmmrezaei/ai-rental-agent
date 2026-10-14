"""Bounded agency reads and validated, explicitly confirmed agency requests."""
from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select

from app.errors import ApiError
from app.models import Property, RentalUnit, Listing, RentalRequest, RentalContract, Visit, Conversation, User
from app.repositories import inventory as inventory_repo, operations as repo
from app.schemas import inventory as inv, operations as ops
from app.services import inventory, operations, reporting

KINDS = {"create_property", "update_property", "create_unit", "update_unit", "create_listing",
         "update_listing", "change_listing_status", "review_application", "approve_application",
         "reject_application", "update_visit", "send_tenant_message"}
LISTING_TRANSITIONS = {"submitted": {"draft", "rejected"},
    "draft": {"submitted", "approved", "unpublished", "rejected"}, "approved": {"submitted"},
    "rejected": {"submitted"}, "published": {"approved", "unpublished"}, "unpublished": {"published"}}


def require_admin(user):
    if user.role != "admin":
        raise ApiError(403, "forbidden", "Agency role required")


def bounded(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: bounded(item) for key, item in value.items() if key not in {"images", "cover_image"}}
    if isinstance(value, list):
        return [bounded(item) for item in value]
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + " [truncated]"
    return value


def one(session, model, identifier, label):
    record = session.get(model, UUID(str(identifier)))
    if record is None:
        raise ApiError(404, "not_found", f"{label} not found")
    return record


def records(session, user, collection, record_id=None, status=None, query=None, page=1):
    require_admin(user)
    if page < 1 or page > 10000 or (query is not None and len(query) > 100):
        raise ValueError("Invalid page or query")
    models = {"properties": Property, "units": RentalUnit, "listings": Listing,
              "applications": RentalRequest, "contracts": RentalContract, "visits": Visit,
              "conversations": Conversation, "landlords": User, "agents": User}
    if collection not in models:
        raise ValueError("Invalid collection")
    model = models[collection]
    statement = select(model)
    if collection in {"landlords", "agents"}:
        statement = statement.where(User.role == ("landlord" if collection == "landlords" else "admin"), User.is_active.is_(True))
    if record_id:
        statement = statement.where(model.id == UUID(record_id))
    if status:
        statuses = {"listings": inv.ListingStatus, "applications": ops.ApplicationStatus,
                    "contracts": ops.ContractStatus, "visits": ops.VisitStatus}
        from typing import get_args
        if collection not in statuses or status not in get_args(statuses[collection]):
            raise ValueError("Invalid status")
        statement = statement.where(model.status == status)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        if collection in {"landlords", "agents"}:
            statement = statement.where(User.full_name.ilike(pattern, escape="\\"))
        elif collection == "conversations":
            statement = statement.join(User, User.id == Conversation.tenant_id).where(or_(
                Conversation.subject.ilike(pattern, escape="\\"), User.full_name.ilike(pattern, escape="\\")))
        else:
            if collection == "units":
                statement = statement.join(Property, Property.id == RentalUnit.property_id)
            elif collection != "properties":
                statement = statement.join(RentalUnit, RentalUnit.id == model.rental_unit_id).join(Property, Property.id == RentalUnit.property_id)
            filters = [Property.title.ilike(pattern, escape="\\"), Property.city.ilike(pattern, escape="\\")]
            if collection != "properties":
                filters.append(RentalUnit.name.ilike(pattern, escape="\\"))
            if collection in {"applications", "contracts", "visits"}:
                statement = statement.join(User, User.id == model.tenant_id)
                filters.append(User.full_name.ilike(pattern, escape="\\"))
            statement = statement.where(or_(*filters))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(model.created_at.desc(), model.id).offset((page-1)*6).limit(6)).all()
    if record_id and not rows:
        raise ApiError(404, "not_found", "Agency record not found")
    items = []
    for record in rows:
        if collection == "properties":
            view = inventory.property_view(session, record, detail=bool(record_id))
        elif collection == "units":
            view = inventory.unit_view(session, record)
        elif collection == "listings":
            view = inv.ListingRead.model_validate(record).model_dump(mode="json")
            view.update(repo.rental_context(session, record.rental_unit_id))
            view["property_id"] = str(view["property_id"])
            view["monthly_rent"] = str(session.get(RentalUnit, record.rental_unit_id).monthly_rent)
        elif collection == "applications":
            view = repo.application_view(session, record)
        elif collection == "contracts":
            unit = session.get(RentalUnit, record.rental_unit_id)
            view = repo.contract_view(record, unit, session.get(Property, unit.property_id), user)
        elif collection == "visits":
            view = repo.visit_view(record, user, session)
        elif collection == "conversations":
            view = repo.conversation_view(session, record, user)
        else:
            view = {"id": str(record.id), "full_name": record.full_name, "role": record.role}
        item = bounded(view)
        if collection in {"applications", "contracts", "visits", "conversations"}:
            item["tenant_name"] = session.get(User, record.tenant_id).full_name
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": 6}


def report(session, user, kind, as_of=None, page=1):
    require_admin(user)
    if page < 1 or page > 10000:
        raise ValueError("Invalid page")
    if kind == "dashboard":
        return reporting.dashboard(session, user)
    if kind == "occupancy":
        return reporting.occupancy(session, user, date.fromisoformat(as_of) if as_of else None, page, 6)
    raise ValueError("Invalid report")


def validate(session, user, kind, values):
    require_admin(user)
    values = dict(values)
    target = None
    if kind == "create_property":
        data = inv.PropertyCreate.model_validate(values)
        owner = session.get(User, data.landlord_id) if data.landlord_id else None
        if owner is None or owner.role != "landlord" or not owner.is_active:
            raise ApiError(422, "invalid_owner", "Choose an active landlord for this property")
        summary = f"Create {data.title} in {data.city} for landlord {owner.full_name}."
    elif kind == "update_property":
        target = one(session, Property, values.pop("property_id"), "Property")
        inventory.ensure_editable(session, target)
        data = inv.PropertyPatch.model_validate(values)
        summary = f"Update property {target.title} in {target.city}."
    elif kind in {"create_unit", "update_unit"}:
        if kind == "create_unit":
            prop = one(session, Property, values.pop("property_id"), "Property")
            target = prop
            data = inv.UnitCreate.model_validate(values)
            units = session.scalars(select(RentalUnit).where(RentalUnit.property_id == prop.id)).all()
            if len(units) >= 50 or (data.kind == "apartment" and any(u.kind == "apartment" for u in units)) or any(u.name == data.name for u in units):
                raise ApiError(409, "unit_conflict", "Unit name, kind or property limit conflicts with existing units")
            summary = f"Create {data.name} in {prop.title}."
        else:
            target = one(session, RentalUnit, values.pop("unit_id"), "Unit")
            prop = session.get(Property, target.property_id)
            data = inv.UnitPatch.model_validate(values)
            summary = f"Update {prop.title} · {target.name}."
        inventory.ensure_editable(session, prop)
    elif kind in {"create_listing", "update_listing"}:
        unit = one(session, RentalUnit, values.pop("unit_id"), "Unit")
        target = inventory_repo.listing_for(session, unit.id)
        if kind == "create_listing":
            if target is not None:
                raise ApiError(409, "listing_exists", "This unit already has a listing")
            target = unit
            data = inv.ListingCreate.model_validate(values)
        else:
            if target is None:
                raise ApiError(404, "not_found", "Listing not found")
            if target.status not in {"draft", "rejected"}:
                raise ApiError(409, "review_locked", "Withdraw listing before changing availability")
            data = inv.ListingPatch.model_validate(values)
            inv.ListingCreate.model_validate({"available_from": target.available_from, "available_until": target.available_until,
                                             **data.model_dump(exclude_unset=True)})
        prop = session.get(Property, unit.property_id)
        summary = f"{'Create a draft listing for' if kind == 'create_listing' else 'Update listing availability for'} {prop.title} · {unit.name}."
    elif kind == "change_listing_status":
        target = one(session, Listing, values.pop("listing_id"), "Listing")
        next_status = values.pop("status")
        if next_status not in LISTING_TRANSITIONS:
            raise ValueError("Invalid listing status")
        if next_status in {"approved", "rejected", "published", "unpublished"}:
            data = inv.Moderation.model_validate({"status": next_status, **values})
        else:
            # Submission and withdrawal accept no moderation note.
            if values:
                raise ValueError("Submission and withdrawal do not accept notes")
            data = inv.Input.model_validate(values)
        if target.status not in LISTING_TRANSITIONS[next_status]:
            raise ApiError(409, "invalid_transition", "Listing cannot make this status transition")
        if next_status in {"submitted", "published"} and target.available_until and target.available_until <= inventory_repo.today():
            raise ApiError(409, "expired_listing", "Listing availability has expired")
        context = repo.rental_context(session, target.rental_unit_id)
        summary = f"Change {context['property_title']} · {context['unit_name']} from {target.status} to {next_status}."
    elif kind in {"review_application", "approve_application", "reject_application"}:
        target = one(session, RentalRequest, values.pop("application_id"), "Application")
        tenant = session.get(User, target.tenant_id)
        if target.status not in ({"submitted"} if kind == "review_application" else {"submitted", "reviewing"}):
            raise ApiError(409, "invalid_transition", "Application is no longer pending for this decision")
        context = repo.rental_context(session, target.rental_unit_id)
        if kind == "approve_application":
            data = ops.Approval.model_validate(values)
            unit = session.get(RentalUnit, target.rental_unit_id)
            listing = session.scalar(select(Listing).where(Listing.rental_unit_id == unit.id, Listing.status == "published"))
            if listing is None:
                raise ApiError(409, "listing_unavailable", "Listing is not published")
            if not tenant.is_active:
                raise ApiError(409, "inactive_tenant", "Tenant account is inactive")
            operations.check_dates(listing, unit, session, target.start_date, target.end_date)
            data = ops.Approval(monthly_rent=data.monthly_rent if data.monthly_rent is not None else unit.monthly_rent)
            summary = f"Approve {tenant.full_name}'s application for {context['property_title']} · {context['unit_name']}, {target.start_date} to {target.end_date}, and create a contract at €{data.monthly_rent}/month."
        else:
            data = ops.Decision.model_validate(values) if kind == "reject_application" else inv.Input.model_validate(values)
            summary = f"{'Reject' if kind == 'reject_application' else 'Start reviewing'} {tenant.full_name}'s application for {context['property_title']} · {context['unit_name']}, {target.start_date} to {target.end_date}."
    elif kind == "update_visit":
        target = one(session, Visit, values.pop("visit_id"), "Visit")
        data = ops.VisitUpdate.model_validate(values)
        allowed = {"requested": {"scheduled", "rejected", "cancelled"}, "scheduled": {"scheduled", "completed", "cancelled"}}
        if data.status not in allowed.get(target.status, set()):
            raise ApiError(409, "invalid_transition", "Visit cannot make this transition")
        if data.status == "scheduled":
            start = data.scheduled_at or target.scheduled_at
            if start is None or start <= operations.now():
                raise ApiError(422, "invalid_schedule", "Provide a future scheduled_at with timezone")
            staff_id = data.assigned_admin_id or target.assigned_admin_id or user.id
            staff = session.get(User, staff_id)
            if staff is None or staff.role != "admin" or not staff.is_active:
                raise ApiError(422, "invalid_staff", "Assigned user must be an active administrator")
            data = ops.VisitUpdate(**{**data.model_dump(exclude_unset=True), "scheduled_at": start,
                                      "assigned_admin_id": staff_id, "duration_minutes": data.duration_minutes or target.duration_minutes})
        context = repo.rental_context(session, target.rental_unit_id)
        summary = f"Set visit to {context['property_title']} · {context['unit_name']} to {data.status}."
        if data.status == "scheduled":
            summary += f" Assigned agent: {staff.full_name}."
    elif kind == "send_tenant_message":
        target = operations.owned_conversation(session, user, UUID(values.pop("conversation_id")))
        data = ops.MessageCreate.model_validate(values)
        tenant = session.get(User, target.tenant_id)
        summary = f"Send an agency reply to {tenant.full_name} in: {target.subject}"
    else:
        raise ApiError(422, "unknown_action", "Unsupported agency action")
    payload = data.model_dump(mode="json", exclude_unset=kind.startswith("update_"))
    id_fields = {"update_property": "property_id", "create_unit": "property_id", "update_unit": "unit_id",
                 "create_listing": "unit_id", "update_listing": "unit_id", "change_listing_status": "listing_id",
                 "review_application": "application_id", "approve_application": "application_id", "reject_application": "application_id",
                 "update_visit": "visit_id", "send_tenant_message": "conversation_id"}
    if kind in id_fields:
        payload[id_fields[kind]] = str(unit.id if kind in {"create_listing", "update_listing"} else target.id)
    if kind == "change_listing_status":
        payload["status"] = next_status
    if target is not None and kind != "send_tenant_message":
        payload["expected_updated_at"] = target.updated_at.isoformat()
    return payload, summary


def execute(session, user, kind, payload):
    require_admin(user)
    values = dict(payload)
    expected = values.pop("expected_updated_at", None)
    if kind in {"update_property", "create_unit"}:
        target = lock_record(session, Property, values["property_id"])
    elif kind in {"update_unit", "create_listing"}:
        target = lock_record(session, RentalUnit, values["unit_id"])
    elif kind == "update_listing":
        unit = one(session, RentalUnit, values["unit_id"], "Unit")
        listing = inventory_repo.listing_for(session, unit.id)
        target = lock_record(session, Listing, listing.id) if listing else None
    elif kind == "change_listing_status":
        target = lock_record(session, Listing, values["listing_id"])
    elif kind in {"review_application", "approve_application", "reject_application"}:
        target = lock_record(session, RentalRequest, values["application_id"])
    elif kind == "update_visit":
        target = lock_record(session, Visit, values["visit_id"])
    else:
        target = None
    if expected is not None and (target is None or target.updated_at.isoformat() != expected):
        raise ApiError(409, "record_changed", "This record changed. Ask the assistant to prepare a new action.")
    if kind == "create_property":
        return inventory.create_property(session, user, inv.PropertyCreate.model_validate(values), commit_changes=False)
    inventory_actions = {"update_property": ("property_id", inv.PropertyPatch, inventory.update_property),
        "create_unit": ("property_id", inv.UnitCreate, inventory.create_unit),
        "update_unit": ("unit_id", inv.UnitPatch, inventory.update_unit),
        "create_listing": ("unit_id", inv.ListingCreate, inventory.create_listing),
        "update_listing": ("unit_id", inv.ListingPatch, inventory.update_listing)}
    if kind in inventory_actions:
        key, schema, operation = inventory_actions[kind]
        identifier = UUID(values.pop(key))
        return operation(session, identifier, user, schema.model_validate(values), commit_changes=False)
    if kind == "change_listing_status":
        return inv.ListingRead.model_validate(inventory.transition_listing(session, UUID(values["listing_id"]), user,
            values["status"], values.get("review_note"), commit_changes=False))
    if kind in {"review_application", "reject_application"}:
        return operations.application_action(session, user, UUID(values["application_id"]),
            "reviewing" if kind == "review_application" else "rejected", values.get("review_note"))
    if kind == "approve_application":
        identifier = UUID(values.pop("application_id"))
        return operations.approve(session, user, identifier, ops.Approval.model_validate(values))
    if kind == "update_visit":
        identifier = UUID(values.pop("visit_id"))
        return operations.update_visit(session, user, identifier, ops.VisitUpdate.model_validate(values))
    if kind == "send_tenant_message":
        return operations.send_message(session, user, UUID(values["conversation_id"]), ops.MessageCreate(body=values["body"]))
    raise ApiError(422, "unknown_action", "Unsupported agency action")


def lock_record(session, model, identifier):
    """Take the existing parent-before-record lock order before checking the reviewed version."""
    record = one(session, model, identifier, "Agency record")
    if model == Property:
        parent_id = record.id
    elif model == RentalUnit:
        parent_id = record.property_id
    else:
        unit = session.get(RentalUnit, record.rental_unit_id)
        if unit is None:
            raise ApiError(404, "not_found", "Rental unit not found")
        parent_id = unit.property_id
    parent = session.scalar(select(Property).where(Property.id == parent_id).with_for_update())
    if parent is None:
        raise ApiError(404, "not_found", "Property not found")
    record = session.scalar(select(model).where(model.id == record.id).with_for_update().execution_options(populate_existing=True))
    if record is None:
        raise ApiError(404, "not_found", "Agency record not found")
    return record
