"""platform book instances

Revision ID: f6b8c2d4a901
Revises: e9f3b1c8a742
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b8c2d4a901'
down_revision = 'e9f3b1c8a742'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('book', sa.Column('is_platform_book', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('book', sa.Column('created_by', sa.Integer(), nullable=True))
    op.add_column('book', sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.create_index('ix_book_is_platform_book', 'book', ['is_platform_book'], unique=False)
    op.create_index('ix_book_created_by', 'book', ['created_by'], unique=False)
    op.create_index('ix_book_active', 'book', ['active'], unique=False)
    op.create_foreign_key('fk_book_created_by_user', 'book', 'user', ['created_by'], ['id'])
    op.alter_column('book', 'is_platform_book', server_default=None)
    op.alter_column('book', 'active', server_default=None)

    op.alter_column('book_story', 'shcool_id', existing_type=sa.Integer(), nullable=True)

    op.create_table(
        'school_book_instance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shcool_id', 'book_id', name='uq_school_platform_book')
    )
    op.create_index(op.f('ix_school_book_instance_book_id'), 'school_book_instance', ['book_id'], unique=False)
    op.create_index(op.f('ix_school_book_instance_shcool_id'), 'school_book_instance', ['shcool_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_school_book_instance_shcool_id'), table_name='school_book_instance')
    op.drop_index(op.f('ix_school_book_instance_book_id'), table_name='school_book_instance')
    op.drop_table('school_book_instance')

    op.alter_column('book_story', 'shcool_id', existing_type=sa.Integer(), nullable=False)

    op.drop_constraint('fk_book_created_by_user', 'book', type_='foreignkey')
    op.drop_index('ix_book_active', table_name='book')
    op.drop_index('ix_book_created_by', table_name='book')
    op.drop_index('ix_book_is_platform_book', table_name='book')
    op.drop_column('book', 'active')
    op.drop_column('book', 'created_by')
    op.drop_column('book', 'is_platform_book')
