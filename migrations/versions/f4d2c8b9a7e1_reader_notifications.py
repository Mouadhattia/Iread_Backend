"""reader notifications

Revision ID: f4d2c8b9a7e1
Revises: e5b8c2a4d9f7
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4d2c8b9a7e1'
down_revision = 'e5b8c2a4d9f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reader_notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('pack_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column('game_type', sa.String(length=32), nullable=True),
        sa.Column('play_date', sa.Date(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('dedupe_key', sa.String(length=255), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['pack_id'], ['pack.id']),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_reader_notification_user_dedupe')
    )
    op.create_index(op.f('ix_reader_notification_book_id'), 'reader_notification', ['book_id'], unique=False)
    op.create_index(op.f('ix_reader_notification_created_at'), 'reader_notification', ['created_at'], unique=False)
    op.create_index(op.f('ix_reader_notification_dedupe_key'), 'reader_notification', ['dedupe_key'], unique=False)
    op.create_index(op.f('ix_reader_notification_expires_at'), 'reader_notification', ['expires_at'], unique=False)
    op.create_index(op.f('ix_reader_notification_game_type'), 'reader_notification', ['game_type'], unique=False)
    op.create_index(op.f('ix_reader_notification_pack_id'), 'reader_notification', ['pack_id'], unique=False)
    op.create_index(op.f('ix_reader_notification_play_date'), 'reader_notification', ['play_date'], unique=False)
    op.create_index(op.f('ix_reader_notification_read_at'), 'reader_notification', ['read_at'], unique=False)
    op.create_index(op.f('ix_reader_notification_session_id'), 'reader_notification', ['session_id'], unique=False)
    op.create_index(op.f('ix_reader_notification_shcool_id'), 'reader_notification', ['shcool_id'], unique=False)
    op.create_index(op.f('ix_reader_notification_type'), 'reader_notification', ['type'], unique=False)
    op.create_index(op.f('ix_reader_notification_user_id'), 'reader_notification', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_reader_notification_user_id'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_type'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_shcool_id'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_session_id'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_read_at'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_play_date'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_pack_id'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_game_type'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_expires_at'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_dedupe_key'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_created_at'), table_name='reader_notification')
    op.drop_index(op.f('ix_reader_notification_book_id'), table_name='reader_notification')
    op.drop_table('reader_notification')
