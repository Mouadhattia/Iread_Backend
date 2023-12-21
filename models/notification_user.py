## @file 
#@class Session
from extensions import db
from models.user import User

##
# @brief Table for storing information about sessions.
#
class Notification_user(db.Model):
    __tablename__="notification_user"
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.ForeignKey(User.id))
    notification_id=db.Column(db.String(50))

    def __repr__(self):
        return '< Notification_user %s >' %self.notification_id