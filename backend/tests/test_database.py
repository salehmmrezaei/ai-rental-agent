from concurrent.futures import ThreadPoolExecutor
from datetime import date
import time

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session
from app.models import Base
from app.models.entities import User, Property, RentalUnit, Listing, RentalRequest, RentalContract, Conversation, Message, PropertyImage, Visit
from conftest import application, contract


def test_migration_matches_models(engine):
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())


@pytest.mark.parametrize('first,second,conflict', [('room','room',True),('room','apartment',True),('apartment','room',True),('apartment','apartment',True),('room','room_b',False)])
def test_overlap_matrix(engine, inventory, first, second, conflict):
    with Session(engine) as s, s.begin():
        r = application(s, inventory, first); contract(s, inventory, r, first)
    if conflict:
        with pytest.raises(IntegrityError) as exc, Session(engine) as s, s.begin():
            r = application(s, inventory, second); contract(s, inventory, r, second)
        assert exc.value.orig.sqlstate == '23P01'
    else:
        with Session(engine) as s, s.begin():
            r = application(s, inventory, second); contract(s, inventory, r, second)


def test_adjacent_dates(engine, inventory):
    with Session(engine) as s, s.begin():
        r = application(s, inventory); contract(s, inventory, r)
        start, end = date(2027,3,1), date(2027,4,1)
        r = application(s, inventory, start=start, end=end)
        contract(s, inventory, r, start=start, end=end)


def test_cancelled_contract_releases_dates(engine, inventory):
    with Session(engine) as s, s.begin():
        r = application(s, inventory); c = contract(s, inventory, r)
        s.execute(update(RentalContract).where(RentalContract.id==c).values(status='cancelled'))
        r = application(s, inventory); contract(s, inventory, r)


@pytest.mark.parametrize('field,value', [('landlord_id','tenant'), ('landlord_id','other')])
def test_owner_role_constraint(engine, inventory, field, value):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(Property(landlord_id=inventory[value], title='Synthetic', description='fixture', city='Rome', address='Synthetic', postal_code='00100'))
        s.flush()


@pytest.mark.parametrize('model,field,value', [(Property,'landlord_id','other'), (RentalUnit,'kind','apartment')])
def test_identity_immutable(engine, inventory, model, field, value):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        target = inventory['property' if model is Property else 'room']
        s.execute(update(model).where(model.id==target).values(**{field: inventory[value] if field == 'landlord_id' else value}))


def test_one_apartment_per_property(engine, inventory):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(RentalUnit(property_id=inventory['property'], kind='apartment', name='Second whole apartment', monthly_rent=1000)); s.flush()


@pytest.mark.parametrize('start,end', [(date(2027,1,1),date(2027,1,1)),(date(2027,3,1),date(2027,1,1))])
def test_empty_or_reversed_dates(engine, inventory, start, end):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        application(s, inventory, start=start, end=end)


def test_contract_requires_approved_request(engine, inventory):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        r=application(s, inventory, status='submitted'); contract(s, inventory, r)


def test_contract_matches_application(engine, inventory):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        r=application(s, inventory); contract(s, inventory, r, start=date(2027,1,2))


def test_contract_dates_immutable(engine, inventory):
    with Session(engine) as s, s.begin():
        r=application(s, inventory); c=contract(s, inventory, r)
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.execute(update(RentalContract).where(RentalContract.id==c).values(end_date=date(2027,4,1)))


@pytest.mark.parametrize('sender,allowed', [('tenant',True),('admin',True),('owner',False),('other',False)])
def test_agency_only_messaging(engine, inventory, sender, allowed):
    with Session(engine) as s, s.begin():
        c=Conversation(tenant_id=inventory['tenant'], subject='Synthetic inquiry'); s.add(c); s.flush(); cid=c.id
    def send():
        with Session(engine) as s, s.begin():
            s.add(Message(conversation_id=cid, sender_id=inventory[sender], body='Synthetic development message')); s.flush()
    if allowed: send()
    else:
        with pytest.raises(IntegrityError): send()


