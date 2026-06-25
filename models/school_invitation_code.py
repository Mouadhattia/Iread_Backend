## @file
# @class SchoolInvitationCode
from datetime import datetime

from extensions import db
from models.shcool import Shcool
from models.user import User


##
# @brief School invitation codes that let users join a school.
#
class SchoolInvitationCode(db.Model):
    __tablename__ = 'school_invitation_code'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    code = db.Column(db.String(64), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    school = db.relationship(Shcool, backref=db.backref('school_invitation_codes', cascade='all, delete-orphan'))
    creator = db.relationship(User, backref='created_school_invitation_codes')

    def __repr__(self):
        return '<SchoolInvitationCode %s>' % self.code
