from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.models import RentalRequest, RentalContract, User, Visit, Message, Conversation
from app.repositories.inventory import today
from app.services import operations as svc, transactions as tx
from app.schemas.operations import Approval
from conftest import application, contract
from test_auth import api, token_for, headers
from test_inventory import actors, publish, draft

PREFIX='/api/v1'


def apply(api,actors,lid,offset=10,length=30,actor='tenant'):
    response=api.post(PREFIX+'/applications',headers=actors[actor],json={'listing_id':lid,'start_date':str(today()+timedelta(days=offset)),
        'end_date':str(today()+timedelta(days=offset+length)),'note':'Synthetic application'})
    assert response.status_code==201,response.text
    return response.json()


def approve(api,actors,rid,**body): return api.post(f'{PREFIX}/admin/applications/{rid}/approve',headers=actors['admin'],json=body)


def visit_request(api,actors,lid,actor='tenant'):
    response=api.post(PREFIX+'/visits',headers=actors[actor],json={'listing_id':lid,'requested_at':(svc.now()+timedelta(days=2)).isoformat()})
    assert response.status_code==201,response.text
    return response.json()['id']


def test_application_to_contract_workflow(api,engine,inventory,actors):
    lid=publish(api,inventory,actors)
    req=apply(api,actors,lid)
    assert api.get(PREFIX+'/applications',headers=actors['tenant']).json()['total']==1
    assert api.post(f"{PREFIX}/admin/applications/{req['id']}/review",headers=actors['admin']).json()['status']=='reviewing'
    response=approve(api,actors,req['id'],monthly_rent='675.50')
    assert response.status_code==200,response.text
    c=response.json(); assert c['status']=='confirmed' and c['monthly_rent']=='675.50'
    assert approve(api,actors,req['id']).json()['id']==c['id']
    assert approve(api,actors,req['id'],monthly_rent='700').status_code==409
    assert api.get(f"{PREFIX}/applications/{req['id']}",headers=actors['tenant']).json()['status']=='approved'
    assert api.get(PREFIX+'/contracts',headers=actors['tenant']).json()['total']==1
    owner=api.get(f"{PREFIX}/contracts/{c['id']}",headers=actors['owner']).json()
    assert 'tenant_id' not in owner and 'rental_request_id' not in owner
    assert api.get(f"{PREFIX}/contracts/{c['id']}",headers=actors['other_owner']).status_code==404
    assert api.patch(f"{PREFIX}/admin/contracts/{c['id']}",headers=actors['admin'],json={'status':'active'}).status_code==409
    assert api.patch(f"{PREFIX}/admin/contracts/{c['id']}",headers=actors['admin'],json={'monthly_rent':'680'}).status_code==200
    assert api.patch(f"{PREFIX}/admin/contracts/{c['id']}",headers=actors['admin'],json={'status':'cancelled'}).json()['status']=='cancelled'
    again=apply(api,actors,lid)
    assert approve(api,actors,again['id']).status_code==200
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(RentalContract))==2


@pytest.mark.parametrize('action,expected',[('withdraw','withdrawn'),('reject','rejected')])
def test_application_decisions(api,inventory,actors,action,expected):
    lid=publish(api,inventory,actors); req=apply(api,actors,lid)
    if action=='withdraw': response=api.post(f"{PREFIX}/applications/{req['id']}/withdraw",headers=actors['tenant'])
    else: response=api.post(f"{PREFIX}/admin/applications/{req['id']}/reject",headers=actors['admin'],json={'review_note':'Synthetic rejection'})
    assert response.status_code==200,response.text
    assert response.json()['status']==expected
    assert approve(api,actors,req['id']).status_code==409
    assert api.get(PREFIX+'/contracts',headers=actors['tenant']).json()['total']==0


@pytest.mark.parametrize('bad',[
    {'start_date':'2000-01-01','end_date':'2000-02-01'},
    {'end_date':'2000-01-01'}, {'tenant_id':str(uuid4())}, {'status':'approved'}])
