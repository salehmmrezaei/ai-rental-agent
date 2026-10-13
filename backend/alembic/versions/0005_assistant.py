"""Tenant assistant history and explicitly confirmed actions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_assistant"
down_revision = "0004_operations"
branch_labels = None
depends_on = None


def records():
    return [sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.create_table("assistant_threads", *records(),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("tenant_role", sa.String(20), nullable=False, server_default="tenant"),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("history", JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["tenant_id", "tenant_role"], ["users.id", "users.role"], ondelete="CASCADE"),
        sa.CheckConstraint("tenant_role = 'tenant'", name="tenant_role"),
        sa.CheckConstraint("version >= 0", name="version"),
        sa.UniqueConstraint("id", "tenant_id"))
    op.create_index("ix_assistant_threads_tenant_id", "assistant_threads", ["tenant_id"])
    op.create_table("assistant_messages", *records(),
        sa.Column("thread_id", sa.UUID(), sa.ForeignKey("assistant_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("listings", JSONB(), nullable=False, server_default="[]"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="role"))
    op.create_index("ix_assistant_messages_thread_id", "assistant_messages", ["thread_id"])
    op.create_table("assistant_actions", *records(),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", JSONB()),
        sa.ForeignKeyConstraint(["thread_id", "tenant_id"], ["assistant_threads.id", "assistant_threads.tenant_id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('save_listing', 'apply', 'request_visit', 'contact_agency', 'send_message', 'withdraw_application', 'cancel_visit')", name="kind"),
        sa.CheckConstraint("status IN ('pending', 'confirmed', 'cancelled')", name="status"))
    for column in ("thread_id", "tenant_id", "message_id"):
        op.create_index(f"ix_assistant_actions_{column}", "assistant_actions", [column])


def downgrade():
    for table in ("assistant_actions", "assistant_messages", "assistant_threads"):
        op.drop_table(table)
