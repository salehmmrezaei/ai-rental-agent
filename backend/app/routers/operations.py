"""Role-scoped rental workflows; every mutation runs in a retryable transaction."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from app.dependencies import DB, CurrentUser, require_roles
from app.errors import ApiError
from app.models import User, RentalRequest, RentalContract, Visit, Conversation, Message, SavedListing, Listing
from app.repositories import operations as repo, inventory
from app.schemas import operations as dto
from app.schemas.auth import UserProfile
from app.schemas.inventory import Page
from app.services import operations as svc, transactions as tx, reporting, inventory as inventory_service

router=APIRouter(tags=['rental operations'])
Tenant=Annotated[User,Depends(require_roles('tenant'))]
Agency=Annotated[User,Depends(require_roles('admin'))]
Participant=Annotated[User,Depends(require_roles('tenant','admin'))]
PageNumber=Annotated[int,Query(ge=1)]
PageSize=Annotated[int,Query(ge=1,le=100)]


def write(db,user,roles,operation):
    return tx.run(db.get_bind(),tx.Actor.from_user(user),set(roles),operation)


def one(db,query,label):
    result=db.scalar(query)
    if result is None: raise ApiError(404,'not_found',f'{label} not found')
    return result


@router.post('/applications',response_model=dto.ApplicationRead,status_code=201)
def create_application(data:dto.ApplicationCreate,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.create_application(s,u,data))


@router.get('/applications',response_model=Page[dto.ApplicationRead])
@router.get('/admin/applications',response_model=Page[dto.ApplicationRead],dependencies=[Depends(require_roles('admin'))])
def applications(db:DB,user:Participant,status:dto.ApplicationStatus|None=None,rental_unit_id:UUID|None=None,page:PageNumber=1,page_size:PageSize=20):
    query=repo.applications(user)
    if status: query=query.where(RentalRequest.status==status)
    if rental_unit_id: query=query.where(RentalRequest.rental_unit_id==rental_unit_id)
    rows,total=repo.page(db,query,page,page_size,[RentalRequest.created_at.desc(),RentalRequest.id])
    return Page(items=[dto.ApplicationRead.model_validate(r[0]) for r in rows],total=total,page=page,page_size=page_size)


@router.get('/applications/{application_id}',response_model=dto.ApplicationRead)
def application(application_id:UUID,db:DB,user:Participant):
    return one(db,repo.applications(user).where(RentalRequest.id==application_id),'Application')


@router.post('/applications/{application_id}/withdraw',response_model=dto.ApplicationRead)
def withdraw(application_id:UUID,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.application_action(s,u,application_id,'withdrawn'))


@router.post('/admin/applications/{application_id}/review',response_model=dto.ApplicationRead)
def review(application_id:UUID,db:DB,user:Agency):
    return write(db,user,['admin'],lambda s,u:svc.application_action(s,u,application_id,'reviewing'))


@router.post('/admin/applications/{application_id}/reject',response_model=dto.ApplicationRead)
def reject(application_id:UUID,data:dto.Decision,db:DB,user:Agency):
    return write(db,user,['admin'],lambda s,u:svc.application_action(s,u,application_id,'rejected',data.review_note))


@router.post('/admin/applications/{application_id}/approve',response_model=dto.ContractPrivate)
def approve(application_id:UUID,db:DB,user:Agency,data:dto.Approval=dto.Approval()):
    return write(db,user,['admin'],lambda s,u:svc.approve(s,u,application_id,data))


@router.post('/admin/contracts',response_model=dto.ContractPrivate,status_code=201)
def create_contract(data:dto.ContractCreate,db:DB,user:Agency):
    return write(db,user,['admin'],lambda s,u:svc.approve(s,u,data.application_id,data))


@router.get('/contracts',response_model=Page[dto.ContractPrivate|dto.ContractOwner])
@router.get('/admin/contracts',response_model=Page[dto.ContractPrivate],dependencies=[Depends(require_roles('admin'))])
def contracts(db:DB,user:CurrentUser,status:dto.ContractStatus|None=None,rental_unit_id:UUID|None=None,page:PageNumber=1,page_size:PageSize=20):
    query=repo.contracts(user)
    if status: query=query.where(RentalContract.status==status)
    if rental_unit_id: query=query.where(RentalContract.rental_unit_id==rental_unit_id)
    rows,total=repo.page(db,query,page,page_size,[RentalContract.created_at.desc(),RentalContract.id])
    return Page(items=[repo.contract_view(*r,user) for r in rows],total=total,page=page,page_size=page_size)


@router.get('/contracts/{contract_id}',response_model=dto.ContractPrivate|dto.ContractOwner)
def contract(contract_id:UUID,db:DB,user:CurrentUser):
    row=db.execute(repo.contracts(user).where(RentalContract.id==contract_id)).first()
    if row is None: raise ApiError(404,'not_found','Contract not found')
    return repo.contract_view(*row,user)


@router.patch('/admin/contracts/{contract_id}',response_model=dto.ContractPrivate)
def update_contract(contract_id:UUID,data:dto.ContractUpdate,db:DB,user:Agency):
    return write(db,user,['admin'],lambda s,u:svc.update_contract(s,u,contract_id,data))


@router.post('/visits',response_model=dto.VisitRead,status_code=201)
def create_visit(data:dto.VisitCreate,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.create_visit(s,u,data))


@router.get('/visits',response_model=Page[dto.AgencyVisitRead|dto.VisitRead])
@router.get('/admin/visits',response_model=Page[dto.AgencyVisitRead],dependencies=[Depends(require_roles('admin'))])
def visits(db:DB,user:Participant,status:dto.VisitStatus|None=None,period:Literal['all','upcoming','past']='all',page:PageNumber=1,page_size:PageSize=20):
    query=repo.visits(user)
    if status: query=query.where(Visit.status==status)
    instant=func.coalesce(Visit.scheduled_end_at,Visit.requested_at)
    if period=='upcoming': query=query.where(instant>func.now(),Visit.status.in_(['requested','scheduled']))
    if period=='past': query=query.where(instant<=func.now())
    rows,total=repo.page(db,query,page,page_size,[Visit.requested_at,Visit.id])
    return Page(items=[repo.visit_view(r[0],user) for r in rows],total=total,page=page,page_size=page_size)


@router.get('/visits/{visit_id}',response_model=dto.AgencyVisitRead|dto.VisitRead)
def visit(visit_id:UUID,db:DB,user:Participant):
    return repo.visit_view(one(db,repo.visits(user).where(Visit.id==visit_id),'Visit'),user)


@router.post('/visits/{visit_id}/cancel',response_model=dto.VisitRead)
def cancel_visit(visit_id:UUID,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.cancel_visit(s,u,visit_id))


@router.patch('/admin/visits/{visit_id}',response_model=dto.AgencyVisitRead)
def update_visit(visit_id:UUID,data:dto.VisitUpdate,db:DB,user:Agency):
    return write(db,user,['admin'],lambda s,u:svc.update_visit(s,u,visit_id,data))


@router.post('/conversations',response_model=dto.ConversationRead,status_code=201)
def create_conversation(data:dto.ConversationCreate,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.create_conversation(s,u,data))


@router.get('/conversations',response_model=Page[dto.ConversationRead])
@router.get('/admin/conversations',response_model=Page[dto.ConversationRead],dependencies=[Depends(require_roles('admin'))])
def conversations(db:DB,user:Participant,page:PageNumber=1,page_size:PageSize=20):
    rows,total=repo.page(db,repo.conversations(user),page,page_size,[Conversation.updated_at.desc(),Conversation.id])
    return Page(items=[repo.conversation_view(db,r[0],user) for r in rows],total=total,page=page,page_size=page_size)


@router.get('/conversations/{conversation_id}',response_model=dto.ConversationRead)
def conversation(conversation_id:UUID,db:DB,user:Participant):
    return repo.conversation_view(db,svc.owned_conversation(db,user,conversation_id),user)


@router.get('/conversations/{conversation_id}/messages',response_model=Page[dto.MessageRead])
def messages(conversation_id:UUID,db:DB,user:Participant,page:PageNumber=1,page_size:PageSize=20):
    svc.owned_conversation(db,user,conversation_id)
    query=select(Message,User.role).join(User,User.id==Message.sender_id).where(Message.conversation_id==conversation_id)
    rows,total=repo.page(db,query,page,page_size,[Message.created_at,Message.id])
    return Page(items=[repo.message_view(*r) for r in rows],total=total,page=page,page_size=page_size)


@router.post('/conversations/{conversation_id}/messages',response_model=dto.MessageRead,status_code=201)
def send_message(conversation_id:UUID,data:dto.MessageCreate,db:DB,user:Participant):
    return write(db,user,['tenant','admin'],lambda s,u:svc.send_message(s,u,conversation_id,data))


@router.post('/conversations/{conversation_id}/read',response_model=dto.ReadResult)
def read_messages(conversation_id:UUID,db:DB,user:Participant):
    return write(db,user,['tenant','admin'],lambda s,u:svc.mark_read(s,u,conversation_id))


@router.get('/admin/users/{user_id}',response_model=UserProfile)
def admin_user(user_id:UUID,db:DB,user:Agency):
    return one(db,select(User).where(User.id==user_id),'User')


@router.patch('/admin/users/{user_id}',response_model=UserProfile)
def update_user(user_id:UUID,data:dto.AdminUserUpdate,db:DB,user:Agency):
    actor=tx.Actor.from_user(user)
    return write(db,user,['admin'],lambda s,u:svc.update_user(s,u,user_id,data,actor))


@router.post('/saved-listings',response_model=dto.SavedRead,status_code=201)
def save(data:dto.SavedCreate,db:DB,user:Tenant):
    return write(db,user,['tenant'],lambda s,u:svc.save_listing(s,u,data.listing_id))


@router.get('/saved-listings',response_model=Page[dto.SavedDetail])
def saved(db:DB,user:Tenant,page:PageNumber=1,page_size:PageSize=20):
    rows,total=repo.page(db,select(SavedListing).where(SavedListing.tenant_id==user.id),page,page_size,[SavedListing.created_at.desc(),SavedListing.id])
    items=[]
    for (item,) in rows:
        row=db.execute(inventory.listing_rows().where(Listing.id==item.listing_id,Listing.status=='published')).first()
        items.append(dto.SavedDetail(id=item.id,listing_id=item.listing_id,created_at=item.created_at,
            listing=inventory_service.public_view(db,*row) if row else None))
    return Page(items=items,total=total,page=page,page_size=page_size)


@router.delete('/saved-listings/{saved_id}',status_code=204)
def unsave(saved_id:UUID,db:DB,user:Tenant):
    write(db,user,['tenant'],lambda s,u:svc.delete_saved(s,u,saved_id))
    return Response(status_code=204)


@router.get('/dashboard/statistics',response_model=dto.DashboardStatistics)
def dashboard(db:DB,user:CurrentUser): return reporting.dashboard(db,user)


@router.get('/occupancy',response_model=dto.OccupancyReport)
@router.get('/admin/occupancy',response_model=dto.OccupancyReport,dependencies=[Depends(require_roles('admin'))])
def occupancy(db:DB,user:CurrentUser,as_of:date|None=None,page:PageNumber=1,page_size:PageSize=20):
    return reporting.occupancy(db,user,as_of,page,page_size)
