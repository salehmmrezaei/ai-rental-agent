import asyncio
from collections import defaultdict
from datetime import timedelta
import json
import logging
import time
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.config import get_settings
from app.errors import ApiError
from app.models import AssistantThread, AssistantMessage, AssistantAction
from app.schemas.assistant import ActionRead, MessageRead, ThreadRead, ThreadDetail
from app.services import rental_agent, transactions as tx
from app.services.assistant_tools import ToolContext, execute_action
from app.services.operations import now

logger = logging.getLogger(__name__)


def owned_thread(session, user, thread_id, lock=False):
    query = select(AssistantThread).where(AssistantThread.id == thread_id, AssistantThread.user_id == user.id,
                                          AssistantThread.user_role == user.role)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    thread = session.scalar(query)
    if thread is None:
        raise ApiError(404, "not_found", "Assistant conversation not found")
    return thread


def threads(session, user):
    return [ThreadRead.model_validate(t) for t in session.scalars(select(AssistantThread)
        .where(AssistantThread.user_id == user.id, AssistantThread.user_role == user.role)
        .order_by(AssistantThread.updated_at.desc(), AssistantThread.id).limit(20))]


def thread_detail(session, user, thread_id):
    thread = owned_thread(session, user, thread_id)
    actions = defaultdict(list)
    for action in session.scalars(select(AssistantAction).where(AssistantAction.thread_id == thread.id,
            AssistantAction.user_id == user.id).order_by(AssistantAction.created_at, AssistantAction.id)):
        actions[action.message_id].append(ActionRead.model_validate(action))
    messages = [MessageRead(id=m.id, role=m.role, content=m.content, listings=m.listings,
                actions=actions[m.id], created_at=m.created_at) for m in session.scalars(select(AssistantMessage)
                .where(AssistantMessage.thread_id == thread.id).order_by(AssistantMessage.created_at, AssistantMessage.id))]
    return ThreadDetail(id=thread.id, title=thread.title, updated_at=thread.updated_at, messages=messages)


def trim_history(history):
    """Drop complete oldest turns, keeping tool calls and their results together."""
    starts = [i for i, item in enumerate(history) if item.get("role") == "user"]
    while len(json.dumps(history)) > 80000 and len(starts) > 1:
        history = history[starts[1]:]
        starts = [i for i, item in enumerate(history) if item.get("role") == "user"]
    if len(json.dumps(history)) > 100000:
        raise ApiError(422, "context_limit", "Too much context. Start a new chat with a narrower question.")
    return history