def test_application_validation(api,inventory,actors,bad):
    lid=publish(api,inventory,actors)
    payload={'listing_id':lid,'start_date':str(today()+timedelta(days=10)),'end_date':str(today()+timedelta(days=30))}|bad
    assert api.post(PREFIX+'/applications',headers=actors['tenant'],json=payload).status_code==422


def test_duplicate_and_unpublished_application(api,inventory,actors):
    lid=draft(api,inventory,actors)
    payload={'listing_id':lid,'start_date':str(today()),'end_date':str(today()+timedelta(days=20))}
    assert api.post(PREFIX+'/applications',headers=actors['tenant'],json=payload).status_code==404
    assert api.post(f'{PREFIX}/listings/{lid}/submit',headers=actors['owner']).status_code==200
    for status in ['approved','published']: assert api.patch(f'{PREFIX}/admin/listings/{lid}/status',headers=actors['admin'],json={'status':status}).status_code==200
    assert api.post(PREFIX+'/applications',headers=actors['tenant'],json=payload).status_code==201
    assert api.post(PREFIX+'/applications',headers=actors['tenant'],json=payload).status_code==409


@pytest.mark.parametrize('winner,loser',[('room','room'),('room','apartment'),('apartment','room')])
def test_approval_rechecks_conflicts_atomically(api,engine,inventory,actors,winner,loser):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    lids={u:publish(api,inventory,actors,u) for u in set([winner,loser])}
    first=apply(api,actors,lids[winner]); second=apply(api,actors,lids[loser],actor='other')
    assert approve(api,actors,first['id']).status_code==200
    assert approve(api,actors,second['id']).status_code==409
    assert api.get(f"{PREFIX}/applications/{second['id']}",headers=actors['other']).json()['status']=='submitted'
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(RentalContract))==1


def test_approval_rechecks_publication(api,inventory,actors):
    lid=publish(api,inventory,actors); req=apply(api,actors,lid)
    assert api.patch(f'{PREFIX}/admin/listings/{lid}/status',headers=actors['admin'],json={'status':'unpublished'}).status_code==200
    assert approve(api,actors,req['id']).status_code==409
    assert api.get(f"{PREFIX}/applications/{req['id']}",headers=actors['tenant']).json()['status']=='submitted'


@pytest.mark.parametrize('isolation',['READ COMMITTED','REPEATABLE READ','SERIALIZABLE'])
def test_concurrent_apartment_room_approvals(engine,api,inventory,actors,isolation):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    a=apply(api,actors,publish(api,inventory,actors,'apartment'))
    b=apply(api,actors,publish(api,inventory,actors,'room'),actor='other')
    with Session(engine) as s: actor=tx.Actor.from_user(s.get(User,inventory['admin']))
    barrier=Barrier(2)
    isolated=engine.execution_options(isolation_level=isolation)
    def perform(rid):
        first=True
        def operation(s,u):
            nonlocal first
            # Read before the barrier to establish concurrent snapshots.
            s.scalar(select(RentalRequest).where(RentalRequest.id==UUID(rid)))
            if first: first=False; barrier.wait(timeout=10)
            return svc.approve(s,u,UUID(rid),Approval())
        try: tx.run(isolated,actor,{'admin'},operation); return 200
        except Exception as exc:
            from app.errors import ApiError
            if isinstance(exc,ApiError): return exc.status_code
            raise
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(perform,[a['id'],b['id']]))
    assert sorted(results)==[200,409]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(RentalContract))==1
        assert s.scalar(select(func.count()).select_from(RentalRequest).where(RentalRequest.status=='submitted'))==1


def test_independent_rooms_and_adjacent_contracts(api,inventory,actors):
    lid=publish(api,inventory,actors,'room'); lb=publish(api,inventory,actors,'room_b')
    for req in [apply(api,actors,lid),apply(api,actors,lb),apply(api,actors,lid,offset=40)]:
        assert approve(api,actors,req['id']).status_code==200


