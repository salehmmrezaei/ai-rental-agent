"""Add revocable authentication token versions."""
from alembic import op
import sqlalchemy as sa

revision = "0002_auth"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.create_check_constraint(op.f("ck_users_token_version"), "users", "token_version >= 0")


def downgrade():
    op.drop_constraint(op.f("ck_users_token_version"), "users", type_="check")
    op.drop_column("users", "token_version")
