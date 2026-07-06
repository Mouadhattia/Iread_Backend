"""word data cefr layer

Revision ID: f3c8a1d92b56
Revises: e1a5f7c3d9b4
Create Date: 2026-07-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3c8a1d92b56'
down_revision = 'e1a5f7c3d9b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'word_sense',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lemma', sa.String(length=100), nullable=False),
        sa.Column('pos', sa.String(length=16), nullable=False),
        sa.Column('sense_key', sa.String(length=64), nullable=False),
        sa.Column('definition', sa.Text(), nullable=True),
        sa.Column('synonyms', sa.JSON(), nullable=True),
        sa.Column('example_sentence', sa.Text(), nullable=True),
        sa.Column('cefr_level', sa.String(length=2), nullable=True),
        sa.Column('cefr_source', sa.String(length=64), nullable=True),
        sa.Column('cefr_override_level', sa.String(length=2), nullable=True),
        sa.Column('cefr_override_note', sa.String(length=255), nullable=True),
        sa.Column('cefr_override_by', sa.Integer(), nullable=True),
        sa.Column('cefr_override_at', sa.DateTime(), nullable=True),
        sa.Column('proper_noun_excluded', sa.Boolean(), nullable=False),
        sa.Column('frequency_rank', sa.Integer(), nullable=True),
        sa.Column('theme_tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cefr_override_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lemma', 'pos', 'sense_key', name='uq_word_sense_lemma_pos_sense'),
    )
    op.create_index('ix_word_sense_lemma', 'word_sense', ['lemma'], unique=False)
    op.create_index('ix_word_sense_pos', 'word_sense', ['pos'], unique=False)
    op.create_index('ix_word_sense_cefr_level', 'word_sense', ['cefr_level'], unique=False)

    op.create_table(
        'chapter',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('chapter_index', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('book_id', 'chapter_index', name='uq_chapter_book_index'),
    )
    op.create_index('ix_chapter_book_id', 'chapter', ['book_id'], unique=False)

    op.create_table(
        'word_occurrence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word_sense_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('surface_form', sa.String(length=100), nullable=False),
        sa.Column('example_line', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapter.id']),
        sa.ForeignKeyConstraint(['word_sense_id'], ['word_sense.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('word_sense_id', 'chapter_id', name='uq_word_occurrence_sense_chapter'),
    )
    op.create_index('ix_word_occurrence_chapter_id', 'word_occurrence', ['chapter_id'], unique=False)
    op.create_index('ix_word_occurrence_word_sense_id', 'word_occurrence', ['word_sense_id'], unique=False)


def downgrade():
    op.drop_index('ix_word_occurrence_word_sense_id', table_name='word_occurrence')
    op.drop_index('ix_word_occurrence_chapter_id', table_name='word_occurrence')
    op.drop_table('word_occurrence')

    op.drop_index('ix_chapter_book_id', table_name='chapter')
    op.drop_table('chapter')

    op.drop_index('ix_word_sense_cefr_level', table_name='word_sense')
    op.drop_index('ix_word_sense_pos', table_name='word_sense')
    op.drop_index('ix_word_sense_lemma', table_name='word_sense')
    op.drop_table('word_sense')
