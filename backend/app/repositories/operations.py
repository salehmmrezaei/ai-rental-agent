from sqlalchemy import select, func
from app.errors import ApiError
from app.models import RentalRequest, RentalContract, RentalUnit, Property, Visit, Conversation, Message, User
from app.schemas.operations import ApplicationRead, ContractOwner, ContractPrivate, VisitRead, AgencyVisitRead, ConversationRead, MessageRead


def scoped(query, model, user):
    if user.role == 'admin': return query
    if user.role != 'tenant': raise ApiError(403,'forbidden','Tenant or agency role required')
    return query.where(model.tenant_id == user.id)


def applications(user): return scoped(select(RentalRequest),RentalRequest,user)
def visits(user): return scoped(select(Visit),Visit,user)
def conversations(user): return scoped(select(Conversation),Conversation,user)


def contracts(user):
    query=select(RentalContract,RentalUnit,Property).join(RentalUnit,RentalUnit.id==RentalContract.rental_unit_id).join(Property,Property.id==RentalUnit.property_id)
    if user.role=='tenant': return query.where(RentalContract.tenant_id==user.id)
    if user.role=='landlord': return query.where(Property.landlord_id==user.id)
    if user.role=='admin': return query
    raise ApiError(403,'forbidden','Unsupported role')


def contract_view(contract,unit,prop,user):
    fields={k:getattr(contract,k) for k in ('id','rental_unit_id','start_date','end_date','terminated_on','monthly_rent','status','created_at','updated_at')}
    fields.update(property_id=prop.id,property_title=prop.title,unit_name=unit.name,effective_end_date=contract.terminated_on or contract.end_date)
    if user.role=='landlord': return ContractOwner(**fields)
    return ContractPrivate(**fields,tenant_id=contract.tenant_id,rental_request_id=contract.rental_request_id)


def rental_context(session,unit_id):
    row=session.execute(select(RentalUnit.name,Property.title,Property.id).join(Property,Property.id==RentalUnit.property_id).where(RentalUnit.id==unit_id)).one()
    return {"unit_name":row[0],"property_title":row[1],"property_id":row[2]}


def application_view(session,request):
    return ApplicationRead.model_validate(request).model_copy(update=rental_context(session,request.rental_unit_id))


def visit_view(visit,user,session=None):
    cls=AgencyVisitRead if user.role=='admin' else VisitRead
    result=cls.model_validate(visit)
    return result.model_copy(update=rental_context(session,visit.rental_unit_id)) if session is not None else result


def unread_query(user):
    return select(Message.id).join(User,User.id==Message.sender_id).where(Message.read_at.is_(None),User.role!=user.role)


def conversation_view(session,conversation,user):
    count=session.scalar(select(func.count()).select_from(unread_query(user).where(Message.conversation_id==conversation.id).subquery()))
    return ConversationRead(id=conversation.id,tenant_id=conversation.tenant_id,subject=conversation.subject,
        unread_count=count,created_at=conversation.created_at,updated_at=conversation.updated_at)


def message_view(message,sender_role):
    return MessageRead(id=message.id,conversation_id=message.conversation_id,sender_type='agency' if sender_role=='admin' else 'tenant',
        body=message.body,read_at=message.read_at,created_at=message.created_at)


def page(session,query,page,page_size,order):
    total=session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows=session.execute(query.order_by(*order).offset((page-1)*page_size).limit(page_size)).all()
    return rows,total
