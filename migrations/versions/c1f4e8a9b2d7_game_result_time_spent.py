"""game result time spent

Revision ID: c1f4e8a9b2d7
Revises: b7e4d2a9c6f3
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1f4e8a9b2d7'
down_revision = 'b7e4d2a9c6f3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'game_result',
        sa.Column('time_spent_seconds', sa.Integer(), nullable=False, server_default='0')
    )
    op.alter_column('game_result', 'time_spent_seconds', server_default=None)


def downgrade():
    op.drop_column('game_result', 'time_spent_seconds')
