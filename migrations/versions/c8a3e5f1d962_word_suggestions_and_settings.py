"""word suggestions and platform settings

Revision ID: c8a3e5f1d962
Revises: a4d7f1c9b358
Create Date: 2026-07-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8a3e5f1d962'
down_revision = 'a4d7f1c9b358'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('word_sense', sa.Column('enrichment_updated_by', sa.Integer(), nullable=True))
    op.add_column('word_sense', sa.Column('enrichment_updated_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_word_sense_enrichment_updated_by_user',
        'word_sense', 'user', ['enrichment_updated_by'], ['id'],
    )

    op.create_table(
        'word_sense_suggestion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word_sense_id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('suggestion_type', sa.String(length=16), nullable=False),
        sa.Column('suggested_cefr_level', sa.String(length=2), nullable=True),
        sa.Column('suggested_proper_noun_excluded', sa.Boolean(), nullable=True),
        sa.Column('suggested_definition', sa.Text(), nullable=True),
        sa.Column('suggested_synonyms', sa.JSON(), nullable=True),
        sa.Column('suggested_example_sentence', sa.Text(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('suggested_by', sa.Integer(), nullable=False),
        sa.Column('suggested_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_note', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['word_sense_id'], ['word_sense.id']),
        sa.ForeignKeyConstraint(['school_id'], ['shcool.id']),
        sa.ForeignKeyConstraint(['suggested_by'], ['user.id']),
        sa.ForeignKeyConstraint(['reviewed_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_word_sense_suggestion_word_sense_id', 'word_sense_suggestion', ['word_sense_id'], unique=False)
    op.create_index('ix_word_sense_suggestion_school_id', 'word_sense_suggestion', ['school_id'], unique=False)
    op.create_index('ix_word_sense_suggestion_status', 'word_sense_suggestion', ['status'], unique=False)

    op.create_table(
        'platform_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('require_dictionary_approval', sa.Boolean(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('platform_settings')

    op.drop_index('ix_word_sense_suggestion_status', table_name='word_sense_suggestion')
    op.drop_index('ix_word_sense_suggestion_school_id', table_name='word_sense_suggestion')
    op.drop_index('ix_word_sense_suggestion_word_sense_id', table_name='word_sense_suggestion')
    op.drop_table('word_sense_suggestion')

    op.drop_constraint('fk_word_sense_enrichment_updated_by_user', 'word_sense', type_='foreignkey')
    op.drop_column('word_sense', 'enrichment_updated_at')
    op.drop_column('word_sense', 'enrichment_updated_by')
