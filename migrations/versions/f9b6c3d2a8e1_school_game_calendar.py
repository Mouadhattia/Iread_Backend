"""school game calendar

Revision ID: f9b6c3d2a8e1
Revises: e4a1d2c9b7f6
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9b6c3d2a8e1'
down_revision = 'e4a1d2c9b7f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'school_game_setting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=32), nullable=False),
        sa.Column('timer_seconds', sa.Integer(), nullable=False),
        sa.Column('max_hints', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('timer_seconds > 0', name='ck_school_game_setting_timer_positive'),
        sa.CheckConstraint(
            'max_hints IS NULL OR max_hints >= 0',
            name='ck_school_game_setting_max_hints_non_negative'
        ),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shcool_id', 'game_type', name='uq_school_game_setting')
    )
    op.create_index('ix_school_game_setting_shcool_id', 'school_game_setting', ['shcool_id'], unique=False)

    op.create_table(
        'game_calendar_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=32), nullable=False),
        sa.Column('play_date', sa.Date(), nullable=False),
        sa.Column('words', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'shcool_id',
            'book_id',
            'game_type',
            'play_date',
            name='uq_school_book_game_calendar_date'
        )
    )
    op.create_index('ix_game_calendar_entry_book_id', 'game_calendar_entry', ['book_id'], unique=False)
    op.create_index('ix_game_calendar_entry_game_type', 'game_calendar_entry', ['game_type'], unique=False)
    op.create_index('ix_game_calendar_entry_play_date', 'game_calendar_entry', ['play_date'], unique=False)
    op.create_index('ix_game_calendar_entry_shcool_id', 'game_calendar_entry', ['shcool_id'], unique=False)


def downgrade():
    op.drop_index('ix_game_calendar_entry_shcool_id', table_name='game_calendar_entry')
    op.drop_index('ix_game_calendar_entry_play_date', table_name='game_calendar_entry')
    op.drop_index('ix_game_calendar_entry_game_type', table_name='game_calendar_entry')
    op.drop_index('ix_game_calendar_entry_book_id', table_name='game_calendar_entry')
    op.drop_table('game_calendar_entry')

    op.drop_index('ix_school_game_setting_shcool_id', table_name='school_game_setting')
    op.drop_table('school_game_setting')
