"""school public page show public packs toggle

Revision ID: a1c4f8e2b7d3
Revises: b3f7d9a1c6e2
Create Date: 2026-07-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4f8e2b7d3'
down_revision = 'b3f7d9a1c6e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('school_public_page', sa.Column('show_public_packs', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.alter_column('school_public_page', 'show_public_packs', server_default=None)


def downgrade():
    op.drop_column('school_public_page', 'show_public_packs')
