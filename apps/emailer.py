## @file
# @brief One place to render and send a templated HTML email.
#
# Extracted from apps/billing_email.py once account-lifecycle mail (school
# offboarding, and anything that follows) needed the same behaviour: render a
# Jinja template that extends templates/email_base.html, send it as HTML, and
# never let an SMTP failure escape into the caller's transaction.
#
# Every send is best-effort by design. The database state is the thing that
# must be right; a missing email can always be re-sent.
import logging
from datetime import datetime

from flask import render_template

from config import ConfigClass
from extensions import db, mail

try:
    from flask_mail import Message
except ImportError:  # pragma: no cover - flask_mail is a core dependency
    Message = None


##
# @brief Render `template` and send it to `recipients` as an HTML email.
# @param category Human label used only in log lines, so a failure is
#        attributable to the feature that raised it ("Billing email", ...).
# @return True if the message was handed to the mail server.
def send_html_email(subject, recipients, template, category='Email', **context):
    recipients = [address for address in (recipients or []) if address]
    if not recipients:
        logging.warning('%s "%s" had no recipients; skipped.', category, subject)
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
        logging.error('%s "%s" failed: %s', category, subject, error, exc_info=True)
        return False


##
# @brief De-duplicate a recipient list case-insensitively, preserving order.
def unique_addresses(addresses):
    seen, unique = set(), []
    for address in addresses or []:
        if not address:
            continue
        key = address.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(address)
    return unique


##
# @brief Email addresses of every super admin -- the platform side of anything
# that needs a human at iRead to act (a payment landing, a school applying).
#
# Lives here rather than in one feature's module because more than one feature
# now needs it; User is imported lazily so this transport module stays free of
# import-order constraints on the model graph.
def get_super_admin_emails():
    from models.user import User
    return unique_addresses([
        email for (email,) in
        db.session.query(User.email).filter(User.type == 'super_admin').all()
    ])
