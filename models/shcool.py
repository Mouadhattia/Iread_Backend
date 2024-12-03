## @file 
#@class Shcool
from extensions import db


##
# @brief Table for storing the relationship between users and packs they follow.
#
class Shcool(db.Model):
    __tablename__='shcool'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    def __repr__(self):
        return '< shcool %s >' %self.id

