"""Rental operations, effective termination and conflict-safe visit scheduling."""
from alembic import op
import sqlalchemy as sa

revision = "0004_operations"
down_revision = "0003_inventory"
branch_labels = None
depends_on = None

OLD_CONTRACT_GUARD = r"""
CREATE OR REPLACE FUNCTION guard_contract() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p uuid; k text;
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.rental_unit_id, NEW.tenant_id, NEW.rental_request_id,
      NEW.start_date, NEW.end_date) IS DISTINCT FROM (OLD.rental_unit_id, OLD.tenant_id,
      OLD.rental_request_id, OLD.start_date, OLD.end_date) THEN
    RAISE EXCEPTION 'Contract parties and dates are immutable; cancel and reapply' USING ERRCODE = '23514';
  END IF;
  SELECT property_id, kind INTO p, k FROM rental_units WHERE id = NEW.rental_unit_id;
  UPDATE properties SET booking_revision = booking_revision + 1 WHERE id = p;
  IF NOT EXISTS (SELECT 1 FROM rental_requests WHERE id = NEW.rental_request_id AND status = 'approved') THEN
    RAISE EXCEPTION 'Contract requires an approved application' USING ERRCODE = '23514';
  END IF;
  IF NEW.status <> 'cancelled' AND EXISTS (
    SELECT 1 FROM rental_contracts c JOIN rental_units u ON u.id = c.rental_unit_id
    WHERE u.property_id = p AND c.id <> NEW.id AND c.status <> 'cancelled'
      AND daterange(c.start_date, c.end_date, '[)') && daterange(NEW.start_date, NEW.end_date, '[)')
      AND (u.id = NEW.rental_unit_id OR u.kind = 'apartment' OR k = 'apartment')
  ) THEN
    RAISE EXCEPTION 'Rental dates conflict with an existing contract' USING ERRCODE = '23P01';
  END IF;
  RETURN NEW;
END $$;
"""

NEW_CONTRACT_GUARD = r"""
CREATE OR REPLACE FUNCTION guard_contract() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p uuid; k text;
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.rental_unit_id, NEW.tenant_id, NEW.rental_request_id,
      NEW.start_date, NEW.end_date) IS DISTINCT FROM (OLD.rental_unit_id, OLD.tenant_id,
      OLD.rental_request_id, OLD.start_date, OLD.end_date) THEN
    RAISE EXCEPTION 'Contract parties and dates are immutable; cancel and reapply' USING ERRCODE = '23514';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.terminated_on IS NOT NULL AND NEW.terminated_on IS DISTINCT FROM OLD.terminated_on THEN
      RAISE EXCEPTION 'Effective termination is immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.terminated_on IS DISTINCT FROM OLD.terminated_on AND NOT (OLD.status = 'active' AND NEW.status = 'terminated') THEN
      RAISE EXCEPTION 'Termination date requires active-to-terminated transition' USING ERRCODE = '23514';
    END IF;
    IF NEW.monthly_rent IS DISTINCT FROM OLD.monthly_rent AND NOT (OLD.status = 'confirmed' AND NEW.status = 'confirmed') THEN
      RAISE EXCEPTION 'Only confirmed contract rent can be amended' USING ERRCODE = '23514';
    END IF;
  END IF;
  SELECT property_id, kind INTO p, k FROM rental_units WHERE id = NEW.rental_unit_id;
  UPDATE properties SET booking_revision = booking_revision + 1 WHERE id = p;
  IF NOT EXISTS (SELECT 1 FROM rental_requests WHERE id = NEW.rental_request_id AND status = 'approved') THEN
    RAISE EXCEPTION 'Contract requires an approved application' USING ERRCODE = '23514';
  END IF;
  IF NEW.status <> 'cancelled' AND EXISTS (
    SELECT 1 FROM rental_contracts c JOIN rental_units u ON u.id = c.rental_unit_id
    WHERE u.property_id = p AND c.id <> NEW.id AND c.status <> 'cancelled'
      AND daterange(c.start_date, coalesce(c.terminated_on, c.end_date), '[)') && daterange(NEW.start_date, coalesce(NEW.terminated_on, NEW.end_date), '[)')
      AND (u.id = NEW.rental_unit_id OR u.kind = 'apartment' OR k = 'apartment')
  ) THEN
    RAISE EXCEPTION 'Rental dates conflict with an existing contract' USING ERRCODE = '23P01';
  END IF;
  RETURN NEW;
END $$;
"""

