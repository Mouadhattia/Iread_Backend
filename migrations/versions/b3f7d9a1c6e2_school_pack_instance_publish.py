"""school pack instance publish + display name

Revision ID: b3f7d9a1c6e2
Revises: e5f8c1a2d740
Create Date: 2026-07-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f7d9a1c6e2'
down_revision = 'e5f8c1a2d740'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('school_pack_instance', sa.Column('public', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('school_pack_instance', sa.Column('display_name', sa.String(length=255), nullable=True))
    op.alter_column('school_pack_instance', 'public', server_default=None)


def downgrade():
    op.drop_column('school_pack_instance', 'display_name')
    op.drop_column('school_pack_instance', 'public')
