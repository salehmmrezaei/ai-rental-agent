from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.dependencies import require_property_owner, require_unit_owner
from app.main import create_app
from app.models import User, Property, RentalUnit
from app.security import hash_password, verify_password

PASSWORD = 'Synthetic-Password-2027'
KEY = 'phase2-test-only-signing-key-at-least-32-bytes-long'


@pytest.fixture
def api(engine, inventory, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused@localhost/unused')
    monkeypatch.setenv('JWT_SECRET', KEY)
    monkeypatch.setenv('AUTH_RATE_LIMIT', '100')
    get_settings.cache_clear()
    with Session(engine) as s, s.begin():
        encoded = hash_password(PASSWORD)
        s.execute(update(User).values(password_hash=encoded))
        other_owner = User(email='other-landlord@example.test', full_name='Synthetic Second Landlord',
                           password_hash=encoded, role='landlord')
        s.add(other_owner); s.flush(); inventory['other_owner'] = other_owner.id
    app = create_app()
    def session():
        with Session(engine) as s: yield s
    app.dependency_overrides[get_session] = session
    # Test-only routes exercise the exact dependencies that inventory CRUD will use.
    @app.get('/_test/properties/{property_id}', include_in_schema=False)
    def guarded_property(prop: Annotated[Property, Depends(require_property_owner)]):
        return {'id':str(prop.id)}
    @app.get('/_test/units/{unit_id}', include_in_schema=False)
    def guarded_unit(unit: Annotated[RentalUnit, Depends(require_unit_owner)]):
        return {'id':str(unit.id)}
    with TestClient(app) as client: yield client
    get_settings.cache_clear()


def login(api, email='tenant@example.test', password=PASSWORD):
    # API tests adapt inherited .test fixture addresses to reserved example.com
    # addresses in token_for; no delivery or external email is used.
    response = api.post('/api/v1/auth/login', json={'email':email,'password':password})
    return response


def register(api, email='synthetic.new@example.com', role='tenant'):
    return api.post('/api/v1/auth/register', json={
        'email':email, 'password':PASSWORD, 'full_name':'Synthetic New User', 'role':role})


def token_for(api, engine, inventory, key='tenant'):
    # Normalize fixture email to a syntactically valid reserved example.com address.
    email = f'synthetic.{key}@example.com'
    with Session(engine) as s, s.begin():
        s.execute(update(User).where(User.id==inventory[key]).values(email=email))
    response=login(api,email)
    assert response.status_code==200, response.text
    return response.json()['access_token']


def headers(token): return {'Authorization':f'Bearer {token}'}


@pytest.mark.parametrize('role', ['tenant','landlord'])
def test_register_login_profile_persisted(api, engine, role):
    response=register(api, role=role)
    assert response.status_code==201, response.text
    data=response.json()
    assert data['role']==role and 'password_hash' not in data and 'password' not in data
    with Session(engine) as s:
        user=s.scalar(select(User).where(User.email==data['email']))
        assert user.password_hash.startswith('$argon2id$')
        assert user.password_hash != PASSWORD and verify_password(PASSWORD, user.password_hash)
    response=login(api, 'synthetic.new@example.com')
    assert response.status_code==200, response.text
    assert response.headers['cache-control']=='no-store'
    result=response.json(); assert result['expires_in']==1800 and result['token_type']=='bearer'
    assert api.get('/api/v1/users/me', headers=headers(result['access_token'])).json()['id']==data['id']


def test_registration_normalizes_and_rejects_duplicate(api):
    assert register(api, '  SYNTHETIC.NEW@EXAMPLE.COM  ').status_code==201
    response=register(api)
    assert response.status_code==409
    assert response.json()['error']['code']=='email_conflict'


@pytest.mark.parametrize('extra', [{'role':'admin'},{'is_active':True},{'password_hash':'injected'},{'token_version':0}])
def test_public_registration_cannot_set_privileged_fields(api, extra):
    payload={'email':'synthetic.new@example.com','password':PASSWORD,'full_name':'Synthetic New User'}
    payload.update(extra)
    assert api.post('/api/v1/auth/register',json=payload).status_code==422


@pytest.mark.parametrize('change', [{'password':'short'},{'password':'x'*129},{'email':'invalid'}, {'full_name':'   '}, {'full_name':'x'*151}])
def test_register_validation_does_not_echo_secrets(api, change):
    data={'email':'synthetic.new@example.com','password':PASSWORD,'full_name':'Synthetic New User'}
    data.update(change)
    response=api.post('/api/v1/auth/register',json=data)
    assert response.status_code==422
    assert PASSWORD not in response.text
    assert 'input' not in response.text


def test_passwords_have_unique_salts():
    a,b=hash_password(PASSWORD),hash_password(PASSWORD)
    assert a!=b and verify_password(PASSWORD,a) and not verify_password('wrong',a)
    assert not verify_password(PASSWORD,'invalid-unusable-hash')


def test_unknown_and_wrong_password_indistinguishable(api):
    register(api)
    absent=login(api,'synthetic.absent@example.com')
    wrong=login(api,'synthetic.new@example.com','incorrect-password')
    assert absent.status_code==wrong.status_code==401
    assert absent.json()==wrong.json()
    assert absent.headers['www-authenticate']=='Bearer'


def test_deactivation_revokes_existing_token_and_blocks_login(api, engine, inventory):
    token=token_for(api,engine,inventory)
    with Session(engine) as s, s.begin(): s.execute(update(User).where(User.id==inventory['tenant']).values(is_active=False))
    assert api.get('/api/v1/users/me', headers=headers(token)).status_code==401
    assert login(api,'synthetic.tenant@example.com').status_code==401


@pytest.mark.parametrize('authorization', [None,'Basic abc','Bearer broken-token'])
def test_missing_or_malformed_auth(api, authorization):
    h={'Authorization':authorization} if authorization else {}
    assert api.get('/api/v1/users/me',headers=h).status_code==401


def signed_claims(user_id):
    now=datetime.now(timezone.utc)
    return {'sub':str(user_id),'jti':str(uuid4()),'iat':now,'nbf':now,'exp':now+timedelta(minutes=30),
            'iss':'ai-rental-agent','aud':'ai-rental-agent-api','type':'access','token_version':0}


@pytest.mark.parametrize('change', ['expired','future','issuer','audience','subject','missing_exp','version','type','algorithm','signature','unknown_user'])
def test_reject_invalid_signed_tokens(api, inventory, change):
    claims=signed_claims(inventory['tenant']); algorithm='HS256'; key=KEY
    if change=='expired': claims['exp']=datetime.now(timezone.utc)-timedelta(seconds=1)
    if change=='future': claims['nbf']=datetime.now(timezone.utc)+timedelta(minutes=5)
    if change=='issuer': claims['iss']='wrong'
    if change=='audience': claims['aud']='wrong'
    if change=='subject': claims['sub']='not-a-uuid'
    if change=='missing_exp': del claims['exp']
    if change=='version': claims['token_version']=True
    if change=='type': claims['type']='refresh'
    if change=='algorithm': algorithm='HS384'
    if change=='signature': key='other-test-only-signing-key-which-is-long-enough'
    if change=='unknown_user': claims['sub']=str(uuid4())
    token=jwt.encode(claims,key,algorithm=algorithm)
    assert api.get('/api/v1/users/me',headers=headers(token)).status_code==401


def test_logout_revokes_all_tokens(api, engine, inventory):
    first=token_for(api,engine,inventory); second=login(api,'synthetic.tenant@example.com').json()['access_token']
    assert api.post('/api/v1/auth/logout',headers=headers(first)).status_code==204
    for token in [first,second]: assert api.get('/api/v1/users/me',headers=headers(token)).status_code==401
    assert login(api,'synthetic.tenant@example.com').status_code==200


def test_profile_name_persists_without_exposing_hash(api,engine,inventory):
    token=token_for(api,engine,inventory)
    response=api.patch('/api/v1/users/me',headers=headers(token),json={'full_name':'  Synthetic Updated Name  '})
    assert response.status_code==200 and response.json()['full_name']=='Synthetic Updated Name'
    assert 'password_hash' not in response.text
    assert api.get('/api/v1/users/me',headers=headers(token)).json()['full_name']=='Synthetic Updated Name'


@pytest.mark.parametrize('payload', [{'role':'admin'},{'is_active':False},{'email':None},{'full_name':'  '},{}, {'email':'synthetic.changed@example.com'}])
def test_profile_rejects_privilege_escalation_and_invalid_changes(api,engine,inventory,payload):
    token=token_for(api,engine,inventory)
    assert api.patch('/api/v1/users/me',headers=headers(token),json=payload).status_code==422


def test_email_change_requires_password_and_revokes_tokens(api,engine,inventory):
    token=token_for(api,engine,inventory)
    payload={'email':'SYNTHETIC.CHANGED@EXAMPLE.COM','current_password':'wrong-password'}
    assert api.patch('/api/v1/users/me',headers=headers(token),json=payload).status_code==403
    payload['current_password']=PASSWORD
    response=api.patch('/api/v1/users/me',headers=headers(token),json=payload)
    assert response.status_code==200 and response.json()['email']=='synthetic.changed@example.com'
    assert api.get('/api/v1/users/me',headers=headers(token)).status_code==401
    assert login(api,'synthetic.tenant@example.com').status_code==401
    assert login(api,'synthetic.changed@example.com').status_code==200


def test_duplicate_email_change_rolls_back(api,engine,inventory):
    token=token_for(api,engine,inventory)
    register(api)
    response=api.patch('/api/v1/users/me',headers=headers(token),json={'email':'synthetic.new@example.com','current_password':PASSWORD})
    assert response.status_code==409
    assert api.get('/api/v1/users/me',headers=headers(token)).json()['email']=='synthetic.tenant@example.com'


def test_password_change_requires_current_and_invalidates_old_credentials(api,engine,inventory):
    token=token_for(api,engine,inventory)
    data={'current_password':'wrong-password','new_password':'Synthetic-New-Password-2027'}
    assert api.put('/api/v1/users/me/password',headers=headers(token),json=data).status_code==403
    data['current_password']=PASSWORD
    assert api.put('/api/v1/users/me/password',headers=headers(token),json=data).status_code==204
    assert api.get('/api/v1/users/me',headers=headers(token)).status_code==401
    assert login(api,'synthetic.tenant@example.com').status_code==401
    assert login(api,'synthetic.tenant@example.com',data['new_password']).status_code==200


@pytest.mark.parametrize('role,expected', [('tenant',403),('owner',403),('admin',200)])
def test_admin_list_requires_live_admin_role(api,engine,inventory,role,expected):
    token=token_for(api,engine,inventory,role)
    response=api.get('/api/v1/admin/users?page=1&page_size=2',headers=headers(token))
    assert response.status_code==expected
    if expected==200:
        assert len(response.json()['items'])==2 and response.json()['total']==5
        assert 'password_hash' not in response.text and 'token_version' not in response.text
        assert api.get('/api/v1/admin/users?page_size=101',headers=headers(token)).status_code==422


def test_permissions_use_database_role_not_token_claim(api,engine,inventory):
    token=token_for(api,engine,inventory,'admin')
    with Session(engine) as s,s.begin(): s.execute(update(User).where(User.id==inventory['admin']).values(role='tenant'))
    assert api.get('/api/v1/admin/users',headers=headers(token)).status_code==403


def test_profile_reads_are_self_or_admin_only(api,engine,inventory):
    token=token_for(api,engine,inventory)
    assert api.get(f"/api/v1/users/{inventory['tenant']}",headers=headers(token)).status_code==200
    assert api.get(f"/api/v1/users/{inventory['other']}",headers=headers(token)).status_code==404
    admin=token_for(api,engine,inventory,'admin')
    assert api.get(f"/api/v1/users/{inventory['other']}",headers=headers(admin)).status_code==200


@pytest.mark.parametrize('role,expected', [('owner',200),('other_owner',404),('tenant',404),('admin',200)])
@pytest.mark.parametrize('resource', ['properties','units'])
def test_property_and_unit_ownership(api,engine,inventory,role,expected,resource):
    token=token_for(api,engine,inventory,role)
    target=inventory['property' if resource=='properties' else 'room']
    assert api.get(f'/_test/{resource}/{target}',headers=headers(token)).status_code==expected
    assert api.get(f'/_test/{resource}/{uuid4()}',headers=headers(token)).status_code==404


def test_admin_cli_and_duplicate_safety(api,engine,monkeypatch,capsys):
    from app import admin
    monkeypatch.setattr(admin,'get_engine',lambda:engine)
    monkeypatch.setattr('sys.argv',['admin','--email','synthetic.cli@example.com','--full-name','Synthetic CLI Admin'])
    monkeypatch.setattr(admin,'getpass',lambda prompt:PASSWORD)
    assert admin.main()==0
    result=login(api,'synthetic.cli@example.com')
    assert result.status_code==200 and result.json()['user']['role']=='admin'
    assert admin.main()==1
    assert PASSWORD not in capsys.readouterr().out


def test_auth_rate_limit(monkeypatch):
    monkeypatch.setenv('JWT_SECRET',KEY)
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://unused@localhost/unused')
    monkeypatch.setenv('AUTH_RATE_LIMIT','2')
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        # Invalid schemas never access the database but still count as auth attempts.
        for _ in range(2): assert c.post('/api/v1/auth/login',json={}).status_code==422
        response=c.post('/api/v1/auth/login',json={},headers={'X-Forwarded-For':'1.2.3.4'})
        assert response.status_code==429 and int(response.headers['retry-after'])>0
        assert c.get('/api/v1/health/live').status_code==200
    get_settings.cache_clear()


def test_server_requires_secret(monkeypatch):
    from app.config import Settings
    for value in [None,'short','replace-with-a-random-secret-at-least-32-bytes']:
        settings=Settings(_env_file=None,database_url='postgresql+psycopg://unused/unused',jwt_secret=value)
        with pytest.raises(ValueError): settings.signing_key()
