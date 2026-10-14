"""Allow private agency assistant conversations and confirmed agency actions."""
from alembic import op

revision = "0006_agency_assistant"
down_revision = "0005_assistant"
branch_labels = None
depends_on = None

TENANT_KINDS = "'save_listing', 'apply', 'request_visit', 'contact_agency', 'send_message', 'withdraw_application', 'cancel_visit'"
AGENCY_KINDS = "'create_property', 'update_property', 'create_unit', 'update_unit', 'create_listing', 'update_listing', 'change_listing_status', 'review_application', 'approve_application', 'reject_application', 'update_visit', 'send_tenant_message'"


def upgrade():
    op.drop_constraint(op.f("ck_assistant_threads_tenant_role"), "assistant_threads", type_="check")
    op.alter_column("assistant_threads", "tenant_id", new_column_name="user_id")
    op.alter_column("assistant_threads", "tenant_role", new_column_name="user_role")
    op.alter_column("assistant_actions", "tenant_id", new_column_name="user_id")
    op.execute("ALTER INDEX ix_assistant_threads_tenant_id RENAME TO ix_assistant_threads_user_id")
    op.execute("ALTER INDEX ix_assistant_actions_tenant_id RENAME TO ix_assistant_actions_user_id")
    op.execute("ALTER TABLE assistant_threads RENAME CONSTRAINT fk_assistant_threads_tenant_id_users TO fk_assistant_threads_user_id_users")
    op.create_check_constraint("user_role", "assistant_threads", "user_role IN ('tenant', 'admin')")
    op.drop_constraint(op.f("ck_assistant_actions_kind"), "assistant_actions", type_="check")
    op.create_check_constraint("kind", "assistant_actions", f"kind IN ({TENANT_KINDS}, {AGENCY_KINDS})")


def downgrade():
    # Narrowing checks refuse to discard agency history; incompatible rows must be handled explicitly.
    op.drop_constraint(op.f("ck_assistant_actions_kind"), "assistant_actions", type_="check")
    op.create_check_constraint("kind", "assistant_actions", f"kind IN ({TENANT_KINDS})")
    op.drop_constraint(op.f("ck_assistant_threads_user_role"), "assistant_threads", type_="check")
    op.create_check_constraint("tenant_role", "assistant_threads", "user_role = 'tenant'")
    op.alter_column("assistant_actions", "user_id", new_column_name="tenant_id")
    op.alter_column("assistant_threads", "user_id", new_column_name="tenant_id")
    op.alter_column("assistant_threads", "user_role", new_column_name="tenant_role")
    op.execute("ALTER INDEX ix_assistant_threads_user_id RENAME TO ix_assistant_threads_tenant_id")
    op.execute("ALTER INDEX ix_assistant_actions_user_id RENAME TO ix_assistant_actions_tenant_id")
    op.execute("ALTER TABLE assistant_threads RENAME CONSTRAINT fk_assistant_threads_user_id_users TO fk_assistant_threads_tenant_id_users")
