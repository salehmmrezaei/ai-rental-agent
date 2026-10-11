from fastapi import APIRouter, Response
from app.dependencies import DB, CurrentUser
from app.schemas.auth import Register, Login, TokenResponse, UserProfile
from app.security import create_token
from app.services import auth

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserProfile, status_code=201)
def register(data: Register, db: DB):
    return auth.register(db, data)


@router.post("/login", response_model=TokenResponse)
def login(data: Login, db: DB, response: Response):
    user = auth.login(db, data)
    token, seconds = create_token(user)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(access_token=token, expires_in=seconds, user=UserProfile.model_validate(user))


@router.post("/logout", status_code=204)
def logout(db: DB, user: CurrentUser):
    """Revoke all of the authenticated user's access tokens across devices."""
    auth.logout(db, user)
    return Response(status_code=204)
