## @file 
#@class Pack

from extensions import db
from enum import Enum

class StatusEnum(Enum):
   
    KID = 'kid'
    TEENAGER = 'teenager'
    ADULT = 'adult'



##
# @brief Table for storing information about packs.
#
class Pack(db.Model):
    __tablename__="pack"
    id=db.Column(db.Integer,primary_key=True)
    token=db.Column(db.String(36),unique=True)
    title=db.Column(db.String(45),nullable=False)
    level=db.Column(db.String(45),nullable=True)
    desc=db.Column(db.String(200))
    age=db.Column(db.Enum(StatusEnum),nullable=True)
    img=db.Column(db.String(100),nullable=True)
    book_number=db.Column(db.Integer,default=0)
    price=db.Column(db.Float,default=0)
    discount=db.Column(db.Float,default=0)
    
    def __repr__(self):
        return '< Pack %s >' %self.title