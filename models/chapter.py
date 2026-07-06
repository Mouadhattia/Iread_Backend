## @file
# @class Chapter
from datetime import datetime

from extensions import db
from models.book import Book


##
# @brief Table for splitting a Book into chapters, so word occurrences and
# chapter/book completion can be tracked at chapter granularity.
#
class Chapter(db.Model):
    __tablename__ = 'chapter'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    chapter_index = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=True)
    text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    book = db.relationship(
        Book,
        backref=db.backref('chapters', cascade='all, delete-orphan', order_by='Chapter.chapter_index'),
    )

    __table_args__ = (
        db.UniqueConstraint('book_id', 'chapter_index', name='uq_chapter_book_index'),
    )

    def __repr__(self):
        return '<Chapter book=%s index=%s>' % (self.book_id, self.chapter_index)
