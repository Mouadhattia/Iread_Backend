"""practice play

Revision ID: d4e7b0a3c9f1
Revises: c3d6a9f2b5e8
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e7b0a3c9f1'
down_revision = 'c3d6a9f2b5e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'practice_play',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column(
            'game',
            sa.Enum('BEE', 'WORDEXPLORER', 'THINKWORD', 'INTELLECTLNK', name='gameenum'),
            nullable=False,
        ),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('day', sa.Date(), nullable=True),
        sa.Column('words_learned', sa.JSON(), nullable=True),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_practice_play_user_id'), 'practice_play', ['user_id'], unique=False)
    op.create_index(op.f('ix_practice_play_day'), 'practice_play', ['day'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_practice_play_day'), table_name='practice_play')
    op.drop_index(op.f('ix_practice_play_user_id'), table_name='practice_play')
    op.drop_table('practice_play')
