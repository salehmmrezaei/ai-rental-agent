from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import aliased
from app.models import Listing, Property, RentalUnit, RentalContract, PropertyImage, Amenity, PropertyAmenity


def today() -> date:
    return datetime.now(ZoneInfo('Europe/Rome')).date()


def conflict_exists(unit, start, end):
    other = aliased(RentalUnit)
    return select(RentalContract.id).join(other, other.id == RentalContract.rental_unit_id).where(
        other.property_id == unit.property_id,
        RentalContract.status != 'cancelled',
        RentalContract.start_date < end, func.coalesce(RentalContract.terminated_on, RentalContract.end_date) > start,
        or_(other.id == unit.id, other.kind == 'apartment', unit.kind == 'apartment')
    ).correlate(unit).exists()


def available_expression(unit, listing, start, end):
    return and_(listing.available_from <= start,
                or_(listing.available_until.is_(None), listing.available_until >= end),
                ~conflict_exists(unit, start, end))


def occupancy(session, unit):
    day = today()
    occupied = session.scalar(select(conflict_exists(RentalUnit, day, day + timedelta(days=1)))
                               .select_from(RentalUnit).where(RentalUnit.id == unit.id))
    if occupied: return 'occupied'
    other = aliased(RentalUnit)
    future = session.scalar(select(RentalContract.id).join(other, other.id == RentalContract.rental_unit_id).where(
        other.property_id == unit.property_id, RentalContract.status != 'cancelled',
        RentalContract.start_date > day,
        or_(other.id == unit.id, other.kind == 'apartment', unit.kind == 'apartment')
    ).limit(1))
    return 'reserved' if future else 'available'


def amenities(session, property_id):
    return list(session.scalars(select(Amenity.name).join(PropertyAmenity).where(
        PropertyAmenity.property_id == property_id).order_by(Amenity.name)))


def images(session, property_id, unit=None):
    query = select(PropertyImage).where(PropertyImage.property_id == property_id)
    if unit is not None and unit.kind != 'apartment':
        query = query.where(or_(PropertyImage.rental_unit_id.is_(None), PropertyImage.rental_unit_id == unit.id))
    return session.scalars(query.order_by(PropertyImage.position, PropertyImage.created_at, PropertyImage.id)).all()


def listing_for(session, unit_id):
    return session.scalar(select(Listing).where(Listing.rental_unit_id == unit_id))


def listing_rows():
    return select(Listing, RentalUnit, Property).join(RentalUnit, Listing.rental_unit_id == RentalUnit.id).join(
        Property, Property.id == RentalUnit.property_id)


def search(session, filters):
    query = listing_rows().where(Listing.status == 'published',
        or_(Listing.available_until.is_(None), Listing.available_until > today()))
    if filters.city: query = query.where(func.lower(Property.city) == filters.city.lower())
    if filters.property_type: query = query.where(RentalUnit.kind == filters.property_type)
    if filters.min_price is not None: query = query.where(RentalUnit.monthly_rent >= filters.min_price)
    if filters.max_price is not None: query = query.where(RentalUnit.monthly_rent <= filters.max_price)
    if filters.min_rooms: query = query.where(RentalUnit.bedrooms >= filters.min_rooms)
    if filters.start_date: query = query.where(available_expression(RentalUnit, Listing, filters.start_date, filters.end_date))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    order = {'newest': Listing.created_at.desc(), 'price_asc': RentalUnit.monthly_rent.asc(),
             'price_desc': RentalUnit.monthly_rent.desc()}[filters.sort]
    rows = session.execute(query.order_by(order, Listing.id).offset((filters.page - 1) * filters.page_size).limit(filters.page_size)).all()
    return rows, total
