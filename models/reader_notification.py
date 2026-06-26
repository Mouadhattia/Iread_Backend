## @file
# @class ReaderNotification

from datetime import datetime

from extensions import db
from models.book import Book
from models.pack import Pack
from models.session import Session
from models.shcool import Shcool
from models.user import User


class ReaderNotification(db.Model):
    __tablename__ = 'reader_notification'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=True, index=True)
    type = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    link = db.Column(db.String(500), nullable=True)
    pack_id = db.Column(db.Integer, db.ForeignKey(Pack.id), nullable=True, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey(Session.id), nullable=True, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=True, index=True)
    game_type = db.Column(db.String(32), nullable=True, index=True)
    play_date = db.Column(db.Date, nullable=True, index=True)
    payload = db.Column(db.JSON, nullable=True)
    dedupe_key = db.Column(db.String(255), nullable=True, index=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship(User, foreign_keys=[user_id], backref='reader_notifications')
    school = db.relationship(Shcool, backref='reader_notifications')
    pack = db.relationship(Pack, backref='reader_notifications')
    session = db.relationship(Session, backref='reader_notifications')
    book = db.relationship(Book, backref='reader_notifications')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'dedupe_key', name='uq_reader_notification_user_dedupe'),
    )

    def __repr__(self):
        return '<ReaderNotification %s user=%s>' % (self.type, self.user_id)
