"""global packs

Revision ID: a7c9e2f4b6d8
Revises: f6b8c2d4a901
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c9e2f4b6d8'
down_revision = 'f6b8c2d4a901'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pack', sa.Column('is_global_pack', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('pack', sa.Column('created_by', sa.Integer(), nullable=True))
    op.add_column('pack', sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.create_index('ix_pack_is_global_pack', 'pack', ['is_global_pack'], unique=False)
    op.create_index('ix_pack_created_by', 'pack', ['created_by'], unique=False)
    op.create_index('ix_pack_active', 'pack', ['active'], unique=False)
    op.create_foreign_key('fk_pack_created_by_user', 'pack', 'user', ['created_by'], ['id'])
    op.alter_column('pack', 'is_global_pack', server_default=None)
    op.alter_column('pack', 'active', server_default=None)

    op.add_column('unit', sa.Column('pack_id', sa.Integer(), nullable=True))
    op.create_index('ix_unit_pack_id', 'unit', ['pack_id'], unique=False)
    op.create_foreign_key('fk_unit_pack_id_pack', 'unit', 'pack', ['pack_id'], ['id'])

    op.create_table(
        'school_pack_instance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('pack_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['pack_id'], ['pack.id']),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shcool_id', 'pack_id', name='uq_school_global_pack')
    )
    op.create_index(op.f('ix_school_pack_instance_pack_id'), 'school_pack_instance', ['pack_id'], unique=False)
    op.create_index(op.f('ix_school_pack_instance_shcool_id'), 'school_pack_instance', ['shcool_id'], unique=False)

    op.create_table(
        'global_teacher',
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['user.id']),
        sa.PrimaryKeyConstraint('teacher_id')
    )
    op.alter_column('global_teacher', 'active', server_default=None)


def downgrade():
    op.drop_table('global_teacher')

    op.drop_index(op.f('ix_school_pack_instance_shcool_id'), table_name='school_pack_instance')
    op.drop_index(op.f('ix_school_pack_instance_pack_id'), table_name='school_pack_instance')
    op.drop_table('school_pack_instance')

    op.drop_constraint('fk_unit_pack_id_pack', 'unit', type_='foreignkey')
    op.drop_index('ix_unit_pack_id', table_name='unit')
    op.drop_column('unit', 'pack_id')

    op.drop_constraint('fk_pack_created_by_user', 'pack', type_='foreignkey')
    op.drop_index('ix_pack_active', table_name='pack')
    op.drop_index('ix_pack_created_by', table_name='pack')
    op.drop_index('ix_pack_is_global_pack', table_name='pack')
    op.drop_column('pack', 'active')
    op.drop_column('pack', 'created_by')
    op.drop_column('pack', 'is_global_pack')
