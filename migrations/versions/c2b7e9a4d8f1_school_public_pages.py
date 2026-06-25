"""school public pages

Revision ID: c2b7e9a4d8f1
Revises: a7c9e2f4b6d8
Create Date: 2026-06-12 00:00:00.000000

"""
import json
import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2b7e9a4d8f1'
down_revision = 'a7c9e2f4b6d8'
branch_labels = None
depends_on = None


def normalize_school_slug(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-zA-Z0-9]+', '-', value).strip('-').lower()
    return value or 'school'


def unique_slug(value, used_slugs):
    base_slug = normalize_school_slug(value)
    slug = base_slug
    counter = 2
    while slug in used_slugs:
        slug = f'{base_slug}-{counter}'
        counter += 1
    used_slugs.add(slug)
    return slug


def upgrade():
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        """
        SELECT LOWER(name) AS normalized_name, COUNT(*) AS total
        FROM shcool
        GROUP BY LOWER(name)
        HAVING COUNT(*) > 1
        """
    )).fetchall()
    if duplicates:
        duplicate_names = ', '.join([row[0] for row in duplicates])
        raise Exception(
            'Cannot add unique school name index. Duplicate school names found: '
            f'{duplicate_names}'
        )

    op.create_index('uq_shcool_name', 'shcool', ['name'], unique=True)

    op.create_table(
        'school_public_page',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('logo', sa.String(length=500), nullable=True),
        sa.Column('cover_image', sa.String(length=500), nullable=True),
        sa.Column('headline', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('sections', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shcool_id', name='uq_school_public_page_shcool_id'),
        sa.UniqueConstraint('slug', name='uq_school_public_page_slug')
    )
    op.create_index('ix_school_public_page_shcool_id', 'school_public_page', ['shcool_id'], unique=False)
    op.create_index('ix_school_public_page_slug', 'school_public_page', ['slug'], unique=False)

    schools = connection.execute(sa.text('SELECT id, name FROM shcool ORDER BY id ASC')).fetchall()
    used_slugs = set()
    now = datetime.now()
    for school_id, school_name in schools:
        slug = unique_slug(school_name, used_slugs)
        sections = json.dumps([{
            'title': 'Welcome',
            'content': f'Welcome to {school_name} on IREAD.',
            'image': None
        }])
        connection.execute(
            sa.text(
                """
                INSERT INTO school_public_page
                    (shcool_id, slug, active, headline, description, sections, created_at, updated_at)
                VALUES
                    (:shcool_id, :slug, :active, :headline, :description, :sections, :created_at, :updated_at)
                """
            ),
            {
                'shcool_id': school_id,
                'slug': slug,
                'active': True,
                'headline': f'Read with {school_name}',
                'description': f'Welcome to {school_name} on IREAD.',
                'sections': sections,
                'created_at': now,
                'updated_at': now
            }
        )


def downgrade():
    op.drop_index('ix_school_public_page_slug', table_name='school_public_page')
    op.drop_index('ix_school_public_page_shcool_id', table_name='school_public_page')
    op.drop_table('school_public_page')
    op.drop_index('uq_shcool_name', table_name='shcool')
