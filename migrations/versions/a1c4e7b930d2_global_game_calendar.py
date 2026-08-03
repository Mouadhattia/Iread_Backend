"""global game calendar

Revision ID: a1c4e7b930d2
Revises: e2c8b4d1f036
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e7b930d2'
down_revision = 'e2c8b4d1f036'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'global_game_setting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=32), nullable=False),
        sa.Column('timer_seconds', sa.Integer(), nullable=False),
        sa.Column('timer_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('max_hints', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('timer_seconds > 0', name='ck_global_game_setting_timer_positive'),
        sa.CheckConstraint(
            'max_hints IS NULL OR max_hints >= 0',
            name='ck_global_game_setting_max_hints_non_negative'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_type', name='uq_global_game_setting_game_type')
    )

    op.create_table(
        'global_game_calendar_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=32), nullable=False),
        sa.Column('play_date', sa.Date(), nullable=False),
        sa.Column('words', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'book_id',
            'game_type',
            'play_date',
            name='uq_global_book_game_calendar_date'
        )
    )
    op.create_index(
        'ix_global_game_calendar_entry_book_id',
        'global_game_calendar_entry',
        ['book_id'],
        unique=False
    )
    op.create_index(
        'ix_global_game_calendar_entry_game_type',
        'global_game_calendar_entry',
        ['game_type'],
        unique=False
    )
    op.create_index(
        'ix_global_game_calendar_entry_play_date',
        'global_game_calendar_entry',
        ['play_date'],
        unique=False
    )

    # Existing instances keep the conservative default: replay from the start
    # of the schedule, ranked inside their own school. Opting a school into a
    # cross-school competition is a deliberate admin choice, never a migration
    # side effect.
    op.add_column(
        'school_pack_instance',
        sa.Column('games_mode', sa.String(length=16), nullable=False, server_default='from_start')
    )
    op.add_column(
        'school_pack_instance',
        sa.Column('games_anchor_date', sa.Date(), nullable=True)
    )
    op.add_column(
        'school_pack_instance',
        sa.Column('global_leaderboard_opt_in', sa.Boolean(), nullable=False, server_default=sa.true())
    )

    # Instances already published keep a stable day 1 rather than silently
    # restarting from today the first time a reader opens a game.
    op.execute(
        'UPDATE school_pack_instance '
        'SET games_anchor_date = DATE(created_at) '
        'WHERE public = 1 AND games_anchor_date IS NULL'
    )


def downgrade():
    op.drop_column('school_pack_instance', 'global_leaderboard_opt_in')
    op.drop_column('school_pack_instance', 'games_anchor_date')
    op.drop_column('school_pack_instance', 'games_mode')

    op.drop_index('ix_global_game_calendar_entry_play_date', table_name='global_game_calendar_entry')
    op.drop_index('ix_global_game_calendar_entry_game_type', table_name='global_game_calendar_entry')
    op.drop_index('ix_global_game_calendar_entry_book_id', table_name='global_game_calendar_entry')
    op.drop_table('global_game_calendar_entry')

    op.drop_table('global_game_setting')
