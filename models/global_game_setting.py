## @file
# @class GlobalGameSetting
from datetime import datetime

from extensions import db


class GlobalGameSetting(db.Model):
    """Platform-wide timer/hint rules for the global game schedule.

    Schools playing a global book in `global` mode are ranked against readers
    from every other school, so they all have to play under the same clock and
    hint budget -- their own `SchoolGameSetting` is ignored there. Schools in
    `from_start` mode rank only against themselves, so their own setting still
    wins and this acts as the fallback when they never configured one.
    """

    __tablename__ = 'global_game_setting'

    id = db.Column(db.Integer, primary_key=True)
    game_type = db.Column(db.String(32), nullable=False, unique=True)
    timer_seconds = db.Column(db.Integer, nullable=False)
    timer_enabled = db.Column(db.Boolean, nullable=False, default=True)
    max_hints = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.CheckConstraint('timer_seconds > 0', name='ck_global_game_setting_timer_positive'),
        db.CheckConstraint('max_hints IS NULL OR max_hints >= 0', name='ck_global_game_setting_max_hints_non_negative'),
    )

    def __repr__(self):
        return '<GlobalGameSetting game=%s>' % self.game_type
