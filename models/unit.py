## @file 
#@class Follow_book
from extensions import db
from models.book import Book


##
# @brief Table for storing the relationship between users and books they follow.
#
class Unit(db.Model):
    __tablename__='unit'
    id = db.Column(db.Integer, primary_key=True)
    book_id=db.Column(db.ForeignKey(Book.id),nullable=True)
    name = db.Column(db.String(64), nullable=False)  
     
    def __repr__(self):
        return '< Unit %s >' %self.book_id