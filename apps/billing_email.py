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
import logging
from datetime import datetime

from flask import render_template

from config import ConfigClass
from extensions import mail, db
from models.user import User
from models.user_shcool import User_shcool

try:
    from flask_mail import Message
except ImportError:  # pragma: no cover - flask_mail is a core dependency
    Message = None


##
# @brief Format integer cents for display in an email.
def format_money(cents, currency='EUR'):
    if cents is None:
        return '—'
    symbol = {'EUR': '€', 'GBP': '£', 'USD': '$'}.get((currency or '').upper(), '')
    amount = '{:,.2f}'.format(cents / 100).rstrip('0').rstrip('.')
    return f'{symbol}{amount}' if symbol else f'{amount} {currency}'


def format_date(value):
    if not value:
        return None
    try:
        return value.strftime('%d %b %Y')
    except AttributeError:
        return str(value)


##
# @brief Send one HTML email, swallowing failures.
# @return True if it was handed to the mail server.
def send_email(subject, recipients, template, **context):
    recipients = [address for address in (recipients or []) if address]
    if not recipients:
        logging.warning('Billing email "%s" had no recipients; skipped.', subject)
        return False
    if Message is None:
        logging.error('flask_mail is unavailable; cannot send "%s".', subject)
        return False

    try:
        html = render_template(template, current_year=datetime.now().year, **context)
        message = Message(subject, recipients=recipients, sender=ConfigClass.MAIL_USERNAME)
        message.html = html
        mail.send(message)
        return True
    except Exception as error:
        logging.error('Billing email "%s" failed: %s', subject, error, exc_info=True)
        return False


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
# @brief Email addresses of every super admin -- the platform side.
def get_super_admin_emails():
    return [
        email for (email,) in
        db.session.query(User.email).filter(User.type == 'super_admin').all()
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

    seen, unique = set(), []
    for address in recipients:
        key = address.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(address)
    return unique


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
# @brief Confirm receipt to the school.
def send_payment_received_email(school, invoice, subscription, billing_profile=None):
    return send_email(
        subject='Payment received — your iRead licence is active',
        recipients=get_invoice_recipients(school.id, billing_profile),
        template='billing_payment_received.html',
        school_name=school.name,
        invoice_number=invoice.number or ('#%s' % invoice.id),
        total=format_money(invoice.total_cents, invoice.currency),
        seats=invoice.seats or (subscription.seat_limit if subscription else '—'),
        term_start=format_date(subscription.term_start if subscription else None),
        term_end=format_date(subscription.term_end if subscription else None),
        invoice_pdf=invoice.invoice_pdf,
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
