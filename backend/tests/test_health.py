from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.config import get_settings
from app.database import get_session
from app.main import create_app


def client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused@localhost/unused')
    get_settings.cache_clear()
    return TestClient(create_app())


def test_liveness_and_openapi(monkeypatch):
    with client(monkeypatch) as c:
        assert c.get('/api/v1/health/live').json() == {'status':'ok'}
        assert c.get('/openapi.json').status_code == 200


def test_readiness(engine, monkeypatch):
    from sqlalchemy.orm import Session
    with client(monkeypatch) as c:
        def session():
            with Session(engine) as s: yield s
        c.app.dependency_overrides[get_session] = session
        assert c.get('/api/v1/health/ready').json() == {'status':'ok','database':'ready'}


def test_readiness_does_not_leak_errors(monkeypatch):
    class Unavailable:
        def execute(self, *args): raise OperationalError('private connection details', {}, Exception('private'))
    with client(monkeypatch) as c:
        c.app.dependency_overrides[get_session] = lambda: Unavailable()
        response = c.get('/api/v1/health/ready')
        assert response.status_code == 503
        assert 'private' not in response.text


def test_cors_allowlist(monkeypatch):
    with client(monkeypatch) as c:
        headers={'Origin':'http://localhost:5173', 'Access-Control-Request-Method':'GET'}
        assert c.options('/api/v1/health/live', headers=headers).status_code == 200
        headers['Origin']='https://untrusted.example.test'
        assert c.options('/api/v1/health/live', headers=headers).status_code == 400
