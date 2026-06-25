## @file
# @class GlobalTeacher
from datetime import datetime

from extensions import db
from models.user import User


class GlobalTeacher(db.Model):
    __tablename__ = 'global_teacher'
    teacher_id = db.Column(db.Integer, db.ForeignKey(User.id), primary_key=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    teacher = db.relationship(User, foreign_keys=[teacher_id], backref='global_teacher_record')
    creator = db.relationship(User, foreign_keys=[created_by], backref='created_global_teachers')

    def __repr__(self):
        return '<GlobalTeacher teacher=%s>' % self.teacher_id
