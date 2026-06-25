"""audio books book link and display settings

Revision ID: e5b8c2a4d9f7
Revises: d9a4c1b7e8f2
Create Date: 2026-06-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b8c2a4d9f7'
down_revision = 'd9a4c1b7e8f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('audio_book', sa.Column('book_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_audio_book_book_id'), 'audio_book', ['book_id'], unique=False)
    op.create_foreign_key(
        'fk_audio_book_book_id_book',
        'audio_book',
        'book',
        ['book_id'],
        ['id']
    )

    op.add_column(
        'audio_book_page',
        sa.Column('image_position', sa.String(length=20), nullable=False, server_default='above')
    )
    op.add_column(
        'audio_book_page',
        sa.Column('font_size', sa.Integer(), nullable=False, server_default='18')
    )
    op.alter_column('audio_book_page', 'image_position', server_default=None)
    op.alter_column('audio_book_page', 'font_size', server_default=None)


def downgrade():
    op.drop_column('audio_book_page', 'font_size')
    op.drop_column('audio_book_page', 'image_position')
    op.drop_constraint('fk_audio_book_book_id_book', 'audio_book', type_='foreignkey')
    op.drop_index(op.f('ix_audio_book_book_id'), table_name='audio_book')
    op.drop_column('audio_book', 'book_id')
