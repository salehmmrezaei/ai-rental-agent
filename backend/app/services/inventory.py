from datetime import timedelta
from uuid import UUID
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from app.errors import ApiError
from app.models import Property, RentalUnit, Listing, User, Amenity, PropertyAmenity, PropertyImage
from app.repositories import inventory as repo
from app.schemas.inventory import PropertyRead, PropertyDetail, UnitRead, ListingRead, ImageRead, PublicListing, ListingCreate

FROZEN = ('submitted', 'approved', 'published', 'unpublished')


def commit(session):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if exc.orig.sqlstate in {'23505','23503','23514','23P01'}:
            raise ApiError(409, 'inventory_conflict', 'Operation conflicts with existing inventory or rental history') from None
        raise


def lock_property(session, property_id, user):
    query = select(Property).where(Property.id == property_id)
    if user.role != 'admin':
        if user.role != 'landlord': raise ApiError(404, 'not_found', 'Property not found')
        query = query.where(Property.landlord_id == user.id)
    prop = session.scalar(query.with_for_update().execution_options(populate_existing=True))
    if prop is None: raise ApiError(404, 'not_found', 'Property not found')
    prop.booking_revision += 1
    session.flush()
    return prop


def ensure_editable(session, prop):
    frozen = session.scalar(select(Listing.id).join(RentalUnit).where(
        RentalUnit.property_id == prop.id, Listing.status.in_(FROZEN)).limit(1))
    if frozen:
        raise ApiError(409, 'review_locked', 'Unpublish and withdraw reviewed listings before changing property content')


def image_view(image):
    return ImageRead(id=image.id, property_id=image.property_id, rental_unit_id=image.rental_unit_id,
                     alt_text=image.alt_text, position=image.position, url=f'/api/v1/images/{image.id}')


def unit_view(session, unit):
    listing = repo.listing_for(session, unit.id)
    return UnitRead(id=unit.id, property_id=unit.property_id, kind=unit.kind, name=unit.name,
        monthly_rent=unit.monthly_rent, deposit=unit.deposit, bedrooms=unit.bedrooms, area_sqm=unit.area_sqm,
        occupancy_status=repo.occupancy(session, unit), listing=ListingRead.model_validate(listing) if listing else None)


def property_view(session, prop, detail=False):
    values = {key: getattr(prop, key) for key in PropertyRead.model_fields if key != 'amenities'}
    values['amenities'] = repo.amenities(session, prop.id)
    if not detail: return PropertyRead(**values)
    units = session.scalars(select(RentalUnit).where(RentalUnit.property_id == prop.id).order_by(RentalUnit.name)).all()
    return PropertyDetail(**values, units=[unit_view(session,u) for u in units],
                          images=[image_view(i) for i in repo.images(session, prop.id)])


def set_amenities(session, property_id, names):
    session.execute(delete(PropertyAmenity).where(PropertyAmenity.property_id == property_id))
    for name in names:
        session.execute(insert(Amenity).values(name=name).on_conflict_do_nothing(index_elements=['name']))
        aid = session.scalar(select(Amenity.id).where(Amenity.name == name))
        session.add(PropertyAmenity(property_id=property_id, amenity_id=aid))


def create_property(session, user, data):
    if user.role not in {'landlord','admin'}: raise ApiError(403, 'forbidden', 'Only landlords or agency admins can create properties')
    owner = data.landlord_id or (user.id if user.role == 'landlord' else None)
    if user.role == 'landlord' and owner != user.id: raise ApiError(403, 'forbidden', 'Cannot create property for another owner')
    if owner is None: raise ApiError(422, 'owner_required', 'Agency creation requires a landlord_id')
    landlord = session.scalar(select(User).where(User.id == owner, User.role == 'landlord', User.is_active.is_(True)))
    if landlord is None: raise ApiError(422, 'invalid_owner', 'Owner must be an active landlord')
    prop = Property(**data.model_dump(exclude={'landlord_id','amenities'}), landlord_id=owner)
    session.add(prop); session.flush()
    set_amenities(session, prop.id, data.amenities)
    commit(session); session.refresh(prop)
    return property_view(session, prop, True)


def update_property(session, prop_id, user, data):
    prop = lock_property(session, prop_id, user); ensure_editable(session, prop)
    fields = data.model_dump(exclude_unset=True)
    if 'amenities' in fields:
        set_amenities(session, prop.id, fields.pop('amenities'))
        prop.updated_at = func.now()
    for field,value in fields.items(): setattr(prop, field, value)
    commit(session); session.refresh(prop)
    return property_view(session, prop, True)


def create_unit(session, property_id, user, data):
    prop = lock_property(session, property_id, user); ensure_editable(session, prop)
    count = session.scalar(select(func.count()).select_from(RentalUnit).where(RentalUnit.property_id == property_id))
    if count >= 50: raise ApiError(409, 'unit_limit', 'Maximum 50 units per property')
    unit = RentalUnit(property_id=property_id, **data.model_dump())
    session.add(unit); commit(session); session.refresh(unit)
    return unit_view(session, unit)


def get_owned_unit(session, unit_id, user):
    query = select(RentalUnit).join(Property, Property.id == RentalUnit.property_id).where(RentalUnit.id == unit_id)
    if user.role != 'admin':
        if user.role != 'landlord': raise ApiError(404, 'not_found', 'Rental unit not found')
        query = query.where(Property.landlord_id == user.id)
    unit = session.scalar(query)
    if not unit: raise ApiError(404, 'not_found', 'Rental unit not found')
    prop = lock_property(session, unit.property_id, user)
    unit = session.scalar(select(RentalUnit).where(RentalUnit.id==unit_id).execution_options(populate_existing=True))
    if not unit: raise ApiError(404, 'not_found', 'Rental unit not found')
    return prop, unit