def test_early_termination_releases_dates_preserves_history(api,engine,inventory,actors):
    lid=publish(api,inventory,actors)
    start=today()-timedelta(days=5); end=today()+timedelta(days=60)
    with Session(engine) as s,s.begin():
        rid=application(s,inventory,start=start,end=end)
        cid=contract(s,inventory,rid,start=start,end=end,status='active')
    term=today()+timedelta(days=5)
    response=api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['admin'],json={'status':'terminated','terminated_on':str(term)})
    assert response.status_code==200,response.text
    assert response.json()['end_date']==str(end) and response.json()['effective_end_date']==str(term)
    assert api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['admin'],json={'status':'terminated','terminated_on':str(term+timedelta(days=1))}).status_code==409
    assert approve(api,actors,apply(api,actors,lid,offset=5)['id']).status_code==200
    report=api.get(PREFIX+'/occupancy',headers=actors['owner']).json()['summary']
    assert report['occupied_units']==1 and report['total_units']==2 and report['contracted_monthly_rent']=='650.00'
    future=api.get(PREFIX+'/occupancy',headers=actors['owner'],params={'as_of':str(term)}).json()['summary']
    assert future['occupied_units']==1


def test_contract_lifecycle_completion(api,engine,inventory,actors):
    start=today()-timedelta(days=40); end=today()-timedelta(days=5)
    with Session(engine) as s,s.begin():
        rid=application(s,inventory,start=start,end=end); cid=contract(s,inventory,rid,start=start,end=end)
    response=api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['admin'],json={'status':'completed'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    assert api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['admin'],json={'monthly_rent':'100'}).status_code==409


@pytest.mark.parametrize('path',['applications','visits','conversations','admin/applications','admin/contracts','admin/visits','admin/conversations','admin/occupancy'])
def test_role_boundaries(api,actors,path):
    assert api.get(PREFIX+'/'+path).status_code==401
    assert api.get(PREFIX+'/'+path,headers=actors['owner']).status_code==403
    if path.startswith('admin/'): assert api.get(PREFIX+'/'+path,headers=actors['tenant']).status_code==403


def test_cross_tenant_records_are_hidden(api,engine,inventory,actors):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    lid=publish(api,inventory,actors); req=apply(api,actors,lid); cid=approve(api,actors,req['id']).json()['id']; vid=visit_request(api,actors,lid)
    for path in [f"applications/{req['id']}",f'contracts/{cid}',f'visits/{vid}']:
        assert api.get(PREFIX+'/'+path,headers=actors['other']).status_code==404
    assert api.post(f"{PREFIX}/applications/{req['id']}/withdraw",headers=actors['other']).status_code==404
    assert api.post(f'{PREFIX}/visits/{vid}/cancel',headers=actors['other']).status_code==404
    for path in ['applications','contracts','visits']: assert api.get(PREFIX+'/'+path,headers=actors['other']).json()['total']==0


def test_visit_scheduling_overlap_and_cancellation(api,engine,inventory,actors):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    lid=publish(api,inventory,actors); v1=visit_request(api,actors,lid); v2=visit_request(api,actors,lid,'other')
    start=svc.now()+timedelta(days=3)
    schedule={'status':'scheduled','scheduled_at':start.isoformat(),'duration_minutes':45}
    first=api.patch(f'{PREFIX}/admin/visits/{v1}',headers=actors['admin'],json=schedule)
    assert first.status_code==200,first.text
    assert first.json()['assigned_admin_id']==str(inventory['admin'])
    assert api.patch(f'{PREFIX}/admin/visits/{v2}',headers=actors['admin'],json=schedule).status_code==409
    schedule['scheduled_at']=(start+timedelta(minutes=45)).isoformat()
    assert api.patch(f'{PREFIX}/admin/visits/{v2}',headers=actors['admin'],json=schedule).status_code==200
    assert api.patch(f'{PREFIX}/admin/visits/{v1}',headers=actors['admin'],json={'status':'completed'}).status_code==409
    assert 'assigned_admin_id' not in api.get(f'{PREFIX}/visits/{v1}',headers=actors['tenant']).json()
    assert api.post(f'{PREFIX}/visits/{v1}/cancel',headers=actors['tenant']).status_code==200
    schedule['scheduled_at']=start.isoformat()
    assert api.patch(f'{PREFIX}/admin/visits/{v2}',headers=actors['admin'],json=schedule).status_code==200


