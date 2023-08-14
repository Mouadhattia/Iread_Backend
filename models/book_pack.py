## @file 
#@class Contain
from extensions import db
from models.pack import Pack
from models.book import Book

##
# @brief Table for storing the relationship between packs and books.
#
class Book_pack(db.Model):
    __tablename__='book_pack'
    pack_id=db.Column(db.ForeignKey(Pack.id),primary_key=True)
    book_id=db.Column(db.ForeignKey(Book.id),primary_key=True)
    