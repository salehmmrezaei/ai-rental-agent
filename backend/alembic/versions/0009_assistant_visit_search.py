"""Persist agency visit queue cards and their server-owned filters."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_assistant_visit_search"
down_revision = "0008_assistant_listing_search"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assistant_messages", sa.Column("visit_search", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("assistant_messages", "visit_search")
