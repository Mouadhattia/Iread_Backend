"""account setup complete flag

Revision ID: b2d5f8e3a1c6
Revises: a1c4e7d2f9b3
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2d5f8e3a1c6'
down_revision = 'a1c4e7d2f9b3'
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows have nothing to be asked -- backfill them True, then drop
    # the server default so new inserts fall back to the model's default of
    # False (same two-step pattern as is_primary in d3f7a1c9b5e2).
    op.add_column('user', sa.Column('account_setup_complete', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.alter_column('user', 'account_setup_complete', server_default=None)


def downgrade():
    op.drop_column('user', 'account_setup_complete')