def test_visit_tenant_overlap_with_different_staff(api,engine,inventory,actors):
    lid=publish(api,inventory,actors); a=visit_request(api,actors,lid); b=visit_request(api,actors,lid)
    with Session(engine) as s,s.begin():
        staff=User(email='synthetic.agent2@example.com',password_hash='unusable',full_name='Synthetic Staff',role='admin'); s.add(staff); s.flush(); sid=staff.id
    schedule={'status':'scheduled','scheduled_at':(svc.now()+timedelta(days=4)).isoformat()}
    assert api.patch(f'{PREFIX}/admin/visits/{a}',headers=actors['admin'],json=schedule).status_code==200
    assert api.patch(f'{PREFIX}/admin/visits/{b}',headers=actors['admin'],json=schedule|{'assigned_admin_id':str(sid)}).status_code==409


@pytest.mark.parametrize('payload',[{'requested_at':'2027-01-01T10:00:00'}, {'requested_at':'2000-01-01T10:00:00Z'}, {'tenant_id':str(uuid4())}])
def test_visit_validation(api,inventory,actors,payload):
    lid=publish(api,inventory,actors)
    assert api.post(PREFIX+'/visits',headers=actors['tenant'],json={'listing_id':lid,'requested_at':(svc.now()+timedelta(days=1)).isoformat()}|payload).status_code==422


