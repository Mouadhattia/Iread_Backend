## @file 
#@class Contain
from extensions import db
from models.book import Book

##
# @brief Table for storing the relationship between packs and books.
#
class About_Book(db.Model):
    __tablename__='about_book'
    id = db.Column(db.Integer, primary_key=True,unique=True)
    book_id=db.Column(db.Integer,db.ForeignKey(Book.id))
    about = db.Column(db.JSON)
