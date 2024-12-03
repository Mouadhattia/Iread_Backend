## @file 
#@class Pack

from extensions import db
from enum import Enum
from models.shcool import Shcool

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
    desc=db.Column(db.String(1000))
    age=db.Column(db.Enum(StatusEnum),nullable=True)
    img=db.Column(db.String(200),nullable=True)
    book_number=db.Column(db.Integer,default=0)
    price=db.Column(db.Float,default=0)
    discount=db.Column(db.Float,default=0)
    faq = db.Column(db.JSON, nullable=True)
    product_id_invoicing_api =db.Column(db.String(100), nullable=True)
    duration =db.Column(db.Float,default=0)
    # Define the relationship with Code and set the cascade option
    codes = db.relationship('Code', backref='pack', cascade='all, delete-orphan')
    shcool_id = db.Column(db.ForeignKey(Shcool.id))
    public = db.Column(db.Boolean,default=False)
    
    def __repr__(self):
        return '< Pack %s >' %self.title