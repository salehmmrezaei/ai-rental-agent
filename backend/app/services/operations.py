from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, func
from app.errors import ApiError
from app.models import RentalRequest, RentalContract, RentalUnit, Property, Listing, Visit, Conversation, Message, User, SavedListing
from app.repositories import inventory, operations as repo
from app.schemas.operations import ApplicationRead
from app.schemas.auth import UserProfile
from app.services import transactions as tx


def now(): return datetime.now(timezone.utc)


def lock_parent(session,pid):
    prop=session.scalar(select(Property).where(Property.id==pid).with_for_update().execution_options(populate_existing=True))
    if prop is None: raise ApiError(404,'not_found','Property not found')
    prop.booking_revision+=1
    session.flush()
    return prop


def lock_published(session,lid):
    query=inventory.listing_rows().where(Listing.id==lid,Listing.status=='published')
    row=session.execute(query).first()
    if row is None: raise ApiError(404,'not_found','Listing not found')
    lock_parent(session,row[2].id)
    row=session.execute(query.execution_options(populate_existing=True)).first()
    if row is None: raise ApiError(404,'not_found','Listing not found')
    return row


def check_dates(listing,unit,session,start,end):
    from app.services.inventory import availability
    if start < inventory.today(): raise ApiError(422,'past_dates','Rental start cannot be in the past')
    available,reason=availability(session,listing,unit,start,end)
    if not available: raise ApiError(409,reason,'Requested dates are not available')


def create_application(session,user,data):
    listing,unit,_=lock_published(session,data.listing_id)
    check_dates(listing,unit,session,data.start_date,data.end_date)
    duplicate=session.scalar(select(RentalRequest.id).where(RentalRequest.tenant_id==user.id,RentalRequest.rental_unit_id==unit.id,
        RentalRequest.start_date==data.start_date,RentalRequest.end_date==data.end_date,RentalRequest.status.in_(['submitted','reviewing'])).limit(1))
    if duplicate: raise ApiError(409,'duplicate_application','An application for these dates is already pending')
    req=RentalRequest(tenant_id=user.id,rental_unit_id=unit.id,start_date=data.start_date,end_date=data.end_date,note=data.note)
    session.add(req); session.flush()
    return ApplicationRead.model_validate(req)


def lock_application(session,user,rid):
    req=session.scalar(repo.applications(user).where(RentalRequest.id==rid))
    if req is None: raise ApiError(404,'not_found','Application not found')
    unit=session.get(RentalUnit,req.rental_unit_id)
    lock_parent(session,unit.property_id)
    req=session.scalar(repo.applications(user).where(RentalRequest.id==rid).with_for_update().execution_options(populate_existing=True))
    if req is None: raise ApiError(404,'not_found','Application not found')
    return req


def application_action(session,user,rid,action,note=None):
    req=lock_application(session,user,rid)
    allowed={'withdrawn':{'submitted','reviewing'},'reviewing':{'submitted'},'rejected':{'submitted','reviewing'}}
    if req.status==action: return ApplicationRead.model_validate(req)
    if req.status not in allowed[action]: raise ApiError(409,'invalid_transition','Application cannot make this transition')
    req.status=action
    if note is not None: req.review_note=note
    session.flush(); session.refresh(req)
    return ApplicationRead.model_validate(req)


def approve(session,user,rid,data):
    req=lock_application(session,user,rid)
    existing=session.execute(repo.contracts(user).where(RentalContract.rental_request_id==req.id)).first()
    if existing:
        if data.monthly_rent is not None and data.monthly_rent!=existing[0].monthly_rent:
            raise ApiError(409,'already_approved','Existing contract has different terms')
        return repo.contract_view(*existing,user)
    if req.status not in {'submitted','reviewing','approved'}: raise ApiError(409,'invalid_transition','Only pending applications can be approved')
    tenant=session.scalar(select(User).where(User.id==req.tenant_id,User.role=='tenant',User.is_active.is_(True)))
    if tenant is None: raise ApiError(409,'inactive_tenant','Tenant account is inactive')
    unit=session.scalar(select(RentalUnit).where(RentalUnit.id==req.rental_unit_id).execution_options(populate_existing=True))
    listing=session.scalar(select(Listing).where(Listing.rental_unit_id==unit.id,Listing.status=='published'))
    if listing is None: raise ApiError(409,'listing_unavailable','Listing is not published')
    check_dates(listing,unit,session,req.start_date,req.end_date)
    if req.status=='submitted':
        req.status='reviewing'; session.flush()
    req.status='approved'; req.review_note=None; session.flush()
    contract=RentalContract(rental_request_id=req.id,tenant_id=req.tenant_id,rental_unit_id=unit.id,
        start_date=req.start_date,end_date=req.end_date,monthly_rent=data.monthly_rent if data.monthly_rent is not None else unit.monthly_rent)
    session.add(contract); session.flush()
    prop=session.get(Property,unit.property_id)
    return repo.contract_view(contract,unit,prop,user)


