## @file
# @class GlobalGameCalendarEntry
from datetime import datetime

from extensions import db
from models.book import Book


class GlobalGameCalendarEntry(db.Model):
    """The platform-level master game schedule, authored once by a super admin.

    Deliberately *not* a nullable-school row in `game_calendar_entry`: schools
    never own or edit these days, and a school's players reach them through a
    date mapping (see `resolve_global_play_date`) rather than a copy. One row
    per book/game/day serves every school on the platform, so a super-admin
    word edit lands everywhere at once.

    `play_date` is the master calendar date. Schools running in `global` mode
    read it directly; schools running in `from_start` mode read it through
    their own offset from the first scheduled day.
    """

    __tablename__ = 'global_game_calendar_entry'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    game_type = db.Column(db.String(32), nullable=False, index=True)
    play_date = db.Column(db.Date, nullable=False, index=True)
    words = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    book = db.relationship(Book, backref='global_game_calendar_entries')

    __table_args__ = (
        db.UniqueConstraint(
            'book_id',
            'game_type',
            'play_date',
            name='uq_global_book_game_calendar_date'
        ),
    )

    def __repr__(self):
        return '<GlobalGameCalendarEntry book=%s game=%s date=%s>' % (
            self.book_id,
            self.game_type,
            self.play_date,
        )
