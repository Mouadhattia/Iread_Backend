## @file
# @brief Transactional emails for school licence billing.
#
# These sit *alongside* Stripe's own invoice emails rather than replacing them.
# Stripe keeps ownership of the invoice document, the payment page and the
# automatic overdue reminders; these add the context Stripe cannot know -- which
# plan, how many reader places, which term -- and keep the school hearing from
# iRead rather than only from a payment processor.
#
# Every send is best-effort. An SMTP failure must never roll back a raised
# invoice or a processed webhook: the money and the database state are the
# things that must be right, and a missing email can be re-sent.
from datetime import datetime

from apps.emailer import get_super_admin_emails, send_html_email, unique_addresses
from config import ConfigClass
from extensions import db
from models.user import User
from models.user_shcool import User_shcool


##
# @brief Format integer cents for display in an email.
#
# Always two decimal places. Trimming a trailing zero turns EUR 19.50 into
# "€19.5", which on a receipt reads as a typo at best and a different figure at
# worst -- money is written to the minor unit or not at all.
def format_money(cents, currency='EUR'):
    if cents is None:
        return '—'
    symbol = {'EUR': '€', 'GBP': '£', 'USD': '$'}.get((currency or '').upper(), '')
    amount = '{:,.2f}'.format(cents / 100)
    return f'{symbol}{amount}' if symbol else f'{amount} {currency}'


def format_date(value):
    if not value:
        return None
    try:
        return value.strftime('%d %b %Y')
    except AttributeError:
        return str(value)


##
# @brief The customer block on a receipt: who this was billed to.
#
# Falls back to the school's own name when no billing profile has been filled
# in, so the receipt is never addressed to nobody.
def billing_address_lines(school, billing_profile=None):
    if billing_profile is None:
        return [school.name] if school and school.name else []

    lines = [
        billing_profile.legal_name or (school.name if school else None),
        billing_profile.address_line1,
        billing_profile.address_line2,
        ' '.join(part for part in [billing_profile.postal_code, billing_profile.city] if part) or None,
        billing_profile.region,
        (billing_profile.country or '').upper() or None,
    ]
    return [line for line in lines if line]


##
# @brief Send one HTML email, swallowing failures.
# @return True if it was handed to the mail server.
def send_email(subject, recipients, template, **context):
    return send_html_email(
        subject, recipients, template, category='Billing email', **context
    )


##
# @brief Email addresses of a school's own admins.
def get_school_admin_emails(school_id):
    if not school_id:
        return []
    return [
        email for (email,) in
        db.session.query(User.email)
        .join(User_shcool, User_shcool.user_id == User.id)
        .filter(User_shcool.shcool_id == school_id, User.type == 'admin')
        .all()
        if email
    ]


##
# @brief Recipients for a school's invoice: the billing contact plus the
# school's admins, de-duplicated. The billing contact is often a bursar who
# has no iRead login at all, which is why it cannot just be the admins.
def get_invoice_recipients(school_id, billing_profile=None):
    recipients = []
    if billing_profile is not None and billing_profile.billing_email:
        recipients.append(billing_profile.billing_email)
    recipients.extend(get_school_admin_emails(school_id))
    return unique_addresses(recipients)


##
# @brief Tell the school their licence invoice is ready to pay.
def send_invoice_issued_email(school, invoice, subscription, billing_profile=None):
    return send_email(
        subject='Your iRead licence invoice (%s)' % (invoice.number or invoice.id),
        recipients=get_invoice_recipients(school.id, billing_profile),
        template='billing_invoice_issued.html',
        school_name=school.name,
        invoice_number=invoice.number or ('#%s' % invoice.id),
        plan_name=(subscription.plan.name if subscription and subscription.plan else 'Reading licence'),
        seats=invoice.seats or (subscription.seat_limit if subscription else '—'),
        term_start=format_date(subscription.term_start if subscription else None),
        term_end=format_date(subscription.term_end if subscription else None),
        total=format_money(invoice.total_cents, invoice.currency),
        due_date=format_date(invoice.due_at),
        hosted_invoice_url=invoice.hosted_invoice_url,
        vat_registered=bool(ConfigClass.PLATFORM_VAT_REGISTERED),
    )


