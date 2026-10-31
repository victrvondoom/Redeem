"""conversation turns (context memory)

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
import app.db

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conversation_turns',
        sa.Column('id', sa.String(length=40), nullable=False),
        sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=40), nullable=False),
        sa.Column('channel', sa.String(length=12), nullable=False),
        sa.Column('ref_id', sa.String(length=40), nullable=True),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('text_enc', sa.Text(), nullable=False),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'channel', 'ref_id', 'idx'))
    op.create_index(op.f('ix_conversation_turns_tenant_id'), 'conversation_turns', ['tenant_id'], unique=False)
    op.create_index('ix_turn_user_time', 'conversation_turns', ['tenant_id', 'user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('conversation_turns')
