"""book school owner

Revision ID: d4a7c9b2e6f1
Revises: c7b2a8f4d1e9
Create Date: 2026-06-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a7c9b2e6f1'
down_revision = 'c7b2a8f4d1e9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('book', sa.Column('shcool_id', sa.Integer(), nullable=True))
    op.create_index('ix_book_shcool_id', 'book', ['shcool_id'], unique=False)
    op.create_foreign_key('fk_book_shcool_id_shcool', 'book', 'shcool', ['shcool_id'], ['id'])
    op.execute(
        """
        UPDATE book b
        JOIN (
            SELECT bp.book_id, MIN(p.shcool_id) AS shcool_id
            FROM book_pack bp
            JOIN pack p ON p.id = bp.pack_id
            WHERE p.shcool_id IS NOT NULL
            GROUP BY bp.book_id
        ) school_book ON school_book.book_id = b.id
        SET b.shcool_id = school_book.shcool_id
        WHERE b.shcool_id IS NULL
        """
    )


def downgrade():
    op.drop_constraint('fk_book_shcool_id_shcool', 'book', type_='foreignkey')
    op.drop_index('ix_book_shcool_id', table_name='book')
    op.drop_column('book', 'shcool_id')
