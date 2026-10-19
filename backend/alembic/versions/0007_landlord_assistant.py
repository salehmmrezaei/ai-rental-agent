"""Enable private landlord assistant conversations."""
from alembic import op

revision = "0007_landlord_assistant"
down_revision = "0006_agency_assistant"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_assistant_threads_user_role"), "assistant_threads", type_="check")
    op.create_check_constraint("user_role", "assistant_threads", "user_role IN ('tenant', 'landlord', 'admin')")


def downgrade():
    # The narrower check refuses downgrade while landlord history exists; never discard it.
    op.drop_constraint(op.f("ck_assistant_threads_user_role"), "assistant_threads", type_="check")
    op.create_check_constraint("user_role", "assistant_threads", "user_role IN ('tenant', 'admin')")
