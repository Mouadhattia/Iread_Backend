## @file
# @class SchoolPackInstance
from datetime import datetime

from extensions import db
from models.pack import Pack
from models.shcool import Shcool
from models.user import User


class SchoolPackInstance(db.Model):
    __tablename__ = 'school_pack_instance'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    pack_id = db.Column(db.Integer, db.ForeignKey(Pack.id), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    # Per-school publish flag + display-name override -- a global pack's
    # `Pack.public`/`Pack.title` are shared across every school that has
    # joined it (super-admin/B2C scope), so a school's own "publish this to
    # my readers" and "rename it for my school" choices need their own
    # per-instance fields instead of mutating the shared Pack row.
    public = db.Column(db.Boolean, nullable=False, default=False)
    display_name = db.Column(db.String(255), nullable=True)
    # How this school reads the super admin's master game schedule for the
    # pack's books. 'from_start' replays the schedule from its first day,
    # anchored on `games_anchor_date`, so each school runs its own offset and
    # can only be ranked against itself. 'global' follows the master calendar
    # in real time -- every school plays the same words on the same day, which
    # is what makes a cross-school ranking meaningful.
    games_mode = db.Column(db.String(16), nullable=False, default='from_start')
    # Day 1 of the replay in 'from_start' mode: set when the school first
    # publishes the pack, never moved afterwards. Ignored in 'global' mode.
    games_anchor_date = db.Column(db.Date, nullable=True)
    # Whether this school's readers appear by name on the cross-school
    # leaderboard. Opting out only hides them from other schools -- their own
    # readers still see their true global rank.
    global_leaderboard_opt_in = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    pack = db.relationship(Pack, backref='school_instances')
    school = db.relationship(Shcool, backref='global_pack_instances')
    creator = db.relationship(User, backref='created_school_pack_instances')

    __table_args__ = (
        db.UniqueConstraint('shcool_id', 'pack_id', name='uq_school_global_pack'),
    )

    def __repr__(self):
        return '<SchoolPackInstance school=%s pack=%s>' % (self.shcool_id, self.pack_id)
