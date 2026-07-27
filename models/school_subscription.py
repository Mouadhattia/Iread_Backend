## @file
# @class SchoolSubscription
from datetime import datetime

from extensions import db
from models.contract_plan import ContractPlan
from models.shcool import Shcool
from models.user import User

# Lifecycle. Kept as plain strings rather than a db.Enum because the Pack
# model already demonstrates the trap: two different models in this codebase
# both define a `StatusEnum`, and importing the wrong one is a live-bug class
# (see the pack-detail StatusEnum collision fixed in the parent-dashboard work).
STATUS_DRAFT = 'draft'                      # being prepared by a super admin
STATUS_PENDING_PAYMENT = 'pending_payment'  # invoice issued, not yet paid
STATUS_ACTIVE = 'active'                    # paid and inside its term
STATUS_GRACE = 'grace'                      # term ended / payment failed, inside the 30-day grace
STATUS_EXPIRED = 'expired'                  # grace elapsed -- read-only, no new activations
STATUS_CANCELLED = 'cancelled'              # ended early

# Statuses under which a school may still activate new students.
CONSUMING_STATUSES = (STATUS_PENDING_PAYMENT, STATUS_ACTIVE, STATUS_GRACE)

ALL_SUBSCRIPTION_STATUSES = (
    STATUS_DRAFT, STATUS_PENDING_PAYMENT, STATUS_ACTIVE,
    STATUS_GRACE, STATUS_EXPIRED, STATUS_CANCELLED,
)


##
# @brief One school's contract for one term.
#
# Seat cap and price are copied from the ContractPlan rather than referenced,
# so the contract is a historical record that a later plan edit cannot alter.
# A school accumulates one row per term; only one should be in a CONSUMING_
# STATUSES state at a time, which is enforced in the service layer rather than
# by a DB constraint because the history rows must remain.
class SchoolSubscription(db.Model):
    __tablename__ = 'school_subscription'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey(ContractPlan.id), nullable=True)

    seat_limit = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default='EUR')

    term_start = db.Column(db.Date, nullable=False)
    term_end = db.Column(db.Date, nullable=False)
    grace_days = db.Column(db.Integer, nullable=False, default=30)

    status = db.Column(db.String(30), nullable=False, default=STATUS_DRAFT, index=True)
    auto_renew = db.Column(db.Boolean, nullable=False, default=False)

    stripe_customer_id = db.Column(db.String(120), nullable=True, index=True)
    notes = db.Column(db.String(1000), nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='subscriptions')
    plan = db.relationship(ContractPlan, backref='subscriptions')

    ##
    # @brief Whether this contract still permits new student activations.
    def is_consuming(self):
        return self.status in CONSUMING_STATUSES

    def __repr__(self):
        return '<SchoolSubscription school=%s seats=%s %s>' % (self.shcool_id, self.seat_limit, self.status)