def test_visit_completion_and_rejection(api,inventory,actors,monkeypatch):
    lid=publish(api,inventory,actors); vid=visit_request(api,actors,lid)
    start=svc.now()+timedelta(days=4)
    assert api.patch(f'{PREFIX}/admin/visits/{vid}',headers=actors['admin'],json={'status':'scheduled','scheduled_at':start.isoformat()}).status_code==200
    monkeypatch.setattr(svc,'now',lambda:start+timedelta(hours=1))
    response=api.patch(f'{PREFIX}/admin/visits/{vid}',headers=actors['admin'],json={'status':'completed'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    monkeypatch.undo()
    other=visit_request(api,actors,lid)
    assert api.patch(f'{PREFIX}/admin/visits/{other}',headers=actors['admin'],json={'status':'rejected'}).status_code==422
    assert api.patch(f'{PREFIX}/admin/visits/{other}',headers=actors['admin'],json={'status':'rejected','agency_note':'Synthetic explanation'}).status_code==200


def test_messaging_privacy_and_read_receipts(api,engine,inventory,actors):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    response=api.post(PREFIX+'/conversations',headers=actors['tenant'],json={'subject':'Synthetic support','initial_message':'Rental question'})
    assert response.status_code==201,response.text
    cid=response.json()['id']
    assert api.get(f'{PREFIX}/conversations/{cid}',headers=actors['admin']).json()['unread_count']==1
    for suffix in ['', '/messages']:
        assert api.get(f'{PREFIX}/conversations/{cid}{suffix}',headers=actors['other']).status_code==404
        assert api.get(f'{PREFIX}/conversations/{cid}{suffix}',headers=actors['owner']).status_code==403
    assert api.post(f'{PREFIX}/conversations/{cid}/messages',headers=actors['other'],json={'body':'Intrusion'}).status_code==404
    assert api.post(f'{PREFIX}/conversations/{cid}/read',headers=actors['tenant']).json()['updated']==0
    assert api.post(f'{PREFIX}/conversations/{cid}/read',headers=actors['admin']).json()['updated']==1
    reply=api.post(f'{PREFIX}/conversations/{cid}/messages',headers=actors['admin'],json={'body':'Synthetic answer'})
    assert reply.status_code==201 and reply.json()['sender_type']=='agency' and 'sender_id' not in reply.json()
    assert api.get(PREFIX+'/dashboard/statistics',headers=actors['tenant']).json()['counts']['unread_messages']==1
    assert api.post(f'{PREFIX}/conversations/{cid}/read',headers=actors['tenant']).json()['updated']==1
    assert api.post(f'{PREFIX}/conversations/{cid}/read',headers=actors['tenant']).json()['updated']==0
    assert api.get(f'{PREFIX}/conversations/{cid}/messages',headers=actors['tenant']).json()['total']==2
    assert api.get(PREFIX+'/conversations',headers=actors['other']).json()['total']==0


def test_admin_account_controls_and_revocation(api,inventory,actors):
    uid=inventory['tenant']
    assert api.get(f'{PREFIX}/admin/users/{uid}',headers=actors['admin']).status_code==200
    assert api.patch(f'{PREFIX}/admin/users/{uid}',headers=actors['admin'],json={'role':'admin'}).status_code==422
    response=api.patch(f'{PREFIX}/admin/users/{uid}',headers=actors['admin'],json={'is_active':False})
    assert response.status_code==200 and response.json()['is_active'] is False
    assert 'password_hash' not in response.json() and 'token_version' not in response.json()
    assert api.get(PREFIX+'/dashboard/statistics',headers=actors['tenant']).status_code==401
    assert api.patch(f'{PREFIX}/admin/users/{uid}',headers=actors['admin'],json={'is_active':True}).status_code==200
    assert api.get(PREFIX+'/users/me',headers=actors['tenant']).status_code==401
    assert api.patch(f"{PREFIX}/admin/users/{inventory['admin']}",headers=actors['admin'],json={'is_active':False}).status_code==409


def test_saved_listing_privacy_and_unpublication(api,engine,inventory,actors):
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    lid=publish(api,inventory,actors)
    response=api.post(PREFIX+'/saved-listings',headers=actors['tenant'],json={'listing_id':lid})
    assert response.status_code==201,response.text
    sid=response.json()['id']
    assert api.post(PREFIX+'/saved-listings',headers=actors['tenant'],json={'listing_id':lid}).json()['id']==sid
    assert api.get(PREFIX+'/saved-listings',headers=actors['tenant']).json()['items'][0]['listing']['id']==lid
    assert api.delete(f'{PREFIX}/saved-listings/{sid}',headers=actors['other']).status_code==404
    assert api.patch(f'{PREFIX}/admin/listings/{lid}/status',headers=actors['admin'],json={'status':'unpublished'}).status_code==200
    assert api.get(PREFIX+'/saved-listings',headers=actors['tenant']).json()['items'][0]['listing'] is None
    assert api.delete(f'{PREFIX}/saved-listings/{sid}',headers=actors['tenant']).status_code==204


def test_occupancy_apartment_counts_physical_rooms_once(api,engine,inventory,actors):
    start=today()-timedelta(days=5); end=today()+timedelta(days=5)
    with Session(engine) as s,s.begin():
        rid=application(s,inventory,unit='apartment',start=start,end=end)
        contract(s,inventory,rid,unit='apartment',start=start,end=end,status='active')
    report=api.get(PREFIX+'/occupancy',headers=actors['owner']).json()['summary']
    assert report['total_units']==2 and report['occupied_units']==2 and report['occupancy_percent']=='100.00'
    assert report['contracted_monthly_rent']=='650.00'
    assert api.get(PREFIX+'/occupancy',headers=actors['other_owner']).json()['total']==0
    assert api.get(PREFIX+'/occupancy',headers=actors['tenant']).status_code==403
    assert api.get(PREFIX+'/dashboard/statistics',headers=actors['owner']).json()['occupancy']==report


@pytest.mark.parametrize('path',['applications','contracts','visits','conversations','saved-listings','occupancy'])
def test_pagination_and_private_cache(api,actors,path):
    role='owner' if path=='occupancy' else 'tenant'
    response=api.get(f'{PREFIX}/{path}',headers=actors[role])
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert api.get(f'{PREFIX}/{path}?page_size=101',headers=actors[role]).status_code==422


@pytest.mark.parametrize('code',['40001','40P01'])
def test_transaction_retry_rolls_back_and_reexecutes(engine,inventory,code):
    with Session(engine) as s: actor=tx.Actor.from_user(s.get(User,inventory['tenant']))
    calls=[]
    def operation(s,u):
        calls.append(u.id)
        row=Conversation(tenant_id=u.id,subject='Synthetic retry')
        s.add(row); s.flush()
        if len(calls)==1:
            s.execute(text(f"DO $$ BEGIN RAISE EXCEPTION 'Synthetic retry' USING ERRCODE='{code}'; END $$"))
        return row.id
    cid=tx.run(engine,actor,{'tenant'},operation)
    assert len(calls)==2
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Conversation))==1
        assert s.get(Conversation,cid) is not None