def chat(db, user, data):
    settings = get_settings()
    if not settings.assistant_available():
        raise ApiError(503, "assistant_unconfigured", "The AI assistant is not configured yet. Your operator can enable it with an OpenAI API key.")
    actor, bind, role = tx.Actor.from_user(user), db.get_bind(), user.role
    history, version, states = [], 0, []
    if data.thread_id:
        thread = owned_thread(db, user, data.thread_id)
        version, history = thread.version, list(thread.history)
        if version >= 40:
            raise ApiError(422, "chat_limit", "This conversation is full. Start a new chat.")
        states = [{"id": str(a.id), "kind": a.kind, "status": a.status,
                   "expired": a.expires_at <= now(),
                   "result_identifiers": {key: value for key, value in (a.result or {}).items()
                       if key in {"id", "property_id", "rental_unit_id", "rental_request_id"}}}
                  for a in db.scalars(select(AssistantAction)
                  .where(AssistantAction.thread_id == thread.id, AssistantAction.user_id == user.id))]
    # Release the authentication/read transaction while awaiting the external model.
    db.rollback()
    context = ToolContext(bind, actor, role=role)
    history = trim_history(history + [{"role": "user", "content": data.message}])
    started = time.monotonic()
    try:
        result = asyncio.run(rental_agent.run_agent(settings, context, history, json.dumps(states)))
        content = result.final_output
        if not isinstance(content, str) or not content.strip() or len(content) > 12000:
            raise ApiError(502, "assistant_empty_reply", "The assistant could not finish a reply. Please try again.")
        next_history = trim_history(jsonable_encoder(result.to_input_list()))
    except ApiError:
        raise
    except Exception as exc:
        # Provider/SDK exception strings can contain prompts or credentials. Log only type and timing.
        logger.warning("assistant_run outcome=failed error_type=%s elapsed_ms=%d", type(exc).__name__, int((time.monotonic()-started)*1000))
        code = "assistant_timeout" if isinstance(exc, TimeoutError) else "assistant_unavailable"
        raise ApiError(503, code, "The AI assistant is temporarily unavailable. Please try again.") from None

    def persist(session, active_user):
        if data.thread_id:
            thread = owned_thread(session, active_user, data.thread_id, lock=True)
            if thread.version != version:
                raise ApiError(409, "chat_changed", "This chat changed in another request. Reload and send your message again.")
        else:
            thread = AssistantThread(user_id=active_user.id, user_role=active_user.role, title=data.message[:100])
            session.add(thread)
            session.flush()
        thread.version += 1
        thread.history = next_history
        thread.updated_at = now()
        # Explicit ordered timestamps avoid same-transaction timestamp ties.
        sent_at = now()
        session.add(AssistantMessage(thread_id=thread.id, role="user", content=data.message,
                                     created_at=sent_at, listings=[]))
        message = AssistantMessage(thread_id=thread.id, role="assistant", content=content.strip(),
            listings=list(context.listings.values()), created_at=sent_at + timedelta(microseconds=1))
        session.add(message)
        session.flush()
        for proposal in context.proposals:
            session.add(AssistantAction(id=proposal.id, thread_id=thread.id, user_id=active_user.id,
                message_id=message.id, kind=proposal.kind, summary=proposal.summary, payload=proposal.payload,
                expires_at=now()+timedelta(minutes=10)))
        session.flush()
        return thread_detail(session, active_user, thread.id)

    response = tx.run(bind, actor, {context.role}, persist)
    logger.info("assistant_run outcome=ok tools=%d proposals=%d elapsed_ms=%d", context.calls,
                len(context.proposals), int((time.monotonic()-started)*1000))
    return response


def resolve_action(db, user, action_id: UUID, confirm: bool):
    bind, actor, role = db.get_bind(), tx.Actor.from_user(user), user.role
    db.rollback()

    def operation(session, active_user):
        # Lock order is thread then action for all resolutions, serializing this chat's changes.
        thread_id = session.scalar(select(AssistantAction.thread_id).where(AssistantAction.id == action_id,
                                    AssistantAction.user_id == active_user.id))
        if thread_id is None:
            raise ApiError(404, "not_found", "Assistant action not found")
        thread = owned_thread(session, active_user, thread_id, lock=True)
        action = session.scalar(select(AssistantAction).where(AssistantAction.id == action_id,
            AssistantAction.user_id == active_user.id).with_for_update().execution_options(populate_existing=True))
        if action.status == "confirmed" and confirm:
            return ActionRead.model_validate(action)  # Persistent idempotency, including concurrent retries.
        if action.status == "cancelled" and not confirm:
            return ActionRead.model_validate(action)
        if action.status != "pending":
            raise ApiError(409, "action_resolved", "This action has already been resolved")
        if confirm and action.expires_at <= now():
            raise ApiError(409, "action_expired", "This action expired. Ask the assistant to prepare it again.")
        if confirm:
            action.result = jsonable_encoder(execute_action(session, active_user, action.kind, action.payload))
            action.status = "confirmed"
        else:
            action.status = "cancelled"
        thread.version += 1
        thread.updated_at = now()
        session.flush()
        return ActionRead.model_validate(action)

    result = tx.run(bind, actor, {role} & {"tenant", "admin"}, operation)
    logger.info("assistant_action kind=%s outcome=%s", result.kind, result.status)
    return result
