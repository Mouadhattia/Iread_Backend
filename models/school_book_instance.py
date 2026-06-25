## @file
# @class SchoolBookInstance
from datetime import datetime

from extensions import db
from models.book import Book
from models.shcool import Shcool
from models.user import User


class SchoolBookInstance(db.Model):
    __tablename__ = 'school_book_instance'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    book = db.relationship(Book, backref='school_instances')
    school = db.relationship(Shcool, backref='platform_book_instances')
    creator = db.relationship(User, backref='created_school_book_instances')

    __table_args__ = (
        db.UniqueConstraint('shcool_id', 'book_id', name='uq_school_platform_book'),
    )

    def __repr__(self):
        return '<SchoolBookInstance school=%s book=%s>' % (self.shcool_id, self.book_id)
