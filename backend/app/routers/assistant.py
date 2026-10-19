from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from app.config import get_settings
from app.dependencies import DB, require_roles
from app.errors import ApiError
from app.models import User
from app.schemas.assistant import AssistantStatus, ChatInput, Confirmation, ThreadRead, ThreadDetail, ActionRead
from app.services import assistant as service
from app.throttle import AuthThrottle

router = APIRouter(prefix="/assistant", tags=["assistant"])
Participant = Annotated[User, Depends(require_roles("tenant", "landlord", "admin"))]


@router.get("/status", response_model=AssistantStatus)
def status(user: Participant):
    available = get_settings().assistant_available()
    ready = {"admin": "Ready to help with agency requests.",
             "landlord": "Ready to help manage your properties and listings.",
             "tenant": "Ready to help with your rental search."}[user.role]
    return AssistantStatus(available=available, message=ready if available else
        "The AI assistant is not configured yet. You can still use your workspace.")


@router.get("/threads", response_model=list[ThreadRead])
def threads(db: DB, user: Participant):
    return service.threads(db, user)


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
def detail(thread_id: UUID, db: DB, user: Participant):
    return service.thread_detail(db, user, thread_id)


@router.post("/chat", response_model=ThreadDetail)
def chat(data: ChatInput, db: DB, user: Participant, request: Request):
    throttle: AuthThrottle = request.app.state.assistant_throttle
    delay = throttle.retry_after(str(user.id))
    if delay:
        raise ApiError(429, "rate_limited", "Too many assistant requests. Please wait a minute.", headers={"Retry-After": str(delay)})
    return service.chat(db, user, data)


@router.post("/actions/{action_id}/confirm", response_model=ActionRead)
def confirm(action_id: UUID, data: Confirmation, db: DB, user: Participant):
    return service.resolve_action(db, user, action_id, True)


@router.post("/actions/{action_id}/cancel", response_model=ActionRead)
def cancel(action_id: UUID, db: DB, user: Participant):
    return service.resolve_action(db, user, action_id, False)
