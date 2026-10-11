from typing import Annotated
from uuid import UUID
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_session
from app.errors import ApiError
from app.models import User, Property, RentalUnit
from app.repositories import users
from app.security import decode_token, unauthorized

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_session)]


def current_user(db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if credentials is None:
        raise unauthorized()
    claims = decode_token(credentials.credentials)
    user = users.by_id(db, UUID(claims["sub"]))
    if user is None or not user.is_active or user.token_version != claims["token_version"]:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: str):
    def permitted(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "Your role cannot perform this operation")
        return user
    return permitted


def require_property_owner(property_id: UUID, db: DB, user: CurrentUser) -> Property:
    query = select(Property).where(Property.id == property_id)
    if user.role != "admin":
        if user.role != "landlord":
            raise ApiError(404, "not_found", "Property not found")
        query = query.where(Property.landlord_id == user.id)
    prop = db.scalar(query)
    if prop is None:
        raise ApiError(404, "not_found", "Property not found")
    return prop


def require_unit_owner(unit_id: UUID, db: DB, user: CurrentUser) -> RentalUnit:
    query = select(RentalUnit).join(Property, RentalUnit.property_id == Property.id).where(RentalUnit.id == unit_id)
    if user.role != "admin":
        if user.role != "landlord":
            raise ApiError(404, "not_found", "Rental unit not found")
        query = query.where(Property.landlord_id == user.id)
    unit = db.scalar(query)
    if unit is None:
        raise ApiError(404, "not_found", "Rental unit not found")
    return unit
