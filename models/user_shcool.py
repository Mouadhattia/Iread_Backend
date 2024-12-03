## @file 
#@class user_shcool
from extensions import db
from models.user import User
from models.shcool import Shcool

##
# @brief Table for storing the relationship between users and packs they follow.
#
class User_shcool(db.Model):
    __tablename__='user_shcool'
    user_id=db.Column(db.ForeignKey(User.id),primary_key=True)
    shcool_id=db.Column(db.ForeignKey(Shcool.id),primary_key=True)

    user = db.relationship(User, backref=db.backref('user_shcool', cascade='all, delete-orphan'))
    def __repr__(self):
        return '< user_shcool %s >' %self.pack_id

