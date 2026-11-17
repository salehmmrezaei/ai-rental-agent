from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context
from sqlalchemy import create_engine, pool
from app.config import get_settings
from app.models import Base
from app.database import database_url


def run():
    settings = get_settings()
    direct = settings.database_direct_url.get_secret_value() if settings.database_direct_url else ''
    url = database_url(direct or settings.database_url)
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True,
                          dialect_opts={"paramstyle": "named"})
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()

run()
