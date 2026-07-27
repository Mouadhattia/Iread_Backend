## @file
# @class SchoolBillingProfile
from datetime import datetime

from extensions import db
from models.shcool import Shcool


##
# @brief Billing identity for a school -- who the invoice is actually made out
# to, which is not the same thing as the Shcool row.
#
# Shcool itself carries only name/is_active/suspension fields, so none of the
# details Stripe needs to create a Customer (or that an EU VAT invoice is
# legally required to display) existed anywhere before this table.
#
# `country` is an ISO-3166-1 alpha-2 code and drives VAT treatment: iRead is
# an Irish company, so IE schools are charged Irish VAT while VAT-registered
# businesses elsewhere in the EU are reverse-charged. `vat_number` is what
# makes that determination possible -- without it a customer is treated as
# non-business and charged VAT normally.
class SchoolBillingProfile(db.Model):
    __tablename__ = 'school_billing_profile'
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, unique=True, index=True)
    legal_name = db.Column(db.String(255), nullable=True)
    billing_email = db.Column(db.String(255), nullable=True)
    billing_phone = db.Column(db.String(50), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    region = db.Column(db.String(120), nullable=True)
    postal_code = db.Column(db.String(30), nullable=True)
    country = db.Column(db.String(2), nullable=True)
    vat_number = db.Column(db.String(40), nullable=True)
    purchase_order_ref = db.Column(db.String(120), nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref=db.backref('billing_profile', uselist=False))

    def __repr__(self):
        return '<SchoolBillingProfile school=%s>' % self.shcool_id
