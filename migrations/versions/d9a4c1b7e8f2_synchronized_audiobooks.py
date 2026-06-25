"""synchronized audiobooks

Revision ID: d9a4c1b7e8f2
Revises: c1f4e8a9b2d7
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9a4c1b7e8f2'
down_revision = 'c1f4e8a9b2d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audio_book',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('cover_image_url', sa.String(length=500), nullable=True),
        sa.Column('cover_image_path', sa.String(length=500), nullable=True),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('level', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_by_role', sa.String(length=30), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audio_book_active'), 'audio_book', ['active'], unique=False)
    op.create_index(op.f('ix_audio_book_created_by_id'), 'audio_book', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_audio_book_shcool_id'), 'audio_book', ['shcool_id'], unique=False)
    op.create_index(op.f('ix_audio_book_status'), 'audio_book', ['status'], unique=False)

    op.create_table(
        'audio_book_page',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audio_book_id', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('image_path', sa.String(length=500), nullable=True),
        sa.Column('image_mime_type', sa.String(length=100), nullable=True),
        sa.Column('image_file_size', sa.Integer(), nullable=True),
        sa.Column('audio_url', sa.String(length=500), nullable=True),
        sa.Column('audio_path', sa.String(length=500), nullable=True),
        sa.Column('audio_mime_type', sa.String(length=100), nullable=True),
        sa.Column('audio_file_size', sa.Integer(), nullable=True),
        sa.Column('official_text', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('audio_duration_ms', sa.Integer(), nullable=True),
        sa.Column('alignment_json', sa.JSON(), nullable=True),
        sa.Column('alignment_status', sa.String(length=30), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['audio_book_id'], ['audio_book.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('audio_book_id', 'page_number', name='uq_audio_book_page_number')
    )
    op.create_index(op.f('ix_audio_book_page_active'), 'audio_book_page', ['active'], unique=False)
    op.create_index(op.f('ix_audio_book_page_alignment_status'), 'audio_book_page', ['alignment_status'], unique=False)
    op.create_index(op.f('ix_audio_book_page_audio_book_id'), 'audio_book_page', ['audio_book_id'], unique=False)

    op.create_table(
        'audio_book_progress',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('audio_book_id', sa.Integer(), nullable=False),
        sa.Column('current_page_number', sa.Integer(), nullable=False),
        sa.Column('current_time_ms', sa.Integer(), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['audio_book_id'], ['audio_book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('user_id', 'audio_book_id')
    )


def downgrade():
    op.drop_table('audio_book_progress')
    op.drop_index(op.f('ix_audio_book_page_audio_book_id'), table_name='audio_book_page')
    op.drop_index(op.f('ix_audio_book_page_alignment_status'), table_name='audio_book_page')
    op.drop_index(op.f('ix_audio_book_page_active'), table_name='audio_book_page')
    op.drop_table('audio_book_page')
    op.drop_index(op.f('ix_audio_book_status'), table_name='audio_book')
    op.drop_index(op.f('ix_audio_book_shcool_id'), table_name='audio_book')
    op.drop_index(op.f('ix_audio_book_created_by_id'), table_name='audio_book')
    op.drop_index(op.f('ix_audio_book_active'), table_name='audio_book')
    op.drop_table('audio_book')
