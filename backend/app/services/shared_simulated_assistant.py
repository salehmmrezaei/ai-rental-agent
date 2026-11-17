"""Same deterministic queries/cards; visitor state lives only in PostgreSQL.

Each chat locks its visitor row until the state commit. Distinct visitors proceed
independently; concurrent chat/logout cannot lose turns or resurrect deleted state.
"""
from datetime import datetime, timedelta, timezone
import json
import re
from uuid import UUID, uuid4
from app.errors import ApiError
from app.shared_demo import PostgresDemoStore
from app.schemas.assistant import ThreadDetail, ThreadRead, MessageRead, VisitReference
from app.schemas.inventory import Page
from app.services import simulated_assistant as sim, agency_assistant
from app.services.assistant_tools import visit_reference


def visitor(db, user, lock=False):
    sid = getattr(user, 'demo_session_id', None)
    if not sid:
        raise ApiError(401, 'demo_session_required', 'Choose a demo role first.')
    row = PostgresDemoStore(db).require(sid, user.id, user.role, lock)
    expiry = row.state.get('history_expires_at')
    if expiry and datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
        row.state = {}
    return row


def owned(row, thread_id):
    item = next((t for t in row.state.get('threads', []) if t['id'] == str(thread_id)), None)
    if item is None:
        raise ApiError(404, 'not_found', 'Simulated conversation expired or was not found.')
    return ThreadDetail.model_validate(item)


def threads(db, user):
    row = visitor(db, user)
    return [ThreadRead.model_validate(t) for t in reversed(row.state.get('threads', []))]


def thread_detail(db, user, thread_id):
    return owned(visitor(db, user), thread_id)


def filters_for(db, user, tid, mid, field):
    row = visitor(db, user)
    thread = owned(row, tid)
    message = next((m for m in thread.messages if m.id == mid and m.role == 'assistant'), None)
    filters = row.state.get('filters', {}).get(str(mid))
    if message is None or getattr(message, field) is None or filters is None:
        raise ApiError(404, 'not_found', 'Simulated search was not found.')
    return filters


def listing_search_page(db, user, thread_id, message_id, page):
    if user.role != 'tenant':
        raise ApiError(403, 'forbidden', 'Tenant role required')
    return sim._search(db, filters_for(db, user, thread_id, message_id, 'listing_search'), page)


def visit_search_page(db, user, thread_id, message_id, page):
    agency_assistant.require_admin(user)
    filters = filters_for(db, user, thread_id, message_id, 'visit_search')
    result = agency_assistant.records(db, user, **filters, page=page)
    return Page[VisitReference](items=[VisitReference(**visit_reference(item)) for item in result['items']],
        page=page, page_size=6, total=result['total'])


def chat(db, user, data):
    row = visitor(db, user, lock=True)
    thread = owned(row, data.thread_id) if data.thread_id else None
    if thread and len(thread.messages) >= sim.MAX_TURNS * 2:
        raise ApiError(422, 'chat_limit', 'This simulated conversation is full. Start a new chat.')
    message = data.message
    if data.listing_search_context:
        ctx = data.listing_search_context
        visible = listing_search_page(db, user, data.thread_id, ctx.message_id, ctx.page)
        ordinal = re.search(r'\b(first|second|third|fourth|fifth|sixth)\b', message.casefold())
        if ordinal:
            index = ['first','second','third','fourth','fifth','sixth'].index(ordinal.group(1))
            if index < len(visible.items):
                message += f'\nCurrent home listing ID: {visible.items[index].id}'
    if data.visit_search_context:
        ctx = data.visit_search_context
        visit_search_page(db, user, data.thread_id, ctx.message_id, ctx.page)
    answer = sim._respond(db, user, message)
    instant = datetime.now(timezone.utc)
    if thread is None:
        thread = ThreadDetail(id=uuid4(), title=data.message[:100], updated_at=instant, messages=[])
    response = MessageRead(id=uuid4(), role='assistant', content=answer['content'],
        listings=answer['listings'], listing_search=answer['listing_search'], visit_search=answer['visit_search'],
        created_at=instant + timedelta(microseconds=1))
    thread.messages.extend([MessageRead(id=uuid4(), role='user', content=data.message, created_at=instant), response])
    thread.updated_at = response.created_at
    items = [t for t in row.state.get('threads', []) if t['id'] != str(thread.id)]
    items = (items + [thread.model_dump(mode='json')])[-sim.MAX_THREADS_PER_SESSION:]
    alive = {m['id'] for t in items for m in t['messages']}
    filters = {key:value for key,value in row.state.get('filters', {}).items() if key in alive}
    if answer['filters'] is not None:
        filters[str(response.id)] = answer['filters']
    state = {'threads':items, 'filters':filters,
        'history_expires_at': row.state.get('history_expires_at') or (instant+timedelta(minutes=30)).isoformat()}
    if len(json.dumps(state).encode()) > 131072:
        raise ApiError(422, 'context_limit', 'Temporary history is full. Re-enter a demo role to clear it.')
    row.state = state
    db.commit()
    return thread
