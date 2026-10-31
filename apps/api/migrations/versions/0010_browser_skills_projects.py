"""browser skills, skill runs, project store

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
import app.db

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def _ts():
    return [sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False), sa.Column('updated_at', app.db.UTCDateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table('browser_skills',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False), sa.Column('steps', sa.JSON(), nullable=False), sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('recorded_session_id', sa.String(length=40), nullable=True), sa.Column('runs', sa.Integer(), nullable=False),
        sa.Column('last_status', sa.String(length=24), nullable=True), *_ts(), sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_browser_skills_tenant_id'), 'browser_skills', ['tenant_id'], unique=False)
    op.create_table('browser_skill_runs',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('skill_id', sa.String(length=40), nullable=True), sa.Column('session_id', sa.String(length=40), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False), sa.Column('step_index', sa.Integer(), nullable=False), sa.Column('total_steps', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(length=300), nullable=True), sa.Column('uncertain', sa.Boolean(), nullable=False), *_ts(), sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_browser_skill_runs_tenant_id'), 'browser_skill_runs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_browser_skill_runs_skill_id'), 'browser_skill_runs', ['skill_id'], unique=False)
    op.create_table('projects',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False), sa.Column('description', sa.Text(), nullable=False), *_ts(), sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_projects_tenant_id'), 'projects', ['tenant_id'], unique=False)
    op.create_table('project_items',
        sa.Column('id', sa.String(length=40), nullable=False), sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('project_id', sa.String(length=40), nullable=False), sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('ref_id', sa.String(length=40), nullable=False), sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('project_id', 'kind', 'ref_id'))
    op.create_index(op.f('ix_project_items_tenant_id'), 'project_items', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_project_items_project_id'), 'project_items', ['project_id'], unique=False)


def downgrade() -> None:
    for t in ('project_items', 'projects', 'browser_skill_runs', 'browser_skills'):
        op.drop_table(t)
