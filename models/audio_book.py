## @file
# @class AudioBook
# @class AudioBookPage
# @class AudioBookProgress
from datetime import datetime

from extensions import db
from models.shcool import Shcool
from models.user import User


class AudioBook(db.Model):
    __tablename__ = 'audio_book'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    cover_image_url = db.Column(db.String(500), nullable=True)
    cover_image_path = db.Column(db.String(500), nullable=True)
    language = db.Column(db.String(20), nullable=False, default='en')
    level = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default='draft', index=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    created_by_role = db.Column(db.String(30), nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='audio_books')
    creator = db.relationship(User, backref='created_audio_books')
    source_book = db.relationship('Book', backref=db.backref('audio_books', lazy='dynamic'))

    def __repr__(self):
        return '<AudioBook %s>' % self.title


class AudioBookPage(db.Model):
    __tablename__ = 'audio_book_page'

    id = db.Column(db.Integer, primary_key=True)
    audio_book_id = db.Column(db.Integer, db.ForeignKey(AudioBook.id), nullable=False, index=True)
    page_number = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    image_mime_type = db.Column(db.String(100), nullable=True)
    image_file_size = db.Column(db.Integer, nullable=True)
    audio_url = db.Column(db.String(500), nullable=True)
    audio_path = db.Column(db.String(500), nullable=True)
    audio_mime_type = db.Column(db.String(100), nullable=True)
    audio_file_size = db.Column(db.Integer, nullable=True)
    official_text = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), nullable=False, default='en')
    audio_duration_ms = db.Column(db.Integer, nullable=True)
    image_position = db.Column(db.String(20), nullable=False, default='above')
    font_size = db.Column(db.Integer, nullable=False, default=18)
    alignment_json = db.Column(db.JSON, nullable=True)
    alignment_status = db.Column(db.String(30), nullable=False, default='draft', index=True)
    similarity = db.Column(db.Float, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    audio_book = db.relationship(
        AudioBook,
        backref=db.backref('pages', cascade='all, delete-orphan', order_by='AudioBookPage.page_number')
    )

    __table_args__ = (
        db.UniqueConstraint('audio_book_id', 'page_number', name='uq_audio_book_page_number'),
        db.Index('ix_audio_book_page_book_active_page', 'audio_book_id', 'active', 'page_number'),
        db.Index('ix_audio_book_page_book_active_status', 'audio_book_id', 'active', 'alignment_status'),
    )

    def __repr__(self):
        return '<AudioBookPage book=%s page=%s>' % (self.audio_book_id, self.page_number)


class AudioBookProgress(db.Model):
    __tablename__ = 'audio_book_progress'

    user_id = db.Column(db.Integer, db.ForeignKey(User.id), primary_key=True)
    audio_book_id = db.Column(db.Integer, db.ForeignKey(AudioBook.id), primary_key=True)
    current_page_number = db.Column(db.Integer, nullable=False, default=1)
    current_time_ms = db.Column(db.Integer, nullable=False, default=0)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    user = db.relationship(User, backref=db.backref('audio_book_progress', cascade='all, delete-orphan'))
    audio_book = db.relationship(AudioBook, backref=db.backref('reader_progress', cascade='all, delete-orphan'))

    def __repr__(self):
        return '<AudioBookProgress user=%s audio_book=%s>' % (self.user_id, self.audio_book_id)
