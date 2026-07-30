"""per-school self-hosted file storage

Replaces Cloudinary with a storage folder per school on our own server.

school_file indexes every uploaded asset (story audio/images, book covers and
PDFs, pack images) so the school-admin storage manager can list files and
report disk usage without walking the filesystem on each request.

shcool.storage_quota_mb overrides the platform-wide allowance per school;
NULL means "use ConfigClass.SCHOOL_STORAGE_QUOTA_MB". NULL is meaningfully
different from 0 here -- "follow the default" vs "this school gets none".

Revision ID: e2c8b4d1f036
Revises: d1b4f7c3a982
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2c8b4d1f036'
down_revision = 'd1b4f7c3a982'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'school_file',
        sa.Column('id', sa.Integer(), nullable=False),
        # Nullable: NULL is a platform-owned asset, matching how book/pack/
        # book_story already encode "not school-specific".
        sa.Column('shcool_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('relative_path', sa.String(length=500), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=120), nullable=True),
        # BigInteger: a school's audio library summed over a term can exceed
        # the 2 GB an Integer column tops out at.
        sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('linked_type', sa.String(length=40), nullable=True),
        sa.Column('linked_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        # One row per file on disk: the path is the natural key, and a unique
        # constraint is what makes the indexing script safely re-runnable.
        sa.UniqueConstraint('relative_path', name='uq_school_file_relative_path')
    )
    op.create_index('ix_school_file_shcool_id', 'school_file', ['shcool_id'])
    op.create_index('ix_school_file_category', 'school_file', ['category'])
    # The storage manager's default view is "this school's files, newest first",
    # and the usage totals group by category within a school.
    op.create_index(
        'ix_school_file_school_category',
        'school_file',
        ['shcool_id', 'category', 'active']
    )
    # Resolving "which file backs this book cover?" when deleting an entity.
    op.create_index(
        'ix_school_file_linked',
        'school_file',
        ['linked_type', 'linked_id']
    )

    op.add_column('shcool', sa.Column('storage_quota_mb', sa.Integer(), nullable=True))

    # A self-hosted media URL (origin + /media/ + school folder + category +
    # uuid filename) is around 115 characters, so the old 100-char session.img
    # would truncate one into a broken link. The other image columns
    # (book.img 300, pack.img 200, user.img 300, public page 500) already fit.
    op.alter_column('session', 'img',
                    existing_type=sa.String(length=100),
                    type_=sa.String(length=500),
                    existing_nullable=True)


def downgrade():
    op.alter_column('session', 'img',
                    existing_type=sa.String(length=500),
                    type_=sa.String(length=100),
                    existing_nullable=True)
    op.drop_column('shcool', 'storage_quota_mb')
    op.drop_index('ix_school_file_linked', table_name='school_file')
    op.drop_index('ix_school_file_school_category', table_name='school_file')
    op.drop_index('ix_school_file_category', table_name='school_file')
    op.drop_index('ix_school_file_shcool_id', table_name='school_file')
    op.drop_table('school_file')
