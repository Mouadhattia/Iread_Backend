"""must change password

Revision ID: e1a5f7c3d9b4
Revises: d3f7a1c9b5e2
Create Date: 2026-07-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1a5f7c3d9b4'
down_revision = 'd3f7a1c9b5e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.alter_column('user', 'must_change_password', server_default=None)


def downgrade():
    op.drop_column('user', 'must_change_password')
