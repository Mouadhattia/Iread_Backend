## @file
# @class SchoolInvoice
from datetime import datetime

from extensions import db
from models.school_subscription import SchoolSubscription
from models.shcool import Shcool
from models.user import User

# Mirrors Stripe's own invoice statuses so the webhook can map 1:1 without a
# translation table.
INVOICE_DRAFT = 'draft'
INVOICE_OPEN = 'open'                  # finalized and sent, awaiting payment
INVOICE_PAID = 'paid'
INVOICE_VOID = 'void'
INVOICE_UNCOLLECTIBLE = 'uncollectible'


##
# @brief A local mirror of a Stripe invoice for a school contract.
#
# Stripe remains the source of truth for payment state -- this row exists so
# the dashboards can list and filter invoices without a synchronous API call
# per page load, and so invoice history survives independently of the Stripe
# account.
#
# Deliberately NOT reusing the legacy invoicing microservice
# (invoicing.iread.education): that service is B2C, models a "client" per
# reader/parent and a "product" per pack, and has no concept of a school.
class SchoolInvoice(db.Model):
    __tablename__ = 'school_invoice'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey(SchoolSubscription.id), nullable=True, index=True)

    number = db.Column(db.String(60), nullable=True)
    status = db.Column(db.String(30), nullable=False, default=INVOICE_DRAFT, index=True)

    # subtotal + tax = total. Stored separately because an EU VAT invoice is
    # legally required to show the tax amount as its own line.
    subtotal_cents = db.Column(db.Integer, nullable=False, default=0)
    tax_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default='EUR')

    seats = db.Column(db.Integer, nullable=True)
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)

    stripe_invoice_id = db.Column(db.String(120), nullable=True, unique=True, index=True)
    hosted_invoice_url = db.Column(db.String(500), nullable=True)
    invoice_pdf = db.Column(db.String(500), nullable=True)

    issued_at = db.Column(db.DateTime, nullable=True)
    due_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='invoices')
    subscription = db.relationship(SchoolSubscription, backref='invoices')

    def __repr__(self):
        return '<SchoolInvoice %s school=%s %s>' % (self.number or self.id, self.shcool_id, self.status)
