## @file
# @class GameCalendarEntry
from datetime import datetime

from extensions import db
from models.book import Book
from models.shcool import Shcool


class GameCalendarEntry(db.Model):
    __tablename__ = 'game_calendar_entry'

    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    game_type = db.Column(db.String(32), nullable=False, index=True)
    play_date = db.Column(db.Date, nullable=False, index=True)
    words = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='game_calendar_entries')
    book = db.relationship(Book, backref='game_calendar_entries')

    __table_args__ = (
        db.UniqueConstraint(
            'shcool_id',
            'book_id',
            'game_type',
            'play_date',
            name='uq_school_book_game_calendar_date'
        ),
    )

    def __repr__(self):
        return '<GameCalendarEntry school=%s book=%s game=%s date=%s>' % (
            self.shcool_id,
            self.book_id,
            self.game_type,
            self.play_date,
        )
