"""user display name

Revision ID: c3d6a9f2b5e8
Revises: b2d5f8e3a1c6
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d6a9f2b5e8'
down_revision = 'b2d5f8e3a1c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('display_name', sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column('user', 'display_name')
