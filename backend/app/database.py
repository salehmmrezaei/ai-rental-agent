from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session():
    with Session(get_engine()) as session:
        if get_settings().public_demo_mode:
            # Check anonymous browsing as well as role entry: an accidentally
            # selected real-user database must never become public inventory.
            from app.public_demo import validate_demo_dataset
            validate_demo_dataset(session)
        yield session
