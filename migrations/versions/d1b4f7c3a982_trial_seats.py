"""free trial reader places for schools without a contract

Closes the gap where a school with no contract had no seat cap at all and
could onboard unlimited readers for nothing, without making "no contract" a
hard lockout -- schools legitimately pilot iRead before signing.

platform_settings.default_trial_seats is the platform-wide allowance (10).
shcool.trial_seats overrides it per school; NULL means "use the default".
A school carrying a large pre-billing reader base should be given an explicit
override before seat enforcement is switched on, or its teachers will hit the
cap the same day.

Revision ID: d1b4f7c3a982
Revises: c9a2e5f81b34
Create Date: 2026-07-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1b4f7c3a982'
down_revision = 'c9a2e5f81b34'
branch_labels = None
depends_on = None

DEFAULT_TRIAL_SEATS = 10


def upgrade():
    op.add_column(
        'platform_settings',
        sa.Column('default_trial_seats', sa.Integer(), nullable=False,
                  server_default=str(DEFAULT_TRIAL_SEATS))
    )
    # Per-school override. Nullable on purpose: NULL is meaningfully different
    # from 0 here -- "follow the platform default" vs "this school gets none".
    op.add_column('shcool', sa.Column('trial_seats', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('shcool', 'trial_seats')
    op.drop_column('platform_settings', 'default_trial_seats')
