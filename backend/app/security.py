from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID, uuid4
import secrets
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from app.config import get_settings
from app.errors import ApiError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def unauthorized() -> ApiError:
    return ApiError(401, "unauthorized", "Invalid or expired credentials", {"WWW-Authenticate": "Bearer"})


def create_token(user) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    seconds = settings.access_token_minutes * 60
    payload = {"sub": str(user.id), "iat": now, "nbf": now,
               "exp": now + timedelta(seconds=seconds), "iss": settings.jwt_issuer,
               "aud": settings.jwt_audience, "jti": str(uuid4()),
               "token_version": user.token_version, "type": "access"}
    return jwt.encode(payload, settings.signing_key(), algorithm="HS256"), seconds


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.signing_key(), algorithms=["HS256"],
            issuer=settings.jwt_issuer, audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iat", "nbf", "iss", "aud", "jti", "token_version", "type"],
                     "strict_aud": True})
        UUID(claims["sub"])
        UUID(claims["jti"])
        if claims["type"] != "access" or type(claims["token_version"]) is not int or claims["token_version"] < 0:
            raise ValueError("Invalid token claims")
        return claims
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise unauthorized() from None