##
# @brief The school's receipt for a paid licence invoice.
#
# This is the document a finance office files, so it carries what a receipt is
# expected to carry anywhere: what was bought, for whom, over what period, the
# net/tax/gross split, the date the money was taken, and a link to the PDF.
# Stripe's own copy is authoritative and is linked rather than reproduced --
# but a school should not have to log in to a payment processor to find out
# what it paid for.
def send_payment_received_email(school, invoice, subscription, billing_profile=None):
    seats = invoice.seats or (subscription.seat_limit if subscription else None)
    currency = invoice.currency or ConfigClass.BILLING_CURRENCY
    unit_price_cents = subscription.unit_price_cents if subscription else None
    vat_registered = bool(ConfigClass.PLATFORM_VAT_REGISTERED)

    return send_email(
        subject='Receipt for your iRead licence — %s' % (invoice.number or ('#%s' % invoice.id)),
        recipients=get_invoice_recipients(school.id, billing_profile),
        template='billing_payment_received.html',
        school_name=school.name,
        billed_to=billing_address_lines(school, billing_profile),
        customer_vat_number=(billing_profile.vat_number if billing_profile else None),
        purchase_order_ref=(billing_profile.purchase_order_ref if billing_profile else None),

        invoice_number=invoice.number or ('#%s' % invoice.id),
        paid_on=format_date(invoice.paid_at) or format_date(datetime.now()),

        plan_name=(subscription.plan.name if subscription and subscription.plan else 'Reading licence'),
        seats=seats if seats is not None else '—',
        unit_price=format_money(unit_price_cents, currency) if unit_price_cents else None,
        term_start=format_date(subscription.term_start if subscription else None),
        term_end=format_date(subscription.term_end if subscription else None),

        subtotal=format_money(invoice.subtotal_cents, currency),
        tax=format_money(invoice.tax_cents, currency),
        total=format_money(invoice.total_cents, currency),
        show_tax_line=bool(vat_registered or invoice.tax_cents),
        vat_registered=vat_registered,
        no_vat_note=ConfigClass.INVOICE_NO_VAT_NOTE,

        # Stripe stops exposing invoice_pdf on some invoice states; the hosted
        # page always works and offers the same download, so it is the fallback
        # rather than showing the school no way to get its receipt at all.
        receipt_url=invoice.invoice_pdf or invoice.hosted_invoice_url,
        receipt_is_pdf=bool(invoice.invoice_pdf),

        supplier_name=ConfigClass.PLATFORM_LEGAL_NAME,
        supplier_address=ConfigClass.PLATFORM_ADDRESS,
        supplier_company_number=ConfigClass.PLATFORM_COMPANY_NUMBER,
        supplier_vat_number=ConfigClass.PLATFORM_VAT_NUMBER if vat_registered else None,
    )


##
# @brief Tell the platform's own super admins that money has landed.
def send_payment_received_internal_email(school, invoice, subscription, seats_used=None):
    admin_url = (ConfigClass.ADMIN_FRONT_URL or '').rstrip('/')
    return send_email(
        subject='Licence payment received — %s' % school.name,
        recipients=get_super_admin_emails(),
        template='billing_payment_received_internal.html',
        school_name=school.name,
        invoice_number=invoice.number or ('#%s' % invoice.id),
        total=format_money(invoice.total_cents, invoice.currency),
        seats=invoice.seats or (subscription.seat_limit if subscription else '—'),
        term_start=format_date(subscription.term_start if subscription else None),
        term_end=format_date(subscription.term_end if subscription else None),
        seats_used=seats_used if seats_used is not None else '—',
        contracts_url=f'{admin_url}/super-admin/subscriptions' if admin_url else None,
    )
