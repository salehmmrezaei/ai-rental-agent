"""Persist tenant listing search filters for card pagination."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_assistant_listing_search"
down_revision = "0007_landlord_assistant"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assistant_messages", sa.Column("listing_search", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("assistant_messages", "listing_search")
