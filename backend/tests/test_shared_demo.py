"""Real PostgreSQL tests for independent serverless instances and shared limits."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from app.config import get_settings
from app.database import get_session, database_url
from app.main import create_app
from app.models import Property, AssistantThread, User
from app.models.demo import DemoVisitor, DemoRateBucket
from app.seed import record_id
from app.shared_demo import SharedThrottle, cleanup
from test_public_demo import public_dataset, enter


@pytest.fixture
def instances(engine, public_dataset, monkeypatch):
    for key, value in {'DATABASE_URL': engine.url.render_as_string(hide_password=False),
        'JWT_SECRET':'shared-demo-tests-signing-key-with-at-least-32-bytes',
        'PUBLIC_DEMO_MODE':'true', 'DEMO_STATE_BACKEND':'postgres',
        'DEMO_ACCESS_RATE_LIMIT':'1000', 'ASSISTANT_RATE_LIMIT':'100',
        'DEMO_REQUEST_RATE_LIMIT':'5000', 'DEMO_GLOBAL_RATE_LIMIT':'20000',
        'OPENAI_API_KEY':'accidental-key-never-call-model'}.items():
        monkeypatch.setenv(key,value)
    get_settings.cache_clear()
    import app.database
    monkeypatch.setattr(app.database, 'get_engine', lambda: engine)
    import app.shared_demo
    monkeypatch.setattr(app.shared_demo, 'get_engine', lambda: engine)
    with Session(engine) as db, db.begin():
        db.execute(delete(DemoVisitor)); db.execute(delete(DemoRateBucket))
    def session():
        with Session(engine) as db:
            yield db
    def client():
        app = create_app()
        app.dependency_overrides[get_session] = session
        return TestClient(app)
    yield client
    get_settings.cache_clear()


def test_instances_share_sessions_and_private_chat(instances, engine):
    with instances() as one, instances() as two:
        headers = enter(one)
        other = enter(two)
        answer = one.post('/api/v1/assistant/chat', headers=headers,
            json={'message':'Find rooms in Bologna under 700 euros'})
        assert answer.status_code == 200, answer.text
        thread = answer.json()
        assert thread['messages'][-1]['listings']
        assert two.get('/api/v1/assistant/threads/'+thread['id'], headers=headers).json() == thread
        assert two.get('/api/v1/assistant/threads/'+thread['id'], headers=other).status_code == 404
        assert two.get('/api/v1/assistant/threads', headers=other).json() == []
        assert two.post('/api/v1/auth/logout', headers=headers).status_code == 204
        assert one.get('/api/v1/users/me', headers=headers).status_code == 401
        assert one.get('/api/v1/users/me', headers=other).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AssistantThread)) == 0
        assert db.scalar(select(func.count()).select_from(Property)) == 300


def test_fresh_python_process_restores_chat(instances, engine):
    with instances() as client:
        headers = enter(client)
        reply = client.post('/api/v1/assistant/chat', headers=headers, json={'message':'Show my applications'}).json()
        with Session(engine) as db:
            sid = str(db.scalar(select(DemoVisitor.id)))
    script = '''
import json,sys
from sqlalchemy.orm import Session
from app.database import get_engine
from app.models import User
from app.seed import record_id
from app.services.shared_simulated_assistant import threads
with Session(get_engine()) as db:
    user=db.get(User,record_id('tenant'));user.demo_session_id=sys.argv[1]
    print(json.dumps([str(t.id) for t in threads(db,user)]))
'''
    result = subprocess.run([os.sys.executable,'-c',script,sid],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout) == [reply['id']]


def test_concurrent_turns_are_not_lost(instances):
    with instances() as client:
        headers = enter(client)
        thread = client.post('/api/v1/assistant/chat', headers=headers, json={'message':'Show my applications'}).json()
        def turn(message):
            with instances() as other:
                return other.post('/api/v1/assistant/chat', headers=headers,
                    json={'thread_id':thread['id'], 'message':message})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(turn,['Show my visits','Show my contracts']))
        assert all(r.status_code == 200 for r in results), [r.text for r in results]
        saved = client.get('/api/v1/assistant/threads/'+thread['id'],headers=headers).json()
        assert len(saved['messages']) == 6


def test_expiry_and_cleanup_preserve_rentals(instances, engine):
    with instances() as client:
        headers = enter(client)
        with Session(engine) as db, db.begin():
            db.execute(update(DemoVisitor).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
        assert client.get('/api/v1/users/me', headers=headers).status_code == 401
        with Session(engine) as db, db.begin():
            cleanup(db)
            assert db.scalar(select(func.count()).select_from(DemoVisitor)) == 0
            assert db.scalar(select(func.count()).select_from(Property)) == 300


def test_session_capacity_atomic_under_concurrency(instances, engine, monkeypatch):
    monkeypatch.setenv('DEMO_MAX_SESSIONS','10'); get_settings.cache_clear()
    def visit(_):
        with instances() as client:
            return client.post('/api/v1/demo/access',json={'role':'tenant'}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(visit,range(12)))
    assert statuses.count(200) == 10 and statuses.count(503) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DemoVisitor)) == 10


def test_rate_limits_shared_and_keys_private(instances, engine):
    one, two = SharedThrottle('test',1), SharedThrottle('test',1)
    assert one.retry_after('visitor-address') == 0
    assert two.retry_after('visitor-address') > 0
    with Session(engine) as db, db.begin():
        row = db.scalar(select(DemoRateBucket))
        assert row.key != 'visitor-address' and len(row.key) == 64
        row.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    assert two.retry_after('visitor-address') == 0


def test_history_bounds_and_pagination(instances):
    with instances() as client:
        headers = enter(client)
        history = []
        for _ in range(4):
            reply = client.post('/api/v1/assistant/chat',headers=headers,json={'message':'Find rooms in Bologna'}).json()
            history.append(reply)
        assert len(client.get('/api/v1/assistant/threads',headers=headers).json()) == 3
        assert client.get('/api/v1/assistant/threads/'+history[0]['id'],headers=headers).status_code == 404
        current = history[-1]
        path = f"/api/v1/assistant/threads/{current['id']}/messages/{current['messages'][-1]['id']}/listings?page=2"
        page = client.get(path,headers=headers)
        assert page.status_code == 200 and page.json()['page'] == 2


def test_roles_writes_images_and_no_live_runner(instances, monkeypatch):
    from app.services import rental_agent
    def forbidden(*args,**kwargs):
        pytest.fail('Shared demo invoked a model')
    monkeypatch.setattr(rental_agent,'run_agent',forbidden)
    monkeypatch.setattr(rental_agent,'AsyncOpenAI',forbidden)
    with instances() as client:
        for role in ['tenant','landlord','admin']:
            headers = enter(client,role)
            reply = client.post('/api/v1/assistant/chat',headers=headers,json={'message':'Give me an overview'})
            assert reply.status_code == 200 and 'Simulated' in reply.json()['messages'][-1]['content']
            assert client.post('/api/v1/properties',headers=headers,json={}).status_code == 403
            assert client.patch('/api/v1/users/me',headers=headers,json={}).status_code == 403
            assert client.get('/api/v1/admin/users',headers=headers).status_code == (200 if role=='admin' else 403)
        listing = client.get('/api/v1/listings?page_size=1').json()['items'][0]
        assert client.get(listing['images'][0]['url']).status_code == 200
        assert client.post('/api/v1/auth/register',json={}).status_code == 403


def test_neon_url_and_nullpool(monkeypatch):
    assert database_url('postgres://user:pass@localhost/db').drivername == 'postgresql+psycopg'
    monkeypatch.setenv('DATABASE_URL','postgresql://user:pass@localhost/db')
    monkeypatch.setenv('SERVERLESS_DATABASE','true'); get_settings.cache_clear()
    from app.database import get_engine
    get_engine.cache_clear()
    assert isinstance(get_engine().pool,NullPool)
    get_engine().dispose();get_engine.cache_clear();get_settings.cache_clear()


def test_vercel_entrypoint_has_no_live_dependencies():
    script = '''
import os,sys
os.environ.update(DATABASE_URL='postgresql://unused@localhost/unused',JWT_SECRET='serverless-import-test-secret-at-least-32-bytes')
sys.path.insert(0,'backend')
import vercel_entry
assert 'openai' not in sys.modules and 'agents' not in sys.modules and 'faker' not in sys.modules
assert os.environ['PUBLIC_DEMO_MODE']=='true' and os.environ['DEMO_STATE_BACKEND']=='postgres'
assert os.environ['OPENAI_API_KEY']==''
print('ok')
'''
    result=subprocess.run([os.sys.executable,'-c',script],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='ok'


def test_runtime_database_role_cannot_write_domain_tables(instances, engine):
    from pathlib import Path
    from sqlalchemy.exc import DBAPIError
    script = (Path(__file__).resolve().parents[2]/'deploy/neon-runtime-role.sql').read_text()
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(script)
        with engine.begin() as conn:
            conn.exec_driver_sql('SET LOCAL ROLE casa_runtime')
            assert conn.exec_driver_sql('SELECT casa_demo_dataset_valid()').scalar_one() is True
            conn.exec_driver_sql("INSERT INTO demo_rate_buckets(key,count,expires_at) VALUES ('role-test',1,now()+interval '1 minute')")
        with pytest.raises(DBAPIError) as denied:
            with engine.begin() as conn:
                conn.exec_driver_sql('SET LOCAL ROLE casa_runtime')
                conn.exec_driver_sql("UPDATE users SET full_name='forbidden'")
        assert denied.value.orig.sqlstate == '42501'
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP OWNED BY casa_runtime')
            conn.exec_driver_sql('DROP ROLE casa_runtime')


def test_history_expires_even_when_visitor_session_is_still_valid(instances, engine):
    with instances() as client:
        headers=enter(client)
        thread=client.post('/api/v1/assistant/chat',headers=headers,json={'message':'Show my visits'}).json()
        with Session(engine) as db,db.begin():
            row=db.scalar(select(DemoVisitor))
            row.state={**row.state,'history_expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
        assert client.get('/api/v1/users/me',headers=headers).status_code==200
        assert client.get('/api/v1/assistant/threads',headers=headers).json()==[]
        assert client.get('/api/v1/assistant/threads/'+thread['id'],headers=headers).status_code==404
        assert client.post('/api/v1/assistant/chat',headers=headers,json={'message':'Show my visits'}).status_code==200
