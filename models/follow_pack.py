## @file 
#@class Follow_pack
from extensions import db
from models.user import User
from models.pack import Pack

##
# @brief Table for storing the relationship between users and packs they follow.
#
class Follow_pack(db.Model):
    __tablename__='follow_pack'
    user_id=db.Column(db.ForeignKey(User.id),primary_key=True)
    pack_id=db.Column(db.ForeignKey(Pack.id),primary_key=True)
    approved=db.Column(db.Boolean,default=False)
    
    def __repr__(self):
        return '< follow_pack %s >' %self.pack_id

