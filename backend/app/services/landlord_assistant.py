"""Owner-scoped assistant reads and authorization for shared inventory actions."""
from datetime import date
from typing import get_args
from uuid import UUID

from sqlalchemy import func, or_, select

from app.errors import ApiError
from app.models import Property, RentalUnit, Listing, RentalContract
from app.repositories import inventory as inventory_repo, operations as repo
from app.schemas import inventory as inv, operations as ops
from app.services import inventory, reporting

KINDS = {"create_property", "update_property", "create_unit", "update_unit",
         "create_listing", "update_listing", "change_listing_status"}


def require_landlord(user):
    if user.role != "landlord":
        raise ApiError(403, "forbidden", "Landlord role required")


def scoped(user, model):
    require_landlord(user)
    statement = select(model)
    if model == RentalUnit:
        statement = statement.join(Property, Property.id == RentalUnit.property_id)
    elif model in {Listing, RentalContract}:
        statement = statement.join(RentalUnit, RentalUnit.id == model.rental_unit_id).join(
            Property, Property.id == RentalUnit.property_id)
    elif model != Property:
        raise ValueError("Unsupported landlord record")
    return statement.where(Property.landlord_id == user.id)


def owned(session, user, model, identifier):
    record = session.scalar(scoped(user, model).where(model.id == UUID(str(identifier))))
    if record is None:
        raise ApiError(404, "not_found", "Landlord record not found")
    return record


def authorize_action(session, user, kind, values):
    """Run before proposal validation AND execution, including forged stored payloads."""
    require_landlord(user)
    values = dict(values)
    if kind not in KINDS:
        raise ApiError(403, "forbidden", "This action requires the agency")
    if kind == "create_property":
        owner = values.get("landlord_id")
        if owner is not None and UUID(str(owner)) != user.id:
            raise ApiError(403, "forbidden", "Cannot create property for another owner")
        values["landlord_id"] = str(user.id)
    else:
        if kind == "change_listing_status":
            if values.get("status") not in {"draft", "submitted"}:
                raise ApiError(403, "forbidden", "Listing review and publication require the agency")
            model, key = Listing, "listing_id"
        elif kind in {"update_property", "create_unit"}:
            model, key = Property, "property_id"
        else:
            model, key = RentalUnit, "unit_id"
        owned(session, user, model, values[key])
    return values


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


def records(session, user, collection, record_id=None, property_id=None, status=None, query=None, page=1):
    require_landlord(user)
    models = {"properties": Property, "units": RentalUnit, "listings": Listing, "contracts": RentalContract}
    if collection not in models or not 1 <= page <= 10000 or (query is not None and len(query) > 100):
        raise ValueError("Invalid collection, page or query")
    model = models[collection]
    statement = scoped(user, model)
    if record_id:
        statement = statement.where(model.id == UUID(record_id))
    if property_id:
        owned(session, user, Property, property_id)
        statement = statement.where(Property.id == UUID(property_id))
    if status:
        statuses = {"listings": inv.ListingStatus, "contracts": ops.ContractStatus}
        if collection not in statuses or status not in get_args(statuses[collection]):
            raise ValueError("Invalid status")
        statement = statement.where(model.status == status)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters = [Property.title.ilike(pattern, escape="\\"), Property.city.ilike(pattern, escape="\\")]
        if model != Property:
            filters.append(RentalUnit.name.ilike(pattern, escape="\\"))
        statement = statement.where(or_(*filters))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(model.created_at.desc(), model.id).offset((page-1)*6).limit(6)).all()
    if record_id and not rows:
        raise ApiError(404, "not_found", "Landlord record not found")
    items = []
    for record in rows:
        if model == Property:
            view = inventory.property_view(session, record, detail=bool(record_id))
        elif model == RentalUnit:
            view = inventory.unit_view(session, record)
        elif model == Listing:
            view = inv.ListingRead.model_validate(record).model_dump(mode="json")
            view.update(repo.rental_context(session, record.rental_unit_id))
            view["property_id"] = str(view["property_id"])
            view["monthly_rent"] = str(session.get(RentalUnit, record.rental_unit_id).monthly_rent)
        else:
            unit = session.get(RentalUnit, record.rental_unit_id)
            view = repo.contract_view(record, unit, session.get(Property, unit.property_id), user)
        items.append(bounded(view))
    return {"items": items, "total": total, "page": page, "page_size": 6}


def report(session, user, kind, as_of=None, page=1):
    require_landlord(user)
    if not 1 <= page <= 10000:
        raise ValueError("Invalid page")
    if kind == "dashboard":
        return reporting.dashboard(session, user)
    if kind == "occupancy":
        return reporting.occupancy(session, user, date.fromisoformat(as_of) if as_of else None, page, 6)
    raise ValueError("Invalid report")


def availability(session, user, unit_id, start_date, end_date):
    unit = owned(session, user, RentalUnit, unit_id)
    dates = inv.Search(start_date=start_date, end_date=end_date)
    listing = inventory_repo.listing_for(session, unit.id)
    if listing is None:
        raise ApiError(404, "not_found", "Create a listing to check its rental availability window")
    available, reason = inventory.availability(session, listing, unit, dates.start_date, dates.end_date)
    return {"unit_id": str(unit.id), "listing_id": str(listing.id), "listing_status": listing.status,
            "start_date": start_date, "end_date": end_date, "available": available, "reason": reason,
            "can_accept_applications": available and listing.status == "published"}
