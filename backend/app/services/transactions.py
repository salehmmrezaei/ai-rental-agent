from dataclasses import dataclass
import logging
import random
import time
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.errors import ApiError
from app.models import User
from app.security import unauthorized

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Actor:
    id: UUID
    token_version: int

    @classmethod
    def from_user(cls,user): return cls(user.id,user.token_version)


def authenticate(session, actor, roles):
    user=session.scalar(select(User).where(User.id==actor.id).execution_options(populate_existing=True))
    if user is None or not user.is_active or user.token_version!=actor.token_version: raise unauthorized()
    if user.role not in roles: raise ApiError(403,'forbidden','Your role cannot perform this operation')
    return user


def run(bind, actor, roles, operation, *, attempts=3):
    """Fresh session and authorization on each complete transaction retry."""
    for attempt in range(attempts):
        try:
            with Session(bind) as session:
                with session.begin():
                    user=authenticate(session,actor,roles)
                    result=operation(session,user)
                return result
        except DBAPIError as exc:
            code=getattr(exc.orig,'sqlstate',None)
            if code in {'40001','40P01'}:
                if attempt+1==attempts: raise ApiError(409,'transaction_conflict','Concurrent change; retry this operation') from None
                logger.info('Retrying rental transaction (%s)',code)
                time.sleep(random.uniform(.01,.03)*(attempt+1))
                continue
            if code in {'23P01','23505','23503','23514'}:
                raise ApiError(409,'operation_conflict','Operation conflicts with existing records or reservations') from None
            raise
