"""super admin role

Revision ID: c7b2a8f4d1e9
Revises: 8c2f7d9e4a11
Create Date: 2026-06-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7b2a8f4d1e9'
down_revision = '8c2f7d9e4a11'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'super_admin',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('super_admin')
