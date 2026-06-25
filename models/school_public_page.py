## @file
# @class SchoolPublicPage

import re
import unicodedata
from datetime import datetime

from sqlalchemy import func

from extensions import db
from models.shcool import Shcool


def normalize_school_slug(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-zA-Z0-9]+', '-', value).strip('-').lower()
    return value or 'school'


def generate_unique_school_slug(value, exclude_page_id=None):
    base_slug = normalize_school_slug(value)
    slug = base_slug
    counter = 2

    while True:
        query = SchoolPublicPage.query.filter(func.lower(SchoolPublicPage.slug) == slug.lower())
        if exclude_page_id:
            query = query.filter(SchoolPublicPage.id != exclude_page_id)
        if not query.first():
            return slug
        slug = f'{base_slug}-{counter}'
        counter += 1


def default_school_public_sections(school_name):
    return [{
        'title': 'Welcome',
        'content': f'Welcome to {school_name} on IREAD.',
        'image': None
    }]


def normalize_public_page_sections(sections):
    if not isinstance(sections, list):
        raise ValueError('sections must be a list')
    if len(sections) < 1:
        raise ValueError('At least one section is required')
    if len(sections) > 3:
        raise ValueError('A school public page can have at most 3 sections')

    normalized_sections = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError('Each section must be an object')

        title = str(section.get('title') or '').strip()
        content = str(section.get('content') or '').strip()
        image = str(section.get('image') or '').strip() or None

        if not title and not content:
            raise ValueError('Each section needs a title or content')

        normalized_sections.append({
            'title': title,
            'content': content,
            'image': image
        })

    return normalized_sections


class SchoolPublicPage(db.Model):
    __tablename__ = 'school_public_page'

    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, unique=True, index=True)
    slug = db.Column(db.String(255), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    logo = db.Column(db.String(500), nullable=True)
    cover_image = db.Column(db.String(500), nullable=True)
    headline = db.Column(db.String(255), nullable=True)
    description = db.Column(db.String(1000), nullable=True)
    sections = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref=db.backref('public_page', uselist=False))

    def __repr__(self):
        return '<SchoolPublicPage school=%s slug=%s>' % (self.shcool_id, self.slug)
