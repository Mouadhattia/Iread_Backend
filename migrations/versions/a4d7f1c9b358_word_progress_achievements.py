"""word progress and achievements

Revision ID: a4d7f1c9b358
Revises: f3c8a1d92b56
Create Date: 2026-07-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4d7f1c9b358'
down_revision = 'f3c8a1d92b56'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'word_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('word_sense_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column('pip_bee_genius', sa.Boolean(), nullable=False),
        sa.Column('pip_word_explorer', sa.Boolean(), nullable=False),
        sa.Column('pip_think_word', sa.Boolean(), nullable=False),
        sa.Column('pip_intellect_link', sa.Boolean(), nullable=False),
        sa.Column('distinct_sources_count', sa.Integer(), nullable=False),
        sa.Column('distinct_days_count', sa.Integer(), nullable=False),
        sa.Column('has_unaided_clear', sa.Boolean(), nullable=False),
        sa.Column('consecutive_no_hint_clears', sa.Integer(), nullable=False),
        sa.Column('first_encountered_at', sa.DateTime(), nullable=False),
        sa.Column('first_guessed_at', sa.DateTime(), nullable=True),
        sa.Column('first_known_at', sa.DateTime(), nullable=True),
        sa.Column('mastered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['word_sense_id'], ['word_sense.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'word_sense_id', name='uq_word_progress_user_word_sense'),
    )
    op.create_index('ix_word_progress_user_id', 'word_progress', ['user_id'], unique=False)
    op.create_index('ix_word_progress_word_sense_id', 'word_progress', ['word_sense_id'], unique=False)

    op.create_table(
        'word_progress_evidence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word_progress_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('hints_used', sa.Integer(), nullable=False),
        sa.Column('heaviest_hint_tier', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['word_progress_id'], ['word_progress.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_word_progress_evidence_word_progress_id', 'word_progress_evidence', ['word_progress_id'], unique=False)
    op.create_index('ix_word_progress_evidence_occurred_on', 'word_progress_evidence', ['occurred_on'], unique=False)

    op.create_table(
        'user_streak',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('current_streak', sa.Integer(), nullable=False),
        sa.Column('best_streak', sa.Integer(), nullable=False),
        sa.Column('last_played_on', sa.Date(), nullable=True),
        sa.Column('grace_available', sa.Boolean(), nullable=False),
        sa.Column('grace_used_on', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )

    op.create_table(
        'user_achievement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('achievement_key', sa.String(length=64), nullable=False),
        sa.Column('tier', sa.Integer(), nullable=True),
        sa.Column('earned_at', sa.DateTime(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'achievement_key', 'tier', name='uq_user_achievement_key_tier'),
    )
    op.create_index('ix_user_achievement_user_id', 'user_achievement', ['user_id'], unique=False)

    op.create_table(
        'self_reported_word',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('surface_form', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'surface_form', name='uq_self_reported_word_user_surface'),
    )
    op.create_index('ix_self_reported_word_user_id', 'self_reported_word', ['user_id'], unique=False)


def downgrade():
    op.drop_index('ix_self_reported_word_user_id', table_name='self_reported_word')
    op.drop_table('self_reported_word')

    op.drop_index('ix_user_achievement_user_id', table_name='user_achievement')
    op.drop_table('user_achievement')

    op.drop_table('user_streak')

    op.drop_index('ix_word_progress_evidence_occurred_on', table_name='word_progress_evidence')
    op.drop_index('ix_word_progress_evidence_word_progress_id', table_name='word_progress_evidence')
    op.drop_table('word_progress_evidence')

    op.drop_index('ix_word_progress_word_sense_id', table_name='word_progress')
    op.drop_index('ix_word_progress_user_id', table_name='word_progress')
    op.drop_table('word_progress')