def test_image_cannot_reference_another_property(engine, inventory):
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        p=Property(landlord_id=inventory['owner'], title='Other', description='fixture', city='Milan', address='Synthetic', postal_code='20100'); s.add(p); s.flush()
        s.add(PropertyImage(property_id=p.id, rental_unit_id=inventory['room'], storage_key='fixture.png', alt_text='fixture')); s.flush()


def test_listing_workflow(engine, inventory):
    with Session(engine) as s, s.begin():
        obj=Listing(rental_unit_id=inventory['room'], available_from=date(2027,1,1)); s.add(obj); s.flush(); lid=obj.id
        for state in ['submitted','approved','published','unpublished','published']:
            s.execute(update(Listing).where(Listing.id==lid).values(status=state))
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.execute(update(Listing).where(Listing.id==lid).values(status='draft'))


def test_visit_requires_schedule(engine, inventory):
    from datetime import datetime, timezone
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(Visit(tenant_id=inventory['tenant'], rental_unit_id=inventory['room'], requested_at=datetime.now(timezone.utc), status='scheduled')); s.flush()


def test_application_status_cannot_skip_review(engine, inventory):
    with Session(engine) as s, s.begin(): r=application(s, inventory, status='submitted')
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.execute(update(RentalRequest).where(RentalRequest.id==r).values(status='approved'))


@pytest.mark.parametrize('isolation', ['READ COMMITTED','REPEATABLE READ'])
def test_competing_apartment_and_room_transactions(engine, inventory, isolation):
    with Session(engine) as s, s.begin():
        first=application(s, inventory, 'room'); second=application(s, inventory, 'apartment')
    c1=engine.connect(); t1=c1.begin()
    s1=Session(bind=c1)
    contract(s1, inventory, first)
    def competing():
        with engine.connect().execution_options(isolation_level=isolation) as c2:
            with c2.begin(), Session(bind=c2) as s2:
                s2.execute(text("SET LOCAL application_name = 'rental_conflict_test'"))
                try:
                    contract(s2, inventory, second, 'apartment')
                except DBAPIError as e:
                    return e.orig.sqlstate
                return 'committed'
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(competing)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with engine.connect() as monitor:
                    waiting=monitor.execute(text("SELECT count(*) FROM pg_stat_activity WHERE application_name='rental_conflict_test' AND wait_event_type='Lock'")).scalar_one()
                if waiting: break
                time.sleep(0.02)
            else:
                t1.rollback()
                raise AssertionError('Second transaction never blocked on the property lock')
            t1.commit()
            assert future.result(timeout=10) == ('23P01' if isolation == 'READ COMMITTED' else '40001')
    finally:
        if t1.is_active: t1.rollback()
        s1.close(); c1.close()
    with Session(engine) as s:
        assert len(s.scalars(select(RentalContract)).all())==1


@pytest.mark.parametrize('status', ['active', 'completed', 'terminated'])
def test_historical_contracts_still_block_their_dates(engine, inventory, status):
    with Session(engine) as s, s.begin():
        r = application(s, inventory); c = contract(s, inventory, r)
        s.execute(update(RentalContract).where(RentalContract.id == c).values(status='active'))
        if status != 'active':
            s.execute(update(RentalContract).where(RentalContract.id == c).values(status=status))
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        r = application(s, inventory, 'apartment'); contract(s, inventory, r, 'apartment')


def test_failed_booking_rolls_back_approval(engine, inventory):
    with Session(engine) as s, s.begin():
        r = application(s, inventory); contract(s, inventory, r)
        conflicting = application(s, inventory, 'apartment', status='reviewing')
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.execute(update(RentalRequest).where(RentalRequest.id == conflicting).values(status='approved'))
        contract(s, inventory, conflicting, 'apartment')
    with Session(engine) as s:
        assert s.get(RentalRequest, conflicting).status == 'reviewing'
