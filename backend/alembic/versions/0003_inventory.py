"""Allow withdrawal of unpublished listing reviews for safe editing."""
from alembic import op

revision = "0003_inventory"
down_revision = "0002_auth"
branch_labels = None
depends_on = None

OLD_TRANSITIONS = r"""
CREATE OR REPLACE FUNCTION guard_transition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed boolean := false;
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  CASE TG_TABLE_NAME
    WHEN 'listings' THEN allowed :=
      (OLD.status IN ('draft','rejected') AND NEW.status = 'submitted') OR
      (OLD.status = 'submitted' AND NEW.status IN ('approved','rejected')) OR
      (OLD.status IN ('approved','unpublished') AND NEW.status = 'published') OR
      (OLD.status = 'published' AND NEW.status = 'unpublished');
    WHEN 'rental_requests' THEN allowed :=
      (OLD.status = 'submitted' AND NEW.status IN ('reviewing','rejected','withdrawn')) OR
      (OLD.status = 'reviewing' AND NEW.status IN ('approved','rejected','withdrawn'));
    WHEN 'visits' THEN allowed :=
      (OLD.status = 'requested' AND NEW.status IN ('scheduled','rejected','cancelled')) OR
      (OLD.status = 'scheduled' AND NEW.status IN ('completed','cancelled'));
    WHEN 'rental_contracts' THEN allowed :=
      (OLD.status = 'confirmed' AND NEW.status IN ('active','cancelled')) OR
      (OLD.status = 'active' AND NEW.status IN ('completed','terminated'));
  END CASE;
  IF NOT allowed THEN
    RAISE EXCEPTION 'Invalid % status transition: % -> %', TG_TABLE_NAME, OLD.status, NEW.status USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
"""

NEW_TRANSITIONS = r"""
CREATE OR REPLACE FUNCTION guard_transition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed boolean := false;
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  CASE TG_TABLE_NAME
    WHEN 'listings' THEN allowed :=
      (OLD.status IN ('draft','rejected') AND NEW.status = 'submitted') OR
      (OLD.status = 'submitted' AND NEW.status IN ('approved','rejected')) OR
      (OLD.status IN ('approved','unpublished') AND NEW.status = 'published') OR
      (OLD.status = 'published' AND NEW.status = 'unpublished') OR
      (OLD.status IN ('submitted','approved','unpublished','rejected') AND NEW.status = 'draft');
    WHEN 'rental_requests' THEN allowed :=
      (OLD.status = 'submitted' AND NEW.status IN ('reviewing','rejected','withdrawn')) OR
      (OLD.status = 'reviewing' AND NEW.status IN ('approved','rejected','withdrawn'));
    WHEN 'visits' THEN allowed :=
      (OLD.status = 'requested' AND NEW.status IN ('scheduled','rejected','cancelled')) OR
      (OLD.status = 'scheduled' AND NEW.status IN ('completed','cancelled'));
    WHEN 'rental_contracts' THEN allowed :=
      (OLD.status = 'confirmed' AND NEW.status IN ('active','cancelled')) OR
      (OLD.status = 'active' AND NEW.status IN ('completed','terminated'));
  END CASE;
  IF NOT allowed THEN
    RAISE EXCEPTION 'Invalid % status transition: % -> %', TG_TABLE_NAME, OLD.status, NEW.status USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
"""

def upgrade():
    op.execute(NEW_TRANSITIONS)

def downgrade():
    op.execute(OLD_TRANSITIONS)