def update_unit(session, unit_id, user, data):
    prop, unit = get_owned_unit(session, unit_id, user); ensure_editable(session, prop)
    for field,value in data.model_dump(exclude_unset=True).items(): setattr(unit, field, value)
    commit(session); session.refresh(unit)
    return unit_view(session, unit)


def delete_unit(session, unit_id, user):
    prop, unit = get_owned_unit(session, unit_id, user); ensure_editable(session, prop)
    images = repo.images(session, prop.id)
    keys = [i.storage_key for i in images if i.rental_unit_id == unit.id]
    session.execute(delete(PropertyImage).where(PropertyImage.rental_unit_id == unit.id))
    session.execute(delete(Listing).where(Listing.rental_unit_id == unit.id))
    session.delete(unit); commit(session)
    return keys


def delete_property(session, property_id, user):
    prop = lock_property(session, property_id, user); ensure_editable(session, prop)
    keys = [i.storage_key for i in repo.images(session, prop.id)]
    unit_ids = select(RentalUnit.id).where(RentalUnit.property_id == prop.id)
    session.execute(delete(PropertyImage).where(PropertyImage.property_id == prop.id))
    session.execute(delete(Listing).where(Listing.rental_unit_id.in_(unit_ids)))
    session.execute(delete(RentalUnit).where(RentalUnit.property_id == prop.id))
    session.delete(prop); commit(session)
    return keys


def create_listing(session, unit_id, user, data):
    prop, unit = get_owned_unit(session, unit_id, user)
    # Independent new listings may be drafted while another unit is reviewed;
    # creating a listing changes no property/unit/image content.
    listing = Listing(rental_unit_id=unit.id, **data.model_dump())
    session.add(listing); commit(session); session.refresh(listing)
    return listing


def lock_listing(session, listing_id, user, admin_only=False):
    if admin_only and user.role != 'admin': raise ApiError(403, 'forbidden', 'Agency role required')
    query = repo.listing_rows().where(Listing.id == listing_id)
    if user.role != 'admin':
        if user.role != 'landlord': raise ApiError(404, 'not_found', 'Listing not found')
        query = query.where(Property.landlord_id == user.id)
    row = session.execute(query).first()
    if not row: raise ApiError(404, 'not_found', 'Listing not found')
    listing, unit, prop = row
    lock_property(session, prop.id, user)
    listing = session.scalar(select(Listing).where(Listing.id==listing_id).with_for_update().execution_options(populate_existing=True))
    if not listing: raise ApiError(404, 'not_found', 'Listing not found')
    return listing


def update_listing(session, unit_id, user, data):
    prop, unit = get_owned_unit(session, unit_id, user)
    listing = repo.listing_for(session, unit.id)
    if listing is None: raise ApiError(404, 'not_found', 'Listing not found')
    if listing.status not in {'draft','rejected'}: raise ApiError(409, 'review_locked', 'Withdraw listing before changing availability')
    values = {k:getattr(listing,k) for k in ('available_from','available_until')}
    values.update(data.model_dump(exclude_unset=True))
    try: ListingCreate(**values)
    except ValueError: raise ApiError(422, 'invalid_dates', 'Availability end must follow start') from None
    for k,v in values.items(): setattr(listing,k,v)
    commit(session); session.refresh(listing)
    return listing


def transition_listing(session, listing_id, user, action, note=None):
    listing = lock_listing(session, listing_id, user, admin_only=action in {'approved','rejected','published','unpublished'})
    allowed = {'submitted': {'draft','rejected'}, 'draft': {'submitted','approved','unpublished','rejected'},
               'approved': {'submitted'}, 'rejected': {'submitted'}, 'published': {'approved','unpublished'}, 'unpublished': {'published'}}
    if listing.status not in allowed[action]: raise ApiError(409, 'invalid_transition', 'Listing cannot make this status transition')
    if action in {'submitted','published'} and listing.available_until is not None and listing.available_until <= repo.today():
        raise ApiError(409, 'expired_listing', 'Listing availability has expired')
    listing.status = action
    if action in {'draft','submitted'}: listing.review_note = None
    elif note is not None: listing.review_note = note
    commit(session); session.refresh(listing)
    return listing


def public_listing(session, listing_id):
    row = session.execute(repo.listing_rows().where(Listing.id==listing_id, Listing.status=='published')).first()
    if not row: raise ApiError(404, 'not_found', 'Listing not found')
    return row


def public_view(session, listing, unit, prop):
    day = repo.today()
    available = session.scalar(select(repo.available_expression(RentalUnit, Listing, day, day+timedelta(days=1)))
        .select_from(RentalUnit).join(Listing, Listing.rental_unit_id==RentalUnit.id).where(RentalUnit.id==unit.id))
    return PublicListing(id=listing.id, property_id=prop.id, rental_unit_id=unit.id,
        title=prop.title, description=prop.description, city=prop.city, address=prop.address,
        postal_code=prop.postal_code, is_synthetic=prop.is_synthetic, kind=unit.kind, unit_name=unit.name,
        monthly_rent=unit.monthly_rent, deposit=unit.deposit, bedrooms=unit.bedrooms, area_sqm=unit.area_sqm,
        amenities=repo.amenities(session,prop.id), images=[image_view(i) for i in repo.images(session,prop.id,unit)],
        available_from=listing.available_from, available_until=listing.available_until, available_now=bool(available))


def availability(session, listing, unit, start, end):
    if start < listing.available_from or (listing.available_until is not None and end > listing.available_until):
        return False, 'outside_listing_window'
    conflict = session.scalar(select(repo.conflict_exists(RentalUnit,start,end)).select_from(RentalUnit).where(RentalUnit.id==unit.id))
    return (False,'rental_conflict') if conflict else (True,'available')
