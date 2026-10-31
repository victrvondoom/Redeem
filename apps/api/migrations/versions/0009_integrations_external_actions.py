"""integrations, oauth states, external actions

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
import app.db

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('integrations',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=40), nullable=False), sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False), sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('account_label', sa.String(length=200), nullable=True), sa.Column('token_enc', sa.Text(), nullable=False),
        sa.Column('last_verified_at', app.db.UTCDateTime(timezone=True), nullable=True), sa.Column('last_error', sa.String(length=300), nullable=True),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False), sa.Column('updated_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('tenant_id', 'provider'))
    op.create_index(op.f('ix_integrations_tenant_id'), 'integrations', ['tenant_id'], unique=False)
    op.create_table('oauth_states',
        sa.Column('state_hash', sa.String(length=64), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=40), nullable=False), sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False), sa.Column('expires_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('state_hash'))
    op.create_index(op.f('ix_oauth_states_tenant_id'), 'oauth_states', ['tenant_id'], unique=False)
    op.create_table('external_actions',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=40), nullable=False), sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False), sa.Column('params_enc', sa.Text(), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False), sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('provider_ref', sa.String(length=200), nullable=True), sa.Column('verification', sa.JSON(), nullable=True),
        sa.Column('error', sa.String(length=300), nullable=True), sa.Column('mission_id', sa.String(length=40), nullable=True),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False), sa.Column('updated_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_external_actions_tenant_id'), 'external_actions', ['tenant_id'], unique=False)
    op.create_index('ix_extact_tenant_status', 'external_actions', ['tenant_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_table('external_actions')
    op.drop_table('oauth_states')
    op.drop_table('integrations')
