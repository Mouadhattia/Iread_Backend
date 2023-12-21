## @file 
#@class Session
from extensions import db
from models.session import Session
from datetime import datetime

##
# @brief Table for storing information about sessions.
#
class Session_quiz(db.Model):
    __tablename__="session_quiz"
    id=db.Column(db.Integer,primary_key=True)
    session_id=db.Column(db.ForeignKey(Session.id))
    quiz_token=db.Column(db.String(50))
    release_date=db.Column(db.Date,nullable=False,default=datetime.now())
    teacher= db.Column(db.Integer,nullable=True)
    def __repr__(self):
        return '< Session_quiz %s >' %self.date