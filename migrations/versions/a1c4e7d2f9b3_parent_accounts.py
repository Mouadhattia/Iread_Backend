"""parent accounts

Revision ID: a1c4e7d2f9b3
Revises: d1e9a4c7f203
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e7d2f9b3'
down_revision = 'd1e9a4c7f203'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'parent',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id_invoicing_api', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.add_column('reader', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_reader_parent_id_user',
        'reader', 'user', ['parent_id'], ['id'],
    )

    op.add_column('user_shcool', sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('user_shcool', sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.alter_column('user_shcool', 'joined_at', server_default=None)
    op.alter_column('user_shcool', 'is_default', server_default=None)


def downgrade():
    op.drop_column('user_shcool', 'is_default')
    op.drop_column('user_shcool', 'joined_at')

    op.drop_constraint('fk_reader_parent_id_user', 'reader', type_='foreignkey')
    op.drop_column('reader', 'parent_id')

    op.drop_table('parent')
