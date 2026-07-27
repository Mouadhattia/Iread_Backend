## @file
# @class SchoolSeatActivation
from datetime import datetime

from extensions import db
from models.pack import Pack
from models.school_subscription import SchoolSubscription
from models.shcool import Shcool
from models.user import User


##
# @brief The seat ledger: one row each time a student becomes "activated"
# against a school, closed off when that seat is released.
#
# An activated student is one who has joined a pack. That could be derived on
# the fly by joining Follow_pack -> Pack -> Shcool (plus SchoolPackInstance for
# global packs), but deriving it has two problems this table solves: the query
# is a multi-way join run on every dashboard load, and -- more importantly --
# a derived count has no history, so nobody can answer "how many seats did we
# bill this school for in March?" or audit why a seat was consumed.
#
# Seats are reclaimable (a product decision): `released_at` is stamped when the
# student leaves the school or drops their last school-attributable pack, and
# the seat returns to the pool. Rows are never deleted -- a re-activated
# student gets a new row, preserving the full history.
#
# `subscription_id` is nullable on purpose: activations that predate a school's
# first contract (including everything the backfill imports) still need to be
# counted, and get attached to the contract once one exists.
class SchoolSeatActivation(db.Model):
    __tablename__ = 'school_seat_activation'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey(SchoolSubscription.id), nullable=True, index=True)
    first_pack_id = db.Column(db.Integer, db.ForeignKey(Pack.id), nullable=True)

    activated_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    released_at = db.Column(db.DateTime, nullable=True)
    release_reason = db.Column(db.String(120), nullable=True)
    source = db.Column(db.String(40), nullable=True)  # reader_code | parent_code | admin_assign | backfill

    school = db.relationship(Shcool, backref='seat_activations')
    user = db.relationship(User, backref=db.backref('seat_activations', cascade='all, delete-orphan'))
    subscription = db.relationship(SchoolSubscription, backref='seat_activations')

    __table_args__ = (
        # The hot path is "how many open seats does this school have" and
        # "does this student already hold an open seat here".
        db.Index('ix_seat_activation_school_open', 'shcool_id', 'released_at'),
        db.Index('ix_seat_activation_school_user', 'shcool_id', 'user_id', 'released_at'),
    )

    def __repr__(self):
        return '<SchoolSeatActivation school=%s user=%s%s>' % (
            self.shcool_id, self.user_id, '' if self.released_at is None else ' released'
        )
