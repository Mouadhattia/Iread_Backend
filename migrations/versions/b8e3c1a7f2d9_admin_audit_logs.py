"""admin audit logs

Revision ID: b8e3c1a7f2d9
Revises: a1c4f8e2b7d3
Create Date: 2026-07-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8e3c1a7f2d9'
down_revision = 'a1c4f8e2b7d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_username', sa.String(length=150), nullable=True),
        sa.Column('actor_role', sa.String(length=30), nullable=True),
        sa.Column('action', sa.String(length=60), nullable=False),
        sa.Column('target_type', sa.String(length=60), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('admin_audit_logs')
