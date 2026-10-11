from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import User


def by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def by_id(session: Session, user_id: UUID, *, lock=False) -> User | None:
    query = select(User).where(User.id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return session.scalar(query)


def page(session: Session, page: int, page_size: int):
    total = session.scalar(select(func.count()).select_from(User))
    users = session.scalars(select(User).order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size).limit(page_size)).all()
    return users, total
