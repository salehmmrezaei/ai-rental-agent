from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response
from app.dependencies import DB, CurrentUser, require_roles
from app.errors import ApiError
from app.models import User
from app.repositories import users
from app.schemas.auth import UserProfile, ProfileUpdate, PasswordUpdate, UserPage
from app.services import auth

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserProfile)
def profile(user: CurrentUser):
    return user


@router.patch("/users/me", response_model=UserProfile)
def update_profile(data: ProfileUpdate, db: DB, user: CurrentUser):
    return auth.update_profile(db, user, data)


@router.put("/users/me/password", status_code=204)
def change_password(data: PasswordUpdate, db: DB, user: CurrentUser):
    auth.change_password(db, user, data)
    return Response(status_code=204)


@router.get("/users/{user_id}", response_model=UserProfile)
def get_profile(user_id: UUID, db: DB, user: CurrentUser):
    if user.role != "admin" and user.id != user_id:
        raise ApiError(404, "not_found", "User not found")
    target = users.by_id(db, user_id)
    if target is None:
        raise ApiError(404, "not_found", "User not found")
    return target


@router.get("/admin/users", response_model=UserPage)
def list_users(db: DB, admin: Annotated[User, Depends(require_roles("admin"))],
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = users.page(db, page, page_size)
    return UserPage(items=[UserProfile.model_validate(u) for u in items], total=total,
                    page=page, page_size=page_size)
