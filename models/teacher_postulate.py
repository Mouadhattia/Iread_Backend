## @file 
#@class Contain
from extensions import db
from models.user import Reader

class Teacher_postulate(db.Model):
    __tablename__='teacher_postulate'
    id=db.Column(db.Integer,db.ForeignKey(Reader.id),primary_key=True)
    description=db.Column(db.String(400),nullable=False)
    study_level=db.Column(db.Text,nullable=False)
    selected=db.Column(db.Boolean,nullable=False,default=False)