## @file
# @class ContractPlan
from datetime import datetime

from extensions import db


##
# @brief A super-admin-managed pricing preset for school contracts.
#
# These are presets, not a closed set: SchoolSubscription copies the seat cap
# and price onto itself at creation time, so editing a plan later never
# silently reprices an existing contract, and a bespoke deal can be created
# with no plan at all (subscription.plan_id = NULL).
#
# Money is stored in integer cents -- never floats. Pack.price is a legacy
# Float and is a good illustration of why: it cannot represent 19.99 exactly.
class ContractPlan(db.Model):
    __tablename__ = 'contract_plan'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    min_seats = db.Column(db.Integer, nullable=False)
    max_seats = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='EUR')
    term_months = db.Column(db.Integer, nullable=False, default=12)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return '<ContractPlan %s %s-%s seats>' % (self.code, self.min_seats, self.max_seats)
