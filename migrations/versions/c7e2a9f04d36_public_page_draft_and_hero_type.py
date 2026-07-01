"""public page draft and hero type

Revision ID: c7e2a9f04d36
Revises: b3c9e1a7d524
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e2a9f04d36'
down_revision = 'b3c9e1a7d524'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('school_public_page', sa.Column('hero_type', sa.String(length=30), nullable=False, server_default='cover'))
    op.add_column('school_public_page', sa.Column('draft_data', sa.JSON(), nullable=True))
    op.add_column('school_public_page', sa.Column('published_at', sa.DateTime(), nullable=True))
    op.alter_column('school_public_page', 'hero_type', server_default=None)

    op.execute('UPDATE school_public_page SET published_at = updated_at')


def downgrade():
    op.drop_column('school_public_page', 'published_at')
    op.drop_column('school_public_page', 'draft_data')
    op.drop_column('school_public_page', 'hero_type')
