"""audio book page query indexes

Revision ID: a8e7c4d2f9b1
Revises: f4d2c8b9a7e1
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e7c4d2f9b1'
down_revision = 'f4d2c8b9a7e1'
branch_labels = None
depends_on = None


def index_exists(index_name):
    inspector = sa.inspect(op.get_bind())
    return any(index['name'] == index_name for index in inspector.get_indexes('audio_book_page'))


def upgrade():
    if not index_exists('ix_audio_book_page_book_active_page'):
        op.create_index(
            'ix_audio_book_page_book_active_page',
            'audio_book_page',
            ['audio_book_id', 'active', 'page_number'],
            unique=False
        )
    if not index_exists('ix_audio_book_page_book_active_status'):
        op.create_index(
            'ix_audio_book_page_book_active_status',
            'audio_book_page',
            ['audio_book_id', 'active', 'alignment_status'],
            unique=False
        )


def downgrade():
    if index_exists('ix_audio_book_page_book_active_status'):
        op.drop_index('ix_audio_book_page_book_active_status', table_name='audio_book_page')
    if index_exists('ix_audio_book_page_book_active_page'):
        op.drop_index('ix_audio_book_page_book_active_page', table_name='audio_book_page')