def test_transaction_retry_exhaustion_is_bounded(engine,inventory):
    from app.errors import ApiError
    with Session(engine) as s: actor=tx.Actor.from_user(s.get(User,inventory['tenant']))
    calls=[]
    def operation(s,u):
        calls.append(1)
        s.add(Conversation(tenant_id=u.id,subject='Synthetic rollback')); s.flush()
        s.execute(text("DO $$ BEGIN RAISE EXCEPTION 'Synthetic serialization failure' USING ERRCODE='40001'; END $$"))
    with pytest.raises(ApiError) as failure: tx.run(engine,actor,{'tenant'},operation)
    assert failure.value.status_code==409 and failure.value.code=='transaction_conflict'
    assert len(calls)==3
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Conversation))==0


def test_transaction_retry_reauthorizes_actor(engine,inventory,monkeypatch):
    from app.errors import ApiError
    with Session(engine) as s: actor=tx.Actor.from_user(s.get(User,inventory['tenant']))
    calls=[]
    def operation(s,u):
        calls.append(1)
        s.execute(text("DO $$ BEGIN RAISE EXCEPTION 'Synthetic serialization failure' USING ERRCODE='40001'; END $$"))
    def revoke(_):
        with Session(engine) as s,s.begin(): s.get(User,actor.id).token_version+=1
    monkeypatch.setattr(tx.time,'sleep',revoke)
    with pytest.raises(ApiError) as failure: tx.run(engine,actor,{'tenant'},operation)
    assert failure.value.status_code==401 and len(calls)==1


@pytest.mark.parametrize('kind',['application','visit','conversation','message'])
def test_operation_identity_is_database_immutable(engine,inventory,kind):
    from sqlalchemy.exc import IntegrityError
    with Session(engine) as s,s.begin():
        if kind=='application':
            rid=application(s,inventory,status='submitted'); table='rental_requests'; change="end_date=end_date+1"
        elif kind=='visit':
            obj=Visit(tenant_id=inventory['tenant'],rental_unit_id=inventory['room'],requested_at=svc.now()+timedelta(days=2))
            s.add(obj); s.flush(); rid=obj.id; table='visits'; change="requested_at=requested_at+interval '1 hour'"
        else:
            conv=Conversation(tenant_id=inventory['tenant'],subject='Synthetic conversation'); s.add(conv); s.flush()
            if kind=='conversation': rid=conv.id; table='conversations'; change=f"tenant_id='{inventory['other']}'"
            else:
                obj=Message(conversation_id=conv.id,sender_id=inventory['tenant'],body='Synthetic original')
                s.add(obj); s.flush(); rid=obj.id; table='messages'; change="body='Altered'"
    with pytest.raises(IntegrityError) as failure:
        with Session(engine) as s,s.begin(): s.execute(text(f'UPDATE {table} SET {change} WHERE id=:id'),{'id':rid})
    assert failure.value.orig.sqlstate=='23514'


