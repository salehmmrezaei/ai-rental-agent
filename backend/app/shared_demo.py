"""PostgreSQL visitor state and throttling; safe across processes and restarts."""
from datetime import timedelta
import hashlib
import hmac
from uuid import UUID, uuid4
from sqlalchemy import select, delete, func, text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_engine
from app.errors import ApiError
from app.models.demo import DemoVisitor, DemoRateBucket
from app.security import unauthorized


def now(db):
    return db.scalar(select(func.clock_timestamp()))


def cleanup(db):
    db.execute(delete(DemoVisitor).where(DemoVisitor.expires_at <= func.clock_timestamp()))
    db.execute(delete(DemoRateBucket).where(DemoRateBucket.expires_at <= func.clock_timestamp()))


class PostgresDemoStore:
    def __init__(self, db):
        self.db = db

    def issue(self, user):
        db = self.db
        db.execute(text('SELECT pg_advisory_xact_lock(6006010)'))
        cleanup(db)
        if db.scalar(select(func.count()).select_from(DemoVisitor)) >= get_settings().demo_max_sessions:
            raise ApiError(503, 'demo_capacity', 'The demo is busy. Please try again shortly.', {'Retry-After':'60'})
        sid = uuid4()
        db.add(DemoVisitor(id=sid, user_id=user.id, role=user.role, state={},
            expires_at=now(db) + timedelta(minutes=get_settings().demo_session_minutes)))
        db.commit()
        return str(sid)

    def require(self, sid, user_id, role, lock=False):
        query = select(DemoVisitor).where(DemoVisitor.id == UUID(sid), DemoVisitor.user_id == user_id,
            DemoVisitor.role == role, DemoVisitor.expires_at > func.clock_timestamp())
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.db.scalar(query)
        if row is None:
            raise unauthorized()
        return row

    def discard(self, sid):
        self.db.execute(delete(DemoVisitor).where(DemoVisitor.id == UUID(sid)))
        self.db.commit()


class SharedThrottle:
    """Fixed windows, transaction locks and capped rows; no plaintext IP storage."""
    def __init__(self, scope, limit):
        self.scope, self.limit = scope, limit

    def retry_after(self, key):
        secret = get_settings().signing_key().encode()
        digest = hmac.new(secret, (self.scope + ':' + key).encode(), hashlib.sha256).hexdigest()
        with Session(get_engine()) as db, db.begin():
            # Transaction-scoped locks work through Neon's transaction pooler.
            db.execute(text('SELECT pg_advisory_xact_lock(6006011)'))
            instant = now(db)
            db.execute(delete(DemoVisitor).where(DemoVisitor.expires_at <= instant))
            db.execute(delete(DemoRateBucket).where(DemoRateBucket.expires_at <= instant))
            row = db.get(DemoRateBucket, digest)
            if row is None:
                if db.scalar(select(func.count()).select_from(DemoRateBucket)) >= 4096:
                    return 60
                row = DemoRateBucket(key=digest, count=0, expires_at=instant + timedelta(seconds=60))
                db.add(row)
            if row.count >= self.limit:
                return max(1, int((row.expires_at - instant).total_seconds()) + 1)
            row.count += 1
            return 0


def throttle(scope, limit):
    if get_settings().public_demo_mode and get_settings().demo_state_backend == 'postgres':
        return SharedThrottle(scope, limit)
    from app.throttle import AuthThrottle
    return AuthThrottle(limit)
