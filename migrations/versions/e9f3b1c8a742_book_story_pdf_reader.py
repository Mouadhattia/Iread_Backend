"""book story pdf reader

Revision ID: e9f3b1c8a742
Revises: d4a7c9b2e6f1
Create Date: 2026-06-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9f3b1c8a742'
down_revision = 'd4a7c9b2e6f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'book_story',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_url', sa.String(length=500), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_book_story_book_id'), 'book_story', ['book_id'], unique=False)
    op.create_index(op.f('ix_book_story_shcool_id'), 'book_story', ['shcool_id'], unique=False)

    op.create_table(
        'reader_story_progress',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('current_page', sa.Integer(), nullable=False),
        sa.Column('zoom', sa.Float(), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('last_read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['story_id'], ['book_story.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('user_id', 'story_id')
    )


def downgrade():
    op.drop_table('reader_story_progress')
    op.drop_index(op.f('ix_book_story_shcool_id'), table_name='book_story')
    op.drop_index(op.f('ix_book_story_book_id'), table_name='book_story')
    op.drop_table('book_story')
