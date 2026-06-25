"""school invitation codes

Revision ID: 8c2f7d9e4a11
Revises: 634199115db3
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c2f7d9e4a11'
down_revision = '634199115db3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'school_invitation_code',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(
        op.f('ix_school_invitation_code_shcool_id'),
        'school_invitation_code',
        ['shcool_id'],
        unique=False
    )


def downgrade():
    op.drop_index(op.f('ix_school_invitation_code_shcool_id'), table_name='school_invitation_code')
    op.drop_table('school_invitation_code')
