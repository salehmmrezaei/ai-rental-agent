from decimal import Decimal
from sqlalchemy import select, func
from app.models import Property, RentalUnit, RentalContract, RentalRequest, Visit, User, Listing, SavedListing, Message, Conversation
from app.repositories import inventory, operations as repo
from app.schemas.operations import OccupancyProperty, OccupancySummary, OccupancyReport, DashboardStatistics
from app.errors import ApiError


def occupancy(session,user,day=None,page=1,page_size=20):
    if user.role not in {'admin','landlord'}: raise ApiError(403,'forbidden','Agency or landlord role required')
    day=day or inventory.today()
    query=select(Property).order_by(Property.created_at,Property.id)
    if user.role=='landlord': query=query.where(Property.landlord_id==user.id)
    props=session.scalars(query).all()
    ids=[p.id for p in props]
    units=session.scalars(select(RentalUnit).where(RentalUnit.property_id.in_(ids))).all() if ids else []
    contracts=session.scalars(select(RentalContract).join(RentalUnit).where(RentalUnit.property_id.in_(ids),RentalContract.status!='cancelled',
        func.coalesce(RentalContract.terminated_on,RentalContract.end_date)>day)).all() if ids else []
    by_property={p.id:[] for p in props}
    unit_by_id={u.id:u for u in units}
    for u in units: by_property[u.property_id].append(u)
    bookings={p.id:[] for p in props}
    for c in contracts: bookings[unit_by_id[c.rental_unit_id].property_id].append(c)
    items=[]
    for p in props:
        all_units=by_property[p.id]
        physical=[u for u in all_units if u.kind=='room'] or all_units
        occupied=reserved=0
        current_rent=Decimal('0.00')
        for c in bookings[p.id]:
            if c.start_date<=day: current_rent+=c.monthly_rent
        for u in physical:
            matching=[c for c in bookings[p.id] if c.rental_unit_id==u.id or unit_by_id[c.rental_unit_id].kind=='apartment']
            if any(c.start_date<=day for c in matching): occupied+=1
            elif matching: reserved+=1
        total=len(physical)
        items.append(OccupancyProperty(property_id=p.id,title=p.title,city=p.city,total_units=total,occupied_units=occupied,
            reserved_units=reserved,available_units=total-occupied-reserved,
            occupancy_percent=percent(occupied,total),contracted_monthly_rent=current_rent))
    counts={k:sum(getattr(i,k) for i in items) for k in ['total_units','occupied_units','reserved_units','available_units','contracted_monthly_rent']}
    summary=OccupancySummary(as_of=day,properties=len(props),occupancy_percent=percent(counts['occupied_units'],counts['total_units']),**counts)
    return OccupancyReport(summary=summary,items=items[(page-1)*page_size:page*page_size],total=len(items),page=page,page_size=page_size)


def percent(part,total): return (Decimal(part)*100/total).quantize(Decimal('0.01')) if total else Decimal('0.00')


def count(session,query): return session.scalar(select(func.count()).select_from(query.subquery()))


def dashboard(session,user):
    day=inventory.today()
    counts={}
    if user.role=='tenant':
        counts['pending_applications']=count(session,repo.applications(user).where(RentalRequest.status.in_(['submitted','reviewing'])))
        base=select(RentalContract.id).where(RentalContract.tenant_id==user.id,RentalContract.status!='cancelled',func.coalesce(RentalContract.terminated_on,RentalContract.end_date)>day)
        counts['current_rentals']=count(session,base.where(RentalContract.start_date<=day))
        counts['future_rentals']=count(session,base.where(RentalContract.start_date>day))
        counts['upcoming_visits']=count(session,repo.visits(user).where(Visit.status.in_(['requested','scheduled']),func.coalesce(Visit.scheduled_end_at,Visit.requested_at)>func.now()))
        counts['saved_listings']=count(session,select(SavedListing.id).where(SavedListing.tenant_id==user.id))
        counts['unread_messages']=count(session,repo.unread_query(user).join(Conversation,Conversation.id==Message.conversation_id).where(Conversation.tenant_id==user.id))
        return DashboardStatistics(role=user.role,counts=counts)
    report=occupancy(session,user)
    counts['properties']=report.summary.properties
    counts['contracts']=count(session,repo.contracts(user))
    listing_query=select(Listing.id).join(RentalUnit).join(Property).where(Listing.status=='published')
    if user.role=='landlord': listing_query=listing_query.where(Property.landlord_id==user.id)
    counts['published_listings']=count(session,listing_query)
    if user.role=='admin':
        counts['users']=count(session,select(User.id))
        counts['pending_listings']=count(session,select(Listing.id).where(Listing.status=='submitted'))
        counts['pending_applications']=count(session,select(RentalRequest.id).where(RentalRequest.status.in_(['submitted','reviewing'])))
        counts['requested_visits']=count(session,select(Visit.id).where(Visit.status=='requested'))
        counts['unread_messages']=count(session,repo.unread_query(user))
    return DashboardStatistics(role=user.role,counts=counts,occupancy=report.summary)
