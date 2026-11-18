"""Operational demo state only; no rental domain entities are changed."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, Integer, String, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DemoVisitor(Base):
    __tablename__ = 'demo_visitors'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    __table_args__ = (CheckConstraint("role IN ('tenant','landlord','admin')", name='demo_role'),)


class DemoRateBucket(Base):
    __tablename__ = 'demo_rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
