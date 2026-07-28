## @file
# @brief Transactional emails for a school's application to join iRead.
#
# Signing up on the admin dashboard does not create a usable account: the
# school and its first admin are written straight away, but `approved` is False
# until a super admin reviews them, and sign-in is refused until then. Without
# an acknowledgement the applicant sees a success screen, gets no mail, and has
# no way to tell a queued application apart from a form that silently failed --
# so the "we have your request" email is the only thing standing between a
# pending review and a support ticket.
#
# The internal counterpart matters just as much: nothing else tells the
# platform side that an application is waiting. A promise that a request will
# be reviewed is only true if somebody is told to review it.
#
# Every send is best-effort. The account is already committed by the time these
# run; a mail failure must never turn a successful signup into a 500.
import logging
from datetime import datetime

from apps.emailer import get_super_admin_emails, send_html_email
from config import ConfigClass

CATEGORY = 'School signup email'


##
# @brief The name to greet an applicant by.
def _display_name(admin):
    if admin is None:
        return None
    return (getattr(admin, 'display_name', None) or admin.username or '').strip() or None


def _admin_url(path=''):
    base = (ConfigClass.ADMIN_FRONT_URL or '').rstrip('/')
    return f'{base}{path}' if base else None


##
# @brief Acknowledge a school's application to the person who submitted it.
#
# @param admin  The pending Admin row (already committed).
# @param school The Shcool created alongside it.
# @return True if the message was handed to the mail server.
def send_signup_received_email(admin, school):
    if admin is None or not (admin.email or '').strip():
        return False

    return send_html_email(
        subject='We have received your iRead school registration',
        recipients=[admin.email],
        template='school_admin_signup_received.html',
        category=CATEGORY,
        admin_name=_display_name(admin),
        admin_email=admin.email,
        school_name=(school.name if school else None) or 'your school',
        submitted_at=datetime.now().strftime('%d %b %Y'),
        sign_in_url=_admin_url('/'),
        support_email=ConfigClass.SUPPORT_EMAIL,
    )


##
# @brief Tell every super admin that an application is waiting on them.
def send_signup_pending_review_email(admin, school):
    recipients = get_super_admin_emails()
    if not recipients:
        return False

    return send_html_email(
        subject='New school registration awaiting review — %s' % (
            (school.name if school else None) or 'Unnamed school'),
        recipients=recipients,
        template='school_admin_signup_internal.html',
        category=CATEGORY,
        admin_name=_display_name(admin),
        admin_email=(admin.email if admin else None),
        school_name=(school.name if school else None) or 'Unnamed school',
        submitted_at=datetime.now().strftime('%d %b %Y, %H:%M'),
        review_url=_admin_url('/super-admin/users'),
    )


##
# @brief Both sides of a school signup, neither able to break the other.
# @return dict of which messages were handed to the mail server.
def send_school_admin_signup_emails(admin, school):
    results = {}
    for key, send in (
        ('applicant', lambda: send_signup_received_email(admin, school)),
        ('super_admins', lambda: send_signup_pending_review_email(admin, school)),
    ):
        try:
            results[key] = send()
        except Exception as error:
            # send_html_email already swallows and logs SMTP failures; this
            # catches anything raised before it, such as a recipient lookup
            # hitting the database at a bad moment.
            logging.error('School signup email (%s) failed: %s', key, error, exc_info=True)
            results[key] = False
    return results
