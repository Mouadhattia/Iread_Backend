# @file
# @class Contain
from extensions import db            
from models.pack import Pack
from enum import Enum
from models.user import User

class StatusEnum(Enum):
    ACTIVE = 'active'
    USED = 'used'
    PENDING = 'pending'

##
# @brief Table for storing the relationship between packs and books.
#
class Code(db.Model):
    __tablename__ = 'code'
    id = db.Column(db.Integer, primary_key=True)
    pack_id = db.Column(db.Integer, db.ForeignKey(Pack.id)) 
    code = db.Column(db.String(64), nullable=False, unique=True)
    status = db.Column(db.Enum(StatusEnum), nullable=False, default=StatusEnum.ACTIVE)
    user_id=db.Column(db.ForeignKey(User.id), nullable=True,)

    def __repr__(self):
        return '<Code %s>' % self.code  # Fixed the __repr__ method to use 'code' instead of 'date'
Pack.codes = db.relationship('Code', backref='pack', cascade='all, delete-orphan')