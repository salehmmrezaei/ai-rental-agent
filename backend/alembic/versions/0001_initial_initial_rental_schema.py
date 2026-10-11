"""initial rental schema"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None
GUARDRAILS = r"""
-- VOLATILE trigger queries acquire fresh snapshots under READ COMMITTED.
-- Updating the parent also forces stale REPEATABLE READ transactions to abort.
CREATE FUNCTION guard_contract() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE TRIGGER contract_guard BEFORE INSERT OR UPDATE ON rental_contracts
FOR EACH ROW EXECUTE FUNCTION guard_contract();

CREATE FUNCTION preserve_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'properties' THEN
    IF NEW.landlord_id IS DISTINCT FROM OLD.landlord_id THEN
      RAISE EXCEPTION 'Property ownership cannot be reassigned' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'rental_units' THEN
    IF (NEW.property_id, NEW.kind) IS DISTINCT FROM (OLD.property_id, OLD.kind) THEN
      RAISE EXCEPTION 'Unit property and kind are immutable' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER property_identity BEFORE UPDATE ON properties FOR EACH ROW EXECUTE FUNCTION preserve_identity();
CREATE TRIGGER unit_identity BEFORE UPDATE ON rental_units FOR EACH ROW EXECUTE FUNCTION preserve_identity();

CREATE FUNCTION guard_message() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM users u JOIN conversations c ON c.id = NEW.conversation_id
    WHERE u.id = NEW.sender_id AND (u.role = 'admin' OR (u.role = 'tenant' AND u.id = c.tenant_id))
  ) THEN
    RAISE EXCEPTION 'Messages are restricted to the agency and conversation tenant' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER message_guard BEFORE INSERT OR UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION guard_message();

CREATE FUNCTION guard_transition() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE TRIGGER listing_transition BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION guard_transition();
CREATE TRIGGER request_transition BEFORE UPDATE ON rental_requests FOR EACH ROW EXECUTE FUNCTION guard_transition();
CREATE TRIGGER visit_transition BEFORE UPDATE ON visits FOR EACH ROW EXECUTE FUNCTION guard_transition();
CREATE TRIGGER contract_transition BEFORE UPDATE ON rental_contracts FOR EACH ROW EXECUTE FUNCTION guard_transition();

CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := CURRENT_TIMESTAMP; RETURN NEW; END $$;
"""


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('amenities',
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_amenities')),
    sa.UniqueConstraint('name', name=op.f('uq_amenities_name'))
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('tenant','landlord','admin')", name=op.f('ck_users_role')),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_normalized')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('id', 'role', name=op.f('uq_users_id'))
    )
    op.create_table('conversations',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_role', sa.String(length=20), server_default='tenant', nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("tenant_role = 'tenant'", name=op.f('ck_conversations_tenant_role')),
    sa.ForeignKeyConstraint(['tenant_id', 'tenant_role'], ['users.id', 'users.role'], name=op.f('fk_conversations_tenant_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_tenant_id'), 'conversations', ['tenant_id'], unique=False)
    op.create_table('properties',
    sa.Column('landlord_id', sa.Uuid(), nullable=False),
    sa.Column('owner_role', sa.String(length=20), server_default='landlord', nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=False),
    sa.Column('postal_code', sa.String(length=10), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('booking_revision', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("owner_role = 'landlord'", name=op.f('ck_properties_owner_role')),
    sa.ForeignKeyConstraint(['landlord_id', 'owner_role'], ['users.id', 'users.role'], name=op.f('fk_properties_landlord_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_properties'))
    )
    op.create_index(op.f('ix_properties_city'), 'properties', ['city'], unique=False)
    op.create_index(op.f('ix_properties_landlord_id'), 'properties', ['landlord_id'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(body)) BETWEEN 1 AND 10000', name=op.f('ck_messages_body')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_messages_sender_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_sender_id'), 'messages', ['sender_id'], unique=False)
    op.create_table('property_amenities',
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('amenity_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['amenity_id'], ['amenities.id'], name=op.f('fk_property_amenities_amenity_id_amenities'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_property_amenities_property_id_properties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('property_id', 'amenity_id', name=op.f('pk_property_amenities'))
    )
    op.create_table('rental_units',
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('monthly_rent', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('deposit', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('bedrooms', sa.Integer(), server_default='1', nullable=False),
    sa.Column('area_sqm', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('apartment','room')", name=op.f('ck_rental_units_kind')),
    sa.CheckConstraint('bedrooms > 0 AND (area_sqm IS NULL OR area_sqm > 0)', name=op.f('ck_rental_units_size')),
    sa.CheckConstraint('monthly_rent > 0 AND deposit >= 0', name=op.f('ck_rental_units_prices')),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_rental_units_property_id_properties'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rental_units')),
    sa.UniqueConstraint('id', 'property_id', name=op.f('uq_rental_units_id')),
    sa.UniqueConstraint('property_id', 'name', name=op.f('uq_rental_units_property_id'))
    )
    op.create_index(op.f('ix_rental_units_property_id'), 'rental_units', ['property_id'], unique=False)
    op.create_index('uq_one_apartment_per_property', 'rental_units', ['property_id'], unique=True, postgresql_where=sa.text("kind = 'apartment'"))
    op.create_table('listings',
    sa.Column('rental_unit_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('available_from', sa.Date(), nullable=False),
    sa.Column('available_until', sa.Date(), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft','submitted','approved','rejected','published','unpublished')", name=op.f('ck_listings_status')),
    sa.CheckConstraint('available_until IS NULL OR available_until > available_from', name=op.f('ck_listings_dates')),
    sa.ForeignKeyConstraint(['rental_unit_id'], ['rental_units.id'], name=op.f('fk_listings_rental_unit_id_rental_units'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_listings')),
    sa.UniqueConstraint('rental_unit_id', name=op.f('uq_listings_rental_unit_id'))
    )
    op.create_index(op.f('ix_listings_status'), 'listings', ['status'], unique=False)
    op.create_table('property_images',
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('rental_unit_id', sa.Uuid(), nullable=True),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('alt_text', sa.String(length=255), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('position >= 0', name=op.f('ck_property_images_position')),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_property_images_property_id_properties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rental_unit_id', 'property_id'], ['rental_units.id', 'rental_units.property_id'], name=op.f('fk_property_images_rental_unit_id_rental_units'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_property_images')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_property_images_storage_key'))
    )
    op.create_index(op.f('ix_property_images_property_id'), 'property_images', ['property_id'], unique=False)
    op.create_table('rental_requests',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_role', sa.String(length=20), server_default='tenant', nullable=False),
    sa.Column('rental_unit_id', sa.Uuid(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='submitted', nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('submitted','reviewing','approved','rejected','withdrawn')", name=op.f('ck_rental_requests_status')),
    sa.CheckConstraint("tenant_role = 'tenant'", name=op.f('ck_rental_requests_tenant_role')),
    sa.CheckConstraint('end_date > start_date', name=op.f('ck_rental_requests_dates')),
    sa.ForeignKeyConstraint(['rental_unit_id'], ['rental_units.id'], name=op.f('fk_rental_requests_rental_unit_id_rental_units'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tenant_id', 'tenant_role'], ['users.id', 'users.role'], name=op.f('fk_rental_requests_tenant_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rental_requests')),
    sa.UniqueConstraint('id', 'tenant_id', 'rental_unit_id', 'start_date', 'end_date', name=op.f('uq_rental_requests_id'))
    )
    op.create_index(op.f('ix_rental_requests_rental_unit_id'), 'rental_requests', ['rental_unit_id'], unique=False)
    op.create_index(op.f('ix_rental_requests_status'), 'rental_requests', ['status'], unique=False)
    op.create_index(op.f('ix_rental_requests_tenant_id'), 'rental_requests', ['tenant_id'], unique=False)
    op.create_table('visits',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_role', sa.String(length=20), server_default='tenant', nullable=False),
    sa.Column('rental_unit_id', sa.Uuid(), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='requested', nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('requested','scheduled','completed','cancelled','rejected')", name=op.f('ck_visits_status')),
    sa.CheckConstraint("status NOT IN ('scheduled','completed') OR scheduled_at IS NOT NULL", name=op.f('ck_visits_schedule')),
    sa.CheckConstraint("tenant_role = 'tenant'", name=op.f('ck_visits_tenant_role')),
    sa.ForeignKeyConstraint(['rental_unit_id'], ['rental_units.id'], name=op.f('fk_visits_rental_unit_id_rental_units'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tenant_id', 'tenant_role'], ['users.id', 'users.role'], name=op.f('fk_visits_tenant_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visits'))
    )
    op.create_index(op.f('ix_visits_rental_unit_id'), 'visits', ['rental_unit_id'], unique=False)
    op.create_index(op.f('ix_visits_status'), 'visits', ['status'], unique=False)
    op.create_index(op.f('ix_visits_tenant_id'), 'visits', ['tenant_id'], unique=False)
    op.create_table('rental_contracts',
    sa.Column('rental_request_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('rental_unit_id', sa.Uuid(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('monthly_rent', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='confirmed', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('confirmed','active','completed','terminated','cancelled')", name=op.f('ck_rental_contracts_status')),
    sa.CheckConstraint('end_date > start_date', name=op.f('ck_rental_contracts_dates')),
    sa.CheckConstraint('monthly_rent > 0', name=op.f('ck_rental_contracts_rent')),
    sa.ForeignKeyConstraint(['rental_request_id', 'tenant_id', 'rental_unit_id', 'start_date', 'end_date'], ['rental_requests.id', 'rental_requests.tenant_id', 'rental_requests.rental_unit_id', 'rental_requests.start_date', 'rental_requests.end_date'], name=op.f('fk_rental_contracts_rental_request_id_rental_requests'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rental_unit_id'], ['rental_units.id'], name=op.f('fk_rental_contracts_rental_unit_id_rental_units'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rental_contracts')),
    sa.UniqueConstraint('rental_request_id', name=op.f('uq_rental_contracts_rental_request_id'))
    )
    op.create_index('ix_contract_unit_dates', 'rental_contracts', ['rental_unit_id', 'start_date', 'end_date'], unique=False)
    op.create_index(op.f('ix_rental_contracts_rental_unit_id'), 'rental_contracts', ['rental_unit_id'], unique=False)
    op.create_index(op.f('ix_rental_contracts_status'), 'rental_contracts', ['status'], unique=False)
    op.create_index(op.f('ix_rental_contracts_tenant_id'), 'rental_contracts', ['tenant_id'], unique=False)
    op.create_table('saved_listings',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_role', sa.String(length=20), server_default='tenant', nullable=False),
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("tenant_role = 'tenant'", name=op.f('ck_saved_listings_tenant_role')),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_saved_listings_listing_id_listings'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'tenant_role'], ['users.id', 'users.role'], name=op.f('fk_saved_listings_tenant_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_listings')),
    sa.UniqueConstraint('tenant_id', 'listing_id', name=op.f('uq_saved_listings_tenant_id'))
    )
    op.create_index(op.f('ix_saved_listings_listing_id'), 'saved_listings', ['listing_id'], unique=False)
    op.create_index(op.f('ix_saved_listings_tenant_id'), 'saved_listings', ['tenant_id'], unique=False)
    op.execute(GUARDRAILS)
    op.execute("CREATE TRIGGER touch_users BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_properties BEFORE UPDATE ON properties FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_rental_units BEFORE UPDATE ON rental_units FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_listings BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_rental_requests BEFORE UPDATE ON rental_requests FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_rental_contracts BEFORE UPDATE ON rental_contracts FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_conversations BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_messages BEFORE UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_visits BEFORE UPDATE ON visits FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_property_images BEFORE UPDATE ON property_images FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_amenities BEFORE UPDATE ON amenities FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    op.execute("CREATE TRIGGER touch_saved_listings BEFORE UPDATE ON saved_listings FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
    # ### end Alembic commands ###
def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_saved_listings_tenant_id'), table_name='saved_listings')
    op.drop_index(op.f('ix_saved_listings_listing_id'), table_name='saved_listings')
    op.drop_table('saved_listings')
    op.drop_index(op.f('ix_rental_contracts_tenant_id'), table_name='rental_contracts')
    op.drop_index(op.f('ix_rental_contracts_status'), table_name='rental_contracts')
    op.drop_index(op.f('ix_rental_contracts_rental_unit_id'), table_name='rental_contracts')
    op.drop_index('ix_contract_unit_dates', table_name='rental_contracts')
    op.drop_table('rental_contracts')
    op.drop_index(op.f('ix_visits_tenant_id'), table_name='visits')
    op.drop_index(op.f('ix_visits_status'), table_name='visits')
    op.drop_index(op.f('ix_visits_rental_unit_id'), table_name='visits')
    op.drop_table('visits')
    op.drop_index(op.f('ix_rental_requests_tenant_id'), table_name='rental_requests')
    op.drop_index(op.f('ix_rental_requests_status'), table_name='rental_requests')
    op.drop_index(op.f('ix_rental_requests_rental_unit_id'), table_name='rental_requests')
    op.drop_table('rental_requests')
    op.drop_index(op.f('ix_property_images_property_id'), table_name='property_images')
    op.drop_table('property_images')
    op.drop_index(op.f('ix_listings_status'), table_name='listings')
    op.drop_table('listings')
    op.drop_index('uq_one_apartment_per_property', table_name='rental_units', postgresql_where=sa.text("kind = 'apartment'"))
    op.drop_index(op.f('ix_rental_units_property_id'), table_name='rental_units')
    op.drop_table('rental_units')
    op.drop_table('property_amenities')
    op.drop_index(op.f('ix_messages_sender_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_properties_landlord_id'), table_name='properties')
    op.drop_index(op.f('ix_properties_city'), table_name='properties')
    op.drop_table('properties')
    op.drop_index(op.f('ix_conversations_tenant_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('users')
    op.drop_table('amenities')
    # ### end Alembic commands ###
    op.execute("DROP FUNCTION touch_updated_at(), guard_transition(), guard_message(), preserve_identity(), guard_contract()")
