## @file
# @class SchoolGameSetting
from datetime import datetime

from extensions import db
from models.shcool import Shcool


class SchoolGameSetting(db.Model):
    __tablename__ = 'school_game_setting'

    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    game_type = db.Column(db.String(32), nullable=False)
    timer_seconds = db.Column(db.Integer, nullable=False)
    timer_enabled = db.Column(db.Boolean, nullable=False, default=True)
    max_hints = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='game_settings')

    __table_args__ = (
        db.UniqueConstraint('shcool_id', 'game_type', name='uq_school_game_setting'),
        db.CheckConstraint('timer_seconds > 0', name='ck_school_game_setting_timer_positive'),
        db.CheckConstraint('max_hints IS NULL OR max_hints >= 0', name='ck_school_game_setting_max_hints_non_negative'),
    )

    def __repr__(self):
        return '<SchoolGameSetting school=%s game=%s>' % (self.shcool_id, self.game_type)
