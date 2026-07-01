"""reader profile pin

Revision ID: d3f7a1c9b5e2
Revises: c7e2a9f04d36
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f7a1c9b5e2'
down_revision = 'c7e2a9f04d36'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.add_column('user', sa.Column('pin_hash', sa.String(length=100), nullable=True))
    op.add_column('user', sa.Column('pin_failed_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('user', sa.Column('pin_locked_until', sa.DateTime(), nullable=True))
    op.alter_column('user', 'is_primary', server_default=None)
    op.alter_column('user', 'pin_failed_attempts', server_default=None)

    # Existing rows that already share an email (siblings created before this
    # feature existed) only had the earliest-created one act as the "main"
    # login; mark that one primary and the rest as child profiles.
    op.execute("""
        UPDATE user u
        JOIN (
            SELECT email, MIN(id) AS min_id FROM user GROUP BY email
        ) primary_accounts ON u.email = primary_accounts.email
        SET u.is_primary = (u.id = primary_accounts.min_id)
    """)


def downgrade():
    op.drop_column('user', 'pin_locked_until')
    op.drop_column('user', 'pin_failed_attempts')
    op.drop_column('user', 'pin_hash')
    op.drop_column('user', 'is_primary')
