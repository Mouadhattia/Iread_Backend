## @file 
#@class Follow_session
from models.user import User
from models.session import Session
from extensions import db


##
# @brief Table for storing the relationship between users and sessions.
#
class Follow_session(db.Model):
    __tablename__='follow_session'
    user_id=db.Column(db.ForeignKey(User.id),primary_key=True)
    session_id=db.Column(db.ForeignKey(Session.id),primary_key=True)
    approved=db.Column(db.Boolean,default=False)
    presence = db.Column(db.Boolean,default=False)
    
    user = db.relationship(User, backref=db.backref('follow_session', cascade='all, delete-orphan'))
    def __repr__(self):
        return '< Follow_session %s >' %self.session_id