def update_contract(session,user,cid,data):
    row=session.execute(repo.contracts(user).where(RentalContract.id==cid)).first()
    if row is None: raise ApiError(404,'not_found','Contract not found')
    lock_parent(session,row[2].id)
    row=session.execute(repo.contracts(user).where(RentalContract.id==cid).with_for_update(of=RentalContract).execution_options(populate_existing=True)).first()
    if row is None: raise ApiError(404,'not_found','Contract not found')
    contract,unit,prop=row
    if data.monthly_rent is not None:
        if contract.status!='confirmed': raise ApiError(409,'immutable_terms','Only confirmed contract rent can change')
        contract.monthly_rent=data.monthly_rent
    if data.status is not None and data.status!=contract.status:
        if data.status=='active' and inventory.today()<contract.start_date:
            raise ApiError(409,'future_contract','Cannot activate before rental start')
        if data.status=='completed':
            if inventory.today()<contract.end_date: raise ApiError(409,'ongoing_contract','Cannot complete before rental end')
            if contract.status=='confirmed': contract.status='active'; session.flush()
        if data.status=='terminated':
            if contract.status!='active': raise ApiError(409,'invalid_transition','Only active contracts can terminate')
            if not contract.start_date<data.terminated_on<=contract.end_date:
                raise ApiError(422,'invalid_termination','Termination must be after start and no later than end')
            contract.terminated_on=data.terminated_on
        allowed={'confirmed':{'active','cancelled'},'active':{'completed','terminated'}}
        if data.status not in allowed.get(contract.status,set()): raise ApiError(409,'invalid_transition','Contract cannot make this transition')
        contract.status=data.status
    elif data.status=='terminated' and data.terminated_on!=contract.terminated_on:
        raise ApiError(409,'immutable_termination','Recorded termination cannot change')
    session.flush(); session.refresh(contract)
    return repo.contract_view(contract,unit,prop,user)


def create_visit(session,user,data):
    _,unit,_=lock_published(session,data.listing_id)
    if data.requested_at<=now(): raise ApiError(422,'past_visit','Requested visit must be in the future')
    visit=Visit(tenant_id=user.id,rental_unit_id=unit.id,requested_at=data.requested_at,note=data.note)
    session.add(visit); session.flush()
    return repo.visit_view(visit,user)


def lock_visit(session,user,vid):
    visit=session.scalar(repo.visits(user).where(Visit.id==vid))
    if visit is None: raise ApiError(404,'not_found','Visit not found')
    unit=session.get(RentalUnit,visit.rental_unit_id); lock_parent(session,unit.property_id)
    visit=session.scalar(repo.visits(user).where(Visit.id==vid).with_for_update().execution_options(populate_existing=True))
    if visit is None: raise ApiError(404,'not_found','Visit not found')
    return visit


def cancel_visit(session,user,vid):
    visit=lock_visit(session,user,vid)
    if visit.status=='cancelled': return repo.visit_view(visit,user)
    if visit.status not in {'requested','scheduled'}: raise ApiError(409,'invalid_transition','Visit cannot be cancelled')
    visit.status='cancelled'; session.flush(); session.refresh(visit)
    return repo.visit_view(visit,user)


