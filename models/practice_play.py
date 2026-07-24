## @file
# @class PracticePlay
from datetime import date, datetime

from extensions import db
from models.book import Book
from models.game_result import GameEnum
from models.user import User


## @brief One row per finished practice-mode round (Word Search, Strands,
# Spelling Bee, the classic word-guess game) -- unlike Game_result, which is
# scoped to Daily Run and upserts a single row per user/day/game/book, practice
# is unlimited (Achievement & Word-Progress brief) so every completed round is
# logged as its own row here, purely for the parent-analytics "games played"
# chart (see get_child_analytics in apps/reader/routes.py).
class PracticePlay(db.Model):
    __tablename__ = 'practice_play'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey(User.id), nullable=False, index=True)
    book_id = db.Column(db.ForeignKey(Book.id), nullable=True)
    game = db.Column(db.Enum(GameEnum), nullable=False)
    score = db.Column(db.Float, default=0)
    day = db.Column(db.Date, default=date.today, index=True)
    words_learned = db.Column(db.JSON, default=[])
    time_spent_seconds = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return '<PracticePlay %s>' % self.game
