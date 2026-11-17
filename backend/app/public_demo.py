"""Restricted public personas over immutable shared synthetic rental records.

Docker defaults to disposable memory (one worker). The serverless entrypoint uses
shared PostgreSQL operational tables, so visitor state survives instance changes.
"""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict
from typing import Literal
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.config import get_settings
from app.dependencies import DB
from app.errors import ApiError
from app.models import Property, PropertyImage, User
from app.schemas.auth import TokenResponse, UserProfile
from app.security import create_demo_token, unauthorized
from app.seed import DEMO_EMAILS, footprint, record_id
from app.throttle import AuthThrottle


@dataclass(frozen=True)
class DemoIdentity:
    user_id: UUID
    role: str
    expires: float


class DemoSessionStore:
    def __init__(self):
        self._sessions: dict[str, DemoIdentity] = {}
        self._lock = Lock()

    def issue(self, user: User) -> str:
        settings = get_settings()
        with self._lock:
            now = monotonic()
            self._sessions = {sid: item for sid, item in self._sessions.items() if item.expires > now}
            if len(self._sessions) >= settings.demo_max_sessions:
                raise ApiError(503, "demo_capacity", "The demo is busy. Please try again shortly.", {"Retry-After": "60"})
            sid = str(uuid4())
            self._sessions[sid] = DemoIdentity(user.id, user.role, now + settings.demo_session_minutes * 60)
            return sid

    def require(self, sid: str, user_id: UUID, role: str) -> None:
        with self._lock:
            identity = self._sessions.get(sid)
            if identity is None or identity.expires <= monotonic():
                self._sessions.pop(sid, None)
                raise unauthorized()
            if identity.user_id != user_id or identity.role != role:
                raise unauthorized()

    def discard(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)
        from app.services.simulated_assistant import discard_demo_session
        discard_demo_session(sid)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
        from app.services.simulated_assistant import reset_demo_state
        reset_demo_state()


_store = DemoSessionStore()


def get_demo_store(db=None):
    if get_settings().demo_state_backend == 'postgres':
        from app.shared_demo import PostgresDemoStore
        return PostgresDemoStore(db)
    return _store


def validate_demo_dataset(db) -> None:
    """Fail closed rather than expose unrelated data through the agency persona.

    Public mode needs a dedicated database containing the complete reserved seed.
    This check performs reads only and never repairs or removes operator data.
    """
    if get_settings().demo_state_backend == 'postgres':
        from sqlalchemy import text
        if not db.scalar(text('SELECT casa_demo_dataset_valid()')):
            raise ApiError(503, 'demo_dataset_required', 'A complete, dedicated synthetic demo database is required.')
        return
    for model, ids in footprint().items():
        count, outsiders = db.execute(select(func.count(), func.count().filter(model.id.not_in(ids)))
                                      .select_from(model)).one()
        if count != len(ids) or outsiders:
            raise ApiError(503, "demo_dataset_required", "A complete, dedicated synthetic demo database is required.")
    if db.scalar(select(Property.id).where(Property.is_synthetic.is_(False)).limit(1)):
        raise ApiError(503, "demo_dataset_required", "Only synthetic demo properties may be exposed.")
    if db.scalar(select(User.id).where(~User.email.endswith("@example.com")).limit(1)):
        raise ApiError(503, "demo_dataset_required", "Only synthetic demo accounts may be exposed.")
    # Public images must be the bundled fictional samples, never unrelated uploads.
    from app.demo_images import bundled_image
    photos = list(db.scalars(select(PropertyImage)))
    expected_photos = {record_id("photo", i) for i in range(1200)}
    if {photo.id for photo in photos} != expected_photos or any(bundled_image(photo) is None for photo in photos):
        raise ApiError(503, "demo_dataset_required", "The bundled synthetic demo photos are required.")


class DemoAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["tenant", "landlord", "admin"]


router = APIRouter(prefix="/demo", tags=["public demonstration"])


@router.get("/status")
def status():
    settings = get_settings()
    return {"enabled": settings.public_demo_mode, "read_only": True,
            "assistant_mode": "simulated" if settings.public_demo_mode else
                ("live" if settings.assistant_available() else "unavailable"),
            "roles": ["tenant", "landlord", "admin"] if settings.public_demo_mode else []}


@router.post("/access", response_model=TokenResponse)
def access(data: DemoAccess, db: DB, request: Request, response: Response):
    if not get_settings().public_demo_mode:
        raise ApiError(404, "not_found", "Public demo access is disabled")
    key = request.client.host if request.client else "unknown"
    delay = request.app.state.demo_access_throttle.retry_after(key)
    if delay:
        raise ApiError(429, "rate_limited", "Too many demo sessions. Please wait a minute.", {"Retry-After": str(delay)})
    validate_demo_dataset(db)
    user = db.get(User, record_id(data.role))
    if user is None or not user.is_active or user.role != data.role or user.email != DEMO_EMAILS[data.role]:
        raise ApiError(503, "demo_dataset_required", "The synthetic demo persona is unavailable.")
    sid = get_demo_store(db).issue(user)
    token, seconds = create_demo_token(user, sid)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(access_token=token, expires_in=seconds, user=UserProfile.model_validate(user))


class PublicDemoPolicy:
    """Default-deny writes before body parsing, including unknown/future API routes."""
    ALLOWED_POSTS = frozenset({"/api/v1/demo/access", "/api/v1/auth/logout", "/api/v1/assistant/chat"})

    def __init__(self, app):
        self.app = app
        settings = get_settings()
        from app.shared_demo import throttle
        self.by_ip = throttle('requests-ip', settings.demo_request_rate_limit)
        self.global_requests = throttle('requests-global', settings.demo_global_rate_limit)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "")
        path = scope.get("path", "").rstrip("/")
        if method not in {"GET", "HEAD", "OPTIONS"} and (method != 'POST' or path not in self.ALLOWED_POSTS):
            # Reject prohibited operations without waking Neon or consuming DB
            # connections, even for huge unauthenticated upload bodies.
            return await JSONResponse(status_code=403, content={"error": {
                "code": "demo_read_only", "message": "This public demo is read-only. Shared rental data cannot be changed."}})(scope, receive, send)
        if path.startswith("/api/v1/") and path not in {"/api/v1/health/live", "/api/v1/demo/status"}:
            address = scope.get("client")
            from starlette.concurrency import run_in_threadpool
            try:
                delay = await run_in_threadpool(self.by_ip.retry_after, address[0] if address else "unknown")
                if not delay:
                    delay = await run_in_threadpool(self.global_requests.retry_after, "all")
            except SQLAlchemyError:
                return await JSONResponse(status_code=503, headers={'Retry-After':'10'},
                    content={'error':{'code':'database_unavailable', 'message':'The demo database is waking or unavailable. Please try again.'}})(scope, receive, send)
            if delay:
                return await JSONResponse(status_code=429, headers={"Retry-After": str(delay)},
                    content={"error": {"code": "rate_limited", "message": "The demo is busy. Please wait a minute."}})(scope, receive, send)
        if method not in {"GET", "HEAD", "OPTIONS"}:
            # These three endpoints take tiny JSON bodies. Bound them even when
            # Content-Length is absent or dishonest, without spooling uploads.
            chunks, total = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > 16384:
                    return await JSONResponse(status_code=413, content={"error": {
                        "code": "request_too_large", "message": "Demo request exceeds size limit."}})(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)
