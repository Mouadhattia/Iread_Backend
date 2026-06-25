## @file 
#@class Book
from extensions import db
from sqlalchemy import UniqueConstraint
from models.shcool import Shcool


##
# @brief Table for storing books and their details.
#
class Book(db.Model):
    __tablename__="book"
    id=db.Column(db.Integer,primary_key=True)
    token=db.Column(db.String(36),unique=True)
    title=db.Column(db.String(100))
    img=db.Column(db.String(200))
    desc=db.Column(db.String(1000))
    author=db.Column(db.String(100),nullable=False)
    img=db.Column(db.String(300),nullable=True)
    release_date=db.Column(db.Date,nullable=True)
    page_number=db.Column(db.Integer,nullable=True)
    category=db.Column(db.String(100),nullable=True)
    neo4j_id=db.Column(db.Integer,nullable=True) #False
    shcool_id = db.Column(db.ForeignKey(Shcool.id), nullable=True)
    is_platform_book = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    


    __table_args__ = (
        UniqueConstraint('title', 'author', name='_title_author_unique'),
    )


    ##
    # @brief Returns a string representation of the `Book` object.
    # @return: A string representation of the `Book` object, containing the book's title.
    #
    def __repr__(self):
        return '< Book %s >' %self.title
