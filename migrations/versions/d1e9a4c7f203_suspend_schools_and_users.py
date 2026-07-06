"""suspend schools and users

Revision ID: d1e9a4c7f203
Revises: c8a3e5f1d962
Create Date: 2026-07-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e9a4c7f203'
down_revision = 'c8a3e5f1d962'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shcool', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('shcool', sa.Column('suspended_at', sa.DateTime(), nullable=True))
    op.add_column('shcool', sa.Column('suspended_by', sa.Integer(), nullable=True))
    op.add_column('shcool', sa.Column('suspended_reason', sa.String(length=500), nullable=True))
    op.create_foreign_key(
        'fk_shcool_suspended_by_user',
        'shcool', 'user', ['suspended_by'], ['id'],
    )

    op.add_column('user', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('user', sa.Column('suspended_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('suspended_by', sa.Integer(), nullable=True))
    op.add_column('user', sa.Column('suspended_reason', sa.String(length=500), nullable=True))
    op.create_foreign_key(
        'fk_user_suspended_by_user',
        'user', 'user', ['suspended_by'], ['id'],
    )


def downgrade():
    op.drop_constraint('fk_user_suspended_by_user', 'user', type_='foreignkey')
    op.drop_column('user', 'suspended_reason')
    op.drop_column('user', 'suspended_by')
    op.drop_column('user', 'suspended_at')
    op.drop_column('user', 'is_active')

    op.drop_constraint('fk_shcool_suspended_by_user', 'shcool', type_='foreignkey')
    op.drop_column('shcool', 'suspended_reason')
    op.drop_column('shcool', 'suspended_by')
    op.drop_column('shcool', 'suspended_at')
    op.drop_column('shcool', 'is_active')
