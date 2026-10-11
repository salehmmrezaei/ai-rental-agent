from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.errors import ApiError
from app.models import User
from app.repositories import users
from app.schemas.auth import Register, Login, ProfileUpdate, PasswordUpdate
from app.security import hash_password, verify_password, dummy_hash, hasher, unauthorized


def save(session: Session, user: User) -> User:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505" and getattr(exc.orig.diag, "constraint_name", None) == "uq_users_email":
            raise ApiError(409, "email_conflict", "Email is already registered") from None
        raise
    session.refresh(user)
    return user


def register(session: Session, data: Register) -> User:
    user = User(email=str(data.email), full_name=data.full_name, role=data.role,
                password_hash=hash_password(data.password.get_secret_value()))
    session.add(user)
    return save(session, user)


def provision_admin(session: Session, data: Register) -> User:
    # This service is called only by the local CLI, never by a public endpoint.
    user = User(email=str(data.email), full_name=data.full_name, role="admin",
                password_hash=hash_password(data.password.get_secret_value()))
    session.add(user)
    return save(session, user)


def login(session: Session, data: Login) -> User:
    user = users.by_email(session, str(data.email))
    valid = verify_password(data.password.get_secret_value(), user.password_hash if user else dummy_hash())
    if not valid or user is None or not user.is_active:
        raise unauthorized()
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password.get_secret_value())
        return save(session, user)
    return user


def locked_user(session: Session, authenticated: User) -> User:
    version = authenticated.token_version
    user = users.by_id(session, authenticated.id, lock=True)
    if not user or not user.is_active or user.token_version != version:
        raise unauthorized()
    return user


def update_profile(session: Session, authenticated: User, data: ProfileUpdate) -> User:
    user = locked_user(session, authenticated)
    if data.email is not None:
        if not verify_password(data.current_password.get_secret_value(), user.password_hash):
            raise ApiError(403, "invalid_password", "Current password is incorrect")
        if user.email != str(data.email):
            user.email = str(data.email)
            user.token_version += 1
    if data.full_name is not None:
        user.full_name = data.full_name
    return save(session, user)


def change_password(session: Session, authenticated: User, data: PasswordUpdate):
    user = locked_user(session, authenticated)
    if not verify_password(data.current_password.get_secret_value(), user.password_hash):
        raise ApiError(403, "invalid_password", "Current password is incorrect")
    if data.current_password.get_secret_value() == data.new_password.get_secret_value():
        raise ApiError(422, "unchanged_password", "New password must differ from current password")
    user.password_hash = hash_password(data.new_password.get_secret_value())
    user.token_version += 1
    save(session, user)


def logout(session: Session, authenticated: User):
    user = locked_user(session, authenticated)
    user.token_version += 1
    save(session, user)
