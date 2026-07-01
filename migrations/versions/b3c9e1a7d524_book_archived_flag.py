"""book archived flag

Revision ID: b3c9e1a7d524
Revises: a8e7c4d2f9b1
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c9e1a7d524'
down_revision = 'a8e7c4d2f9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('book', sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.create_index('ix_book_archived', 'book', ['archived'], unique=False)
    op.alter_column('book', 'archived', server_default=None)


def downgrade():
    op.drop_index('ix_book_archived', table_name='book')
    op.drop_column('book', 'archived')
