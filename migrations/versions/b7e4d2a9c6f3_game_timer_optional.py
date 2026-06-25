"""game timer optional

Revision ID: b7e4d2a9c6f3
Revises: f9b6c3d2a8e1
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e4d2a9c6f3'
down_revision = 'f9b6c3d2a8e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'school_game_setting',
        sa.Column('timer_enabled', sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.alter_column('school_game_setting', 'timer_enabled', server_default=None)


def downgrade():
    op.drop_column('school_game_setting', 'timer_enabled')
