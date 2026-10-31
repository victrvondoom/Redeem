"""memory items and envelope encryption keys

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
import app.db

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('encryption_keys',
        sa.Column('id', sa.String(length=40), nullable=False),
        sa.Column('scope', sa.String(length=40), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('kek_id', sa.String(length=20), nullable=False),
        sa.Column('wrapped', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope', 'version'))
    op.create_index(op.f('ix_encryption_keys_scope'), 'encryption_keys', ['scope'], unique=False)
    op.create_table('memory_items',
        sa.Column('id', sa.String(length=40), nullable=False),
        sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=40), nullable=False),
        sa.Column('project_id', sa.String(length=40), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('field', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('value_enc', sa.Text(), nullable=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('source_ref', sa.String(length=60), nullable=True),
        sa.Column('segment', sa.String(length=40), nullable=True),
        sa.Column('quote_enc', sa.Text(), nullable=True),
        sa.Column('explicit', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Double(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('pinned', sa.Boolean(), nullable=False),
        sa.Column('expires_at', app.db.UTCDateTime(timezone=True), nullable=True),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.Column('updated_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_memory_items_tenant_id'), 'memory_items', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_memory_items_user_id'), 'memory_items', ['user_id'], unique=False)
    op.create_index('ix_memory_tenant_field', 'memory_items', ['tenant_id', 'field'], unique=False)


def downgrade() -> None:
    op.drop_table('memory_items')
    op.drop_table('encryption_keys')
