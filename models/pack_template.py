## @file 
#@class Pack_template
from extensions import db
from enum import Enum
from models.shcool import Shcool


class TemplateType(Enum):
   
    A = 'A'
    B = 'B'
    C = 'C'
    D= 'D'

##
# @brief Table for storing information about template.
#
class Pack_template(db.Model):
    __tablename__="pack_template"
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(45),nullable=False)
    level=db.Column(db.String(45),nullable=True)
    desc=db.Column(db.String(1000))
    age=db.Column(db.String(45),nullable=True)
    img=db.Column(db.String(200),nullable=True)
    faq = db.Column(db.JSON, nullable=True)
    book_pack_ids =db.Column(db.JSON, nullable=True)
    template_type=db.Column(db.Enum(TemplateType),default='A')
    
    

 
    def __repr__(self):
        return '< Pack_template %s >' %self.title