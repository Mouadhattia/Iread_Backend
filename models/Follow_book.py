## @file 
#@class Follow_book
from extensions import db
from models.user import User
from models.book import Book
from models.pack import Pack

##
# @brief Table for storing the relationship between users and books they follow.
#
class Follow_book(db.Model):
    __tablename__='follow_book'
    user_id=db.Column(db.ForeignKey(User.id),primary_key=True)
    book_id=db.Column(db.ForeignKey(Book.id),primary_key=True)
    pack_id=db.Column(db.ForeignKey(Pack.id),primary_key=True)

    
    user = db.relationship(User, backref=db.backref('follow_book', cascade='all, delete-orphan'))
    def __repr__(self):
        return '< follow_book %s >' %self.book_id