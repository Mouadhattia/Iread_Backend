## @file 
#@class Follow_pack
from extensions import db
from models.user import User


##
# @brief Table for storing the relationship between users and packs they follow.
#
class Profile(db.Model):
    __tablename__='profile'
    user_id=db.Column(db.ForeignKey(User.id),primary_key=True)
    first_name = db.Column(db.String(300), nullable=True)
    last_name = db.Column(db.String(300),  nullable=True)
    phone = db.Column(db.String(300),  nullable=True)
    birth_day = db.Column(db.Date,nullable=True)
    address_1 = db.Column(db.String(300), nullable=True)
    address_2 = db.Column(db.String(300),  nullable=True)
    state = db.Column(db.String(300),  nullable=True)
    country = db.Column(db.String(300),  nullable=True)

    
    user = db.relationship(User, backref=db.backref('profile', cascade='all, delete-orphan'))
    def __repr__(self):
        return '< profile %s >' %self.user_id