IDENTITY_GUARD = r"""
CREATE FUNCTION guard_operation_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'rental_requests' THEN
      IF (NEW.tenant_id, NEW.rental_unit_id, NEW.start_date, NEW.end_date) IS DISTINCT FROM (OLD.tenant_id, OLD.rental_unit_id, OLD.start_date, OLD.end_date) THEN
        RAISE EXCEPTION 'Application parties and dates are immutable' USING ERRCODE = '23514';
      END IF;
    WHEN 'visits' THEN
      IF (NEW.tenant_id, NEW.rental_unit_id, NEW.requested_at) IS DISTINCT FROM (OLD.tenant_id, OLD.rental_unit_id, OLD.requested_at) THEN
        RAISE EXCEPTION 'Visit applicant, unit and requested time are immutable' USING ERRCODE = '23514';
      END IF;
    WHEN 'conversations' THEN
      IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'Conversation tenant is immutable' USING ERRCODE = '23514';
      END IF;
    WHEN 'messages' THEN
      IF (NEW.sender_id, NEW.conversation_id, NEW.body) IS DISTINCT FROM (OLD.sender_id, OLD.conversation_id, OLD.body) THEN
        RAISE EXCEPTION 'Sent messages are immutable' USING ERRCODE = '23514';
      END IF;
  END CASE;
  RETURN NEW;
END $$;
"""

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.add_column("rental_requests", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("rental_contracts", sa.Column("terminated_on", sa.Date(), nullable=True))
    op.create_check_constraint(op.f("ck_rental_contracts_termination"), "rental_contracts",
        "terminated_on IS NULL OR (status = 'terminated' AND terminated_on > start_date AND terminated_on <= end_date)")
    op.execute(NEW_CONTRACT_GUARD)
    op.add_column("visits", sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("visits", sa.Column("duration_minutes", sa.Integer(), server_default="30", nullable=False))
    op.add_column("visits", sa.Column("assigned_admin_id", sa.Uuid(), nullable=True))
    op.add_column("visits", sa.Column("assigned_admin_role", sa.String(20), server_default="admin", nullable=False))
    op.add_column("visits", sa.Column("agency_note", sa.Text(), nullable=True))
    op.execute("UPDATE visits SET scheduled_end_at = scheduled_at + interval '30 minutes' WHERE scheduled_at IS NOT NULL")
    op.create_foreign_key(op.f("fk_visits_assigned_admin_id_users"), "visits", "users", ["assigned_admin_id", "assigned_admin_role"], ["id", "role"], ondelete="RESTRICT")
    op.create_index("ix_visits_assigned_admin_id", "visits", ["assigned_admin_id"])
    op.create_check_constraint(op.f("ck_visits_assigned_admin_role"), "visits", "assigned_admin_role = 'admin'")
    op.create_check_constraint(op.f("ck_visits_duration"), "visits", "duration_minutes BETWEEN 1 AND 180")
    op.create_check_constraint(op.f("ck_visits_schedule_end"), "visits", "status NOT IN ('scheduled','completed') OR (scheduled_at IS NOT NULL AND scheduled_end_at IS NOT NULL AND scheduled_end_at = scheduled_at + make_interval(mins => duration_minutes))")
    for key, column, where in [("staff", "assigned_admin_id", "status = 'scheduled' AND assigned_admin_id IS NOT NULL"), ("tenant", "tenant_id", "status = 'scheduled'")]:
        op.execute(f"ALTER TABLE visits ADD CONSTRAINT ex_visits_{key}_overlap EXCLUDE USING gist ({column} WITH =, tstzrange(scheduled_at, scheduled_end_at, '[)') WITH &&) WHERE ({where})")
    op.execute(IDENTITY_GUARD)
    for table in ["rental_requests", "visits", "conversations", "messages"]:
        op.execute(f"CREATE TRIGGER identity_{table} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_operation_identity()")


def downgrade():
    # Reverting effective ends must never silently restore overlapping full leases.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM rental_contracts a JOIN rental_units ua ON ua.id=a.rental_unit_id
        JOIN rental_units ub ON ub.property_id=ua.property_id JOIN rental_contracts b ON b.rental_unit_id=ub.id
        WHERE a.id < b.id AND a.status <> 'cancelled' AND b.status <> 'cancelled'
          AND daterange(a.start_date,a.end_date,'[)') && daterange(b.start_date,b.end_date,'[)')
          AND (ua.id=ub.id OR ua.kind='apartment' OR ub.kind='apartment')) THEN
        RAISE EXCEPTION 'Cannot downgrade leases that depend on effective termination' USING ERRCODE='23514';
      END IF;
    END $$""")
    for table in ["rental_requests", "visits", "conversations", "messages"]:
        op.execute(f"DROP TRIGGER identity_{table} ON {table}")
    op.execute("DROP FUNCTION guard_operation_identity()")
    op.drop_constraint("ex_visits_staff_overlap", "visits")
    op.drop_constraint("ex_visits_tenant_overlap", "visits")
    for name in ["schedule_end", "duration", "assigned_admin_role"]:
        op.drop_constraint(op.f(f"ck_visits_{name}"), "visits", type_="check")
    op.drop_index("ix_visits_assigned_admin_id", table_name="visits")
    op.drop_constraint(op.f("fk_visits_assigned_admin_id_users"), "visits", type_="foreignkey")
    for column in ["agency_note", "assigned_admin_role", "assigned_admin_id", "duration_minutes", "scheduled_end_at"]:
        op.drop_column("visits", column)
    op.execute(OLD_CONTRACT_GUARD)
    op.drop_constraint(op.f("ck_rental_contracts_termination"), "rental_contracts", type_="check")
    op.drop_column("rental_contracts", "terminated_on")
    op.drop_column("rental_requests", "review_note")
    # btree_gist may be shared by other schema features; retain the extension.