def update_visit(session,user,vid,data):
    visit=lock_visit(session,user,vid)
    allowed={'requested':{'scheduled','rejected','cancelled'},'scheduled':{'scheduled','completed','cancelled'}}
    if data.status not in allowed.get(visit.status,set()): raise ApiError(409,'invalid_transition','Visit cannot make this transition')
    if data.status=='scheduled':
        listing=session.scalar(select(Listing.id).where(Listing.rental_unit_id==visit.rental_unit_id,Listing.status=='published'))
        if listing is None: raise ApiError(409,'listing_unavailable','Listing is not published')
        start=data.scheduled_at or visit.scheduled_at
        if start is None or start<=now(): raise ApiError(422,'invalid_schedule','Provide a future scheduled_at')
        staff=data.assigned_admin_id or visit.assigned_admin_id or user.id
        if not session.scalar(select(User.id).where(User.id==staff,User.role=='admin',User.is_active.is_(True))):
            raise ApiError(422,'invalid_staff','Assigned user must be an active administrator')
        visit.scheduled_at=start
        visit.duration_minutes=data.duration_minutes or visit.duration_minutes
        visit.scheduled_end_at=start+timedelta(minutes=visit.duration_minutes)
        visit.assigned_admin_id=staff
    if data.status=='completed' and (visit.scheduled_end_at is None or visit.scheduled_end_at>now()):
        raise ApiError(409,'future_visit','Visit has not finished yet')
    visit.status=data.status
    if data.agency_note is not None: visit.agency_note=data.agency_note
    session.flush(); session.refresh(visit)
    return repo.visit_view(visit,user)


def owned_conversation(session,user,cid,lock=False):
    query=repo.conversations(user).where(Conversation.id==cid)
    if lock: query=query.with_for_update().execution_options(populate_existing=True)
    conversation=session.scalar(query)
    if conversation is None: raise ApiError(404,'not_found','Conversation not found')
    return conversation


def create_conversation(session,user,data):
    conversation=Conversation(tenant_id=user.id,subject=data.subject)
    session.add(conversation); session.flush()
    session.add(Message(conversation_id=conversation.id,sender_id=user.id,body=data.initial_message))
    session.flush()
    return repo.conversation_view(session,conversation,user)


def send_message(session,user,cid,data):
    conversation=owned_conversation(session,user,cid,True)
    msg=Message(conversation_id=conversation.id,sender_id=user.id,body=data.body)
    session.add(msg); conversation.updated_at=func.now(); session.flush()
    return repo.message_view(msg,user.role)


def mark_read(session,user,cid):
    owned_conversation(session,user,cid,True)
    senders=select(User.id).where(User.role=='tenant' if user.role=='admin' else User.role=='admin')
    result=session.execute(update(Message).where(Message.conversation_id==cid,Message.read_at.is_(None),Message.sender_id.in_(senders)).values(read_at=now()))
    return {'updated':result.rowcount}


def update_user(session,user,uid,data,actor):
    # Stable locks prevent two administrators concurrently deactivating each other.
    session.scalars(select(User).where(User.role=='admin',User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
    tx.authenticate(session,actor,{'admin'})
    target=session.scalar(select(User).where(User.id==uid).with_for_update().execution_options(populate_existing=True))
    if target is None: raise ApiError(404,'not_found','User not found')
    if uid==user.id and data.is_active is False: raise ApiError(409,'self_deactivation','Administrator cannot deactivate their own account')
    changes=data.model_dump(exclude_unset=True)
    if any(k in changes and changes[k]!=getattr(target,k) for k in ['email','is_active']): target.token_version+=1
    for k,v in changes.items(): setattr(target,k,v)
    session.flush(); session.refresh(target)
    return UserProfile.model_validate(target)


def save_listing(session,user,lid):
    lock_published(session,lid)
    existing=session.scalar(select(SavedListing).where(SavedListing.tenant_id==user.id,SavedListing.listing_id==lid))
    if existing is None:
        existing=SavedListing(tenant_id=user.id,listing_id=lid); session.add(existing); session.flush()
    return {'id':existing.id,'listing_id':existing.listing_id,'created_at':existing.created_at}


def delete_saved(session,user,sid):
    saved=session.scalar(select(SavedListing).where(SavedListing.id==sid,SavedListing.tenant_id==user.id).with_for_update())
    if saved is None: raise ApiError(404,'not_found','Saved listing not found')
    session.delete(saved); session.flush()
