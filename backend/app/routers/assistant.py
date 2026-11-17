from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from app.config import get_settings
from app.dependencies import DB, require_roles
from app.errors import ApiError
from app.models import User
from app.schemas.assistant import AssistantStatus, ChatInput, Confirmation, ThreadRead, ThreadDetail, ActionRead, ListingReference, VisitReference
from app.schemas.inventory import Page
from app.services import simulated_assistant
from app.throttle import AuthThrottle

router = APIRouter(prefix="/assistant", tags=["assistant"])
Participant = Annotated[User, Depends(require_roles("tenant", "landlord", "admin"))]
Tenant = Annotated[User, Depends(require_roles("tenant"))]
Agency = Annotated[User, Depends(require_roles("admin"))]


def current_service():
    if get_settings().public_demo_mode:
        if getattr(get_settings(), 'demo_state_backend', 'memory') == 'postgres':
            from app.services import shared_simulated_assistant
            return shared_simulated_assistant
        return simulated_assistant
    return live_service()


def live_service():
    # Public demo imports neither the Agents SDK nor the OpenAI client.
    from app.services import assistant
    return assistant


@router.get("/status", response_model=AssistantStatus)
def status(user: Participant):
    settings = get_settings()
    if settings.public_demo_mode:
        return AssistantStatus(available=True, mode="simulated", message=
            "Simulated AI Assistant: guided, read-only queries against fictional data. No API key or external model is used. "
            "Conversation history is temporary and expires within 30 minutes.")
    available = settings.assistant_available()
    ready = {"admin": "Ready to help with agency requests.",
             "landlord": "Ready to help manage your properties and listings.",
             "tenant": "Ready to help with your rental search."}[user.role]
    return AssistantStatus(available=available, mode="live" if available else "unavailable", message=ready if available else
        "The AI assistant is not configured yet. You can still use your workspace.")


@router.get("/threads", response_model=list[ThreadRead])
def threads(db: DB, user: Participant):
    return current_service().threads(db, user)


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
def detail(thread_id: UUID, db: DB, user: Participant):
    return current_service().thread_detail(db, user, thread_id)


@router.get("/threads/{thread_id}/messages/{message_id}/listings", response_model=Page[ListingReference])
def listing_search_page(thread_id: UUID, message_id: UUID, db: DB, user: Tenant,
                        page: Annotated[int, Query(ge=1, le=10000)] = 1):
    return current_service().listing_search_page(db, user, thread_id, message_id, page)


@router.get("/threads/{thread_id}/messages/{message_id}/visits", response_model=Page[VisitReference])
def visit_search_page(thread_id: UUID, message_id: UUID, db: DB, user: Agency,
                      page: Annotated[int, Query(ge=1, le=10000)] = 1):
    return current_service().visit_search_page(db, user, thread_id, message_id, page)


@router.post("/chat", response_model=ThreadDetail)
def chat(data: ChatInput, db: DB, user: Participant, request: Request):
    throttle: AuthThrottle = request.app.state.assistant_throttle
    delay = throttle.retry_after(str(getattr(user, "demo_session_id", user.id)))
    if delay:
        raise ApiError(429, "rate_limited", "Too many assistant requests. Please wait a minute.", headers={"Retry-After": str(delay)})
    return current_service().chat(db, user, data)


@router.post("/actions/{action_id}/confirm", response_model=ActionRead)
def confirm(action_id: UUID, data: Confirmation, db: DB, user: Participant):
    if get_settings().public_demo_mode:
        raise ApiError(403, "demo_read_only", "The public demo cannot confirm changes to shared records.")
    return live_service().resolve_action(db, user, action_id, True)


@router.post("/actions/{action_id}/cancel", response_model=ActionRead)
def cancel(action_id: UUID, db: DB, user: Participant):
    if get_settings().public_demo_mode:
        raise ApiError(403, "demo_read_only", "The public demo cannot change shared assistant actions.")
    return live_service().resolve_action(db, user, action_id, False)
