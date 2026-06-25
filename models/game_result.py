## @file 
#@class Contain
from extensions import db
from models.user import User
from models.book import Book
from models.pack import Pack
from enum import Enum
from datetime import date
class GameEnum(Enum):
    BEE = 'bee-genius'
    WORDEXPLORER = 'Word-explorer'
    THINKWORD = 'think-word'
    INTELLECTLNK = 'intellect-link'

##
# @brief Table for storing the relationship between packs and books.
#
class Game_result(db.Model):
    __tablename__='game_result'
    id = db.Column(db.Integer, primary_key=True,unique=True)
    score=db.Column(db.Float,default=0)
    game=db.Column(db.Enum(GameEnum),nullable=False)
    user_id=db.Column(db.ForeignKey(User.id))
    book_id=db.Column(db.ForeignKey(Book.id))
    day = db.Column(db.Date, default=date.today)
    completed = db.Column(db.Boolean, default=False)
    words_learned = db.Column(db.JSON,default=[])
    time_spent_seconds = db.Column(db.Integer, default=0)
 
    def __repr__(self):
        return '<Game_result %s>' % self.game


