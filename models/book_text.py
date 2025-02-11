## @file 
#@class Follow_book
from extensions import db
from models.book import Book


##
# @brief Table for storing the relationship between users and books they follow.
#
class Book_text(db.Model):
    __tablename__='bok_text'
    id = db.Column(db.Integer, primary_key=True)
    book_id=db.Column(db.ForeignKey(Book.id),nullable=False)
    text = db.Column(db.Text, nullable=False)
     
    def __repr__(self):
        return '< Book_text %s >' %self.book_id