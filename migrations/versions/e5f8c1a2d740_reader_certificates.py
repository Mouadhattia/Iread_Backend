"""reader certificates (Global Reading Passport §2)

Revision ID: e5f8c1a2d740
Revises: d4e7b0a3c9f1
Create Date: 2026-07-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f8c1a2d740'
down_revision = 'd4e7b0a3c9f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'certificate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('milestone_key', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('cefr_level', sa.String(length=10), nullable=True),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column('serial', sa.String(length=40), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('serial'),
        sa.UniqueConstraint('user_id', 'milestone_key', name='uq_certificate_user_milestone'),
    )
    op.create_index(op.f('ix_certificate_user_id'), 'certificate', ['user_id'], unique=False)
    op.create_index(op.f('ix_certificate_kind'), 'certificate', ['kind'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_certificate_kind'), table_name='certificate')
    op.drop_index(op.f('ix_certificate_user_id'), table_name='certificate')
    op.drop_table('certificate')
