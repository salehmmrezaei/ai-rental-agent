from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Record


class AssistantThread(Record, Base):
    __tablename__ = "assistant_threads"
    user_id: Mapped[UUID] = mapped_column(index=True)
    user_role: Mapped[str] = mapped_column(String(20), default="tenant", server_default="tenant")
    title: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    history: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "user_role"], ["users.id", "users.role"], ondelete="CASCADE"),
        CheckConstraint("user_role IN ('tenant', 'landlord', 'admin')", name="user_role"),
        CheckConstraint("version >= 0", name="version"),
        UniqueConstraint("id", "user_id"),
    )


class AssistantMessage(Record, Base):
    __tablename__ = "assistant_messages"
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("assistant_threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    listings: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="role"),)


class AssistantAction(Record, Base):
    __tablename__ = "assistant_actions"
    thread_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(index=True)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("assistant_messages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(["thread_id", "user_id"], ["assistant_threads.id", "assistant_threads.user_id"], ondelete="CASCADE"),
        CheckConstraint("kind IN ('save_listing', 'apply', 'request_visit', 'contact_agency', 'send_message', 'withdraw_application', 'cancel_visit', 'create_property', 'update_property', 'create_unit', 'update_unit', 'create_listing', 'update_listing', 'change_listing_status', 'review_application', 'approve_application', 'reject_application', 'update_visit', 'send_tenant_message')", name="kind"),
        CheckConstraint("status IN ('pending', 'confirmed', 'cancelled')", name="status"),
    )
