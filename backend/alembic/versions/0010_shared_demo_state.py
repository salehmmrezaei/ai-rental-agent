"""Bounded operational state for serverless public demos.

Seed identity constants are frozen here, independent of future application code.
"""
from uuid import UUID, uuid5
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

revision = '0010_shared_demo_state'
down_revision = '0009_assistant_visit_search'
branch_labels = depends_on = None
NS = UUID('d6e39157-c440-4c6e-9959-c7201979895f')


def seed_ids(kind, count):
    return [str(uuid5(NS, f'v1:{kind}:{i}')) for i in range(count)]


def upgrade():
    op.create_table('demo_visitors',
        sa.Column('id', PGUUID(), primary_key=True), sa.Column('user_id', PGUUID(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', JSONB(), nullable=False, server_default='{}'),
        sa.CheckConstraint("role IN ('tenant','landlord','admin')", name='ck_demo_visitors_demo_role'))
    op.create_index('ix_demo_visitors_expires_at', 'demo_visitors', ['expires_at'])
    op.create_table('demo_rate_buckets',
        sa.Column('key', sa.String(64), primary_key=True), sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_demo_rate_buckets_expires_at', 'demo_rate_buckets', ['expires_at'])
    groups = {'users': seed_ids('admin', 1) + seed_ids('landlord', 100) + seed_ids('tenant', 200)}
    for table, kind, count in [('properties','property',300), ('rental_units','unit',900),
        ('listings','listing',900), ('rental_requests','request',750), ('rental_contracts','contract',550),
        ('visits','visit',100), ('conversations','conversation',50), ('messages','message',150),
        ('saved_listings','saved',200), ('property_images','photo',1200)]:
        groups[table] = seed_ids(kind, count)
    clauses = []
    for table, ids in groups.items():
        literals = ','.join("'" + value + "'::uuid" for value in ids)
        clauses.extend([f'(SELECT count(*) FROM {table}) = {len(ids)}',
            f'NOT EXISTS (SELECT 1 FROM {table} WHERE id <> ALL(ARRAY[{literals}]))'])
    clauses += ["NOT EXISTS (SELECT 1 FROM properties WHERE NOT is_synthetic)",
        "NOT EXISTS (SELECT 1 FROM users WHERE email NOT LIKE '%@example.com')",
        """NOT EXISTS (SELECT 1 FROM property_images WHERE storage_key NOT IN (
            'demo-v1-' || replace(id::text,'-','') || '-bologna-living.webp',
            'demo-v1-' || replace(id::text,'-','') || '-milan-living.webp',
            'demo-v1-' || replace(id::text,'-','') || '-rome-bedroom.webp',
            'demo-v1-' || replace(id::text,'-','') || '-florence-bedroom.webp',
            'demo-v1-' || replace(id::text,'-','') || '-study-bedroom.webp',
            'demo-v1-' || replace(id::text,'-','') || '-shared-kitchen.webp'))"""]
    # One database round trip, no transfer of 1,200 image ORM rows per request.
    op.execute('CREATE FUNCTION casa_demo_dataset_valid() RETURNS boolean LANGUAGE sql STABLE AS $$ SELECT '
               + ' AND '.join(clauses) + ' $$')


def downgrade():
    op.execute('DROP FUNCTION casa_demo_dataset_valid()')
    op.drop_table('demo_rate_buckets')
    op.drop_table('demo_visitors')