def test_concurrent_visit_scheduling_across_properties(engine,api,inventory,actors):
    from app.errors import ApiError
    from app.schemas.operations import VisitUpdate
    from test_inventory import prop_payload
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    first=visit_request(api,actors,publish(api,inventory,actors))
    prop=api.post(PREFIX+'/properties',headers=actors['owner'],json=prop_payload()).json()
    unit=api.post(f"{PREFIX}/properties/{prop['id']}/units",headers=actors['owner'],json={'kind':'room','name':'Synthetic Room','monthly_rent':'500'}).json()
    second=visit_request(api,actors,publish(api,inventory|{'room':unit['id']},actors),actor='other')
    with Session(engine) as s: actor=tx.Actor.from_user(s.get(User,inventory['admin']))
    barrier=Barrier(2)
    data=VisitUpdate(status='scheduled',scheduled_at=svc.now()+timedelta(days=3))
    def perform(vid):
        def operation(s,u):
            barrier.wait(timeout=10)
            return svc.update_visit(s,u,UUID(vid),data)
        try: tx.run(engine,actor,{'admin'},operation); return 200
        except ApiError as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(perform,[first,second]))
    assert sorted(results)==[200,409]
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Visit).where(Visit.status=='scheduled'))==1


def test_inactive_applicant_cannot_be_approved(api,inventory,actors):
    lid=publish(api,inventory,actors); req=apply(api,actors,lid)
    assert api.patch(f"{PREFIX}/admin/users/{inventory['tenant']}",headers=actors['admin'],json={'is_active':False}).status_code==200
    assert approve(api,actors,req['id']).status_code==409
    assert api.get(f"{PREFIX}/applications/{req['id']}",headers=actors['admin']).json()['status']=='submitted'


def test_contract_creation_endpoint_and_owner_write_protection(api,inventory,actors):
    lid=publish(api,inventory,actors); req=apply(api,actors,lid)
    payload={'application_id':req['id']}
    assert api.post(PREFIX+'/admin/contracts',headers=actors['owner'],json=payload).status_code==403
    response=api.post(PREFIX+'/admin/contracts',headers=actors['admin'],json=payload)
    assert response.status_code==201,response.text
    cid=response.json()['id']
    assert api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['tenant'],json={'status':'cancelled'}).status_code==403
    assert api.patch(f'{PREFIX}/admin/contracts/{cid}',headers=actors['owner'],json={'status':'cancelled'}).status_code==403
    assert api.get(PREFIX+'/admin/contracts',headers=actors['admin']).json()['total']==1


def test_concurrent_admins_cannot_deactivate_each_other(engine,inventory):
    from app.errors import ApiError
    from app.schemas.operations import AdminUserUpdate
    with Session(engine) as s,s.begin():
        other=User(email='synthetic.second.admin@example.com',password_hash='unusable',full_name='Synthetic Second Admin',role='admin')
        s.add(other); s.flush()
        actors=[tx.Actor.from_user(s.get(User,inventory['admin'])),tx.Actor.from_user(other)]
    barrier=Barrier(2)
    def perform(index):
        actor=actors[index]; target=actors[1-index].id
        def operation(s,u):
            barrier.wait(timeout=10)
            return svc.update_user(s,u,target,AdminUserUpdate(is_active=False),actor)
        try: tx.run(engine,actor,{'admin'},operation); return 200
        except ApiError as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(perform,[0,1]))
    assert sorted(results)==[200,401]
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(User).where(User.role=='admin',User.is_active.is_(True)))==1


def test_downgrade_refuses_contracts_depending_on_termination(engine,inventory):
    import os
    from pathlib import Path
    import subprocess
    import sys
    start=today()-timedelta(days=10); end=today()+timedelta(days=30); termination=today()
    with Session(engine) as s,s.begin():
        rid=application(s,inventory,start=start,end=end); cid=contract(s,inventory,rid,start=start,end=end,status='active')
        c=s.get(RentalContract,cid); c.status='terminated'; c.terminated_on=termination; s.flush()
        rid2=application(s,inventory,start=termination,end=end); contract(s,inventory,rid2,start=termination,end=end)
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','downgrade','0003_inventory'],cwd=root,
        env=os.environ|{'DATABASE_URL':engine.url.render_as_string(hide_password=False)},capture_output=True,text=True,timeout=30)
    assert result.returncode!=0 and 'Cannot downgrade leases that depend on effective termination' in result.stderr
    with Session(engine) as s:
        assert s.scalar(text('SELECT version_num FROM alembic_version'))=='0004_operations'
        assert s.get(RentalContract,cid).terminated_on==termination
        assert s.scalar(select(func.count()).select_from(RentalContract))==2
