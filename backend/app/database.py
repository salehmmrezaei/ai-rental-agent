from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import get_settings
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url


def database_url(value):
    url = make_url(value)
    if url.drivername in {'postgres', 'postgresql'}:
        url = url.set(drivername='postgresql+psycopg')
    return url


@lru_cache
def get_engine():
    settings = get_settings()
    options = {'poolclass': NullPool, 'connect_args': {'prepare_threshold': None, 'connect_timeout': 10}} if settings.serverless_database else {'pool_pre_ping': True}
    return create_engine(database_url(settings.database_url), **options)


def get_session():
    with Session(get_engine()) as session:
        if get_settings().public_demo_mode:
            # Check anonymous browsing as well as role entry: an accidentally
            # selected real-user database must never become public inventory.
            from app.public_demo import validate_demo_dataset
            validate_demo_dataset(session)
        yield session
