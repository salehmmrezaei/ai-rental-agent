from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(session: Session = Depends(get_session)):
    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "0003_inventory":
            raise HTTPException(503, "Database migration required")
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable or not migrated") from None
    return {"status": "ok", "database": "ready"}
