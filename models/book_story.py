## @file
# @class BookStory
from datetime import datetime

from extensions import db
from models.book import Book
from models.shcool import Shcool
from models.user import User


class BookStory(db.Model):
    __tablename__ = 'book_story'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=True, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_url = db.Column(db.String(500), nullable=True)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    page_count = db.Column(db.Integer, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    book = db.relationship(Book, backref=db.backref('stories', cascade='all, delete-orphan'))
    school = db.relationship(Shcool, backref='book_stories')
    uploader = db.relationship(User, backref='uploaded_book_stories')

    def __repr__(self):
        return '<BookStory %s>' % self.title
