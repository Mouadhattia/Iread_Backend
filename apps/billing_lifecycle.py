## @file
# @brief Time-driven contract transitions and reminders.
#
# Contracts age whether or not anyone logs in, so this runs on a schedule
# rather than off a request. It is deliberately idempotent -- running it twice
# in a day changes nothing the second time -- because the safest cron is one
# that can be re-run after a failure without thought.
#
# The lifecycle, and the reasoning behind it:
#
#   active ──(term_end passes)──▶ grace ──(grace_days elapse)──▶ expired
#
# Grace exists so a late renewal never abruptly cuts children off mid-term. In
# grace the school keeps activating students normally; only when it expires do
# new activations stop, and even then existing readers keep reading. The school
# loses the ability to add students, not its students.
import logging
from datetime import date, timedelta

from extensions import db
from models.school_subscription import (
    CONSUMING_STATUSES,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_GRACE,
    STATUS_PENDING_PAYMENT,
    SchoolSubscription,
)

# How far ahead a school is warned that its term is ending.
RENEWAL_REMINDER_DAYS = (30, 7)


##
# @brief Move contracts whose term has ended into grace.
# @return the number of contracts transitioned.
def sweep_into_grace(as_of=None):
    as_of = as_of or date.today()
    due = (
        SchoolSubscription.query
        .filter(SchoolSubscription.status.in_((STATUS_ACTIVE, STATUS_PENDING_PAYMENT)))
        .filter(SchoolSubscription.term_end < as_of)
        .all()
    )
    for subscription in due:
        subscription.status = STATUS_GRACE
        db.session.add(subscription)
    return len(due)


##
# @brief Expire contracts whose grace window has elapsed.
# @return the number of contracts expired.
def sweep_into_expired(as_of=None):
    as_of = as_of or date.today()
    from apps.notifications import notify_licence_expired

    in_grace = (
        SchoolSubscription.query
        .filter(SchoolSubscription.status == STATUS_GRACE)
        .all()
    )
    expired = 0
    for subscription in in_grace:
        if subscription.term_end is None:
            continue
        grace_end = subscription.term_end + timedelta(days=subscription.grace_days or 0)
        if as_of > grace_end:
            subscription.status = STATUS_EXPIRED
            db.session.add(subscription)
            notify_licence_expired(subscription.shcool_id, subscription)
            expired += 1
    return expired


##
# @brief Warn schools whose term ends soon, at each reminder milestone.
# @return the number of reminders raised.
def send_renewal_reminders(as_of=None):
    as_of = as_of or date.today()
    from apps.notifications import notify_licence_term_ending

    reminders = 0
    for days_ahead in RENEWAL_REMINDER_DAYS:
        target = as_of + timedelta(days=days_ahead)
        # Exact-date match, not a range: the dedupe key already prevents
        # repeats, and a range would fire every milestone at once for a
        # contract created inside the window.
        ending = (
            SchoolSubscription.query
            .filter(SchoolSubscription.status.in_(CONSUMING_STATUSES))
            .filter(SchoolSubscription.term_end == target)
            .all()
        )
        for subscription in ending:
            created = notify_licence_term_ending(
                subscription.shcool_id, subscription, days_ahead
            )
            reminders += len(created or [])
    return reminders


##
# @brief Run every time-driven billing job. Safe to run repeatedly.
# @return a summary dict for the caller to log or print.
def run_billing_sweep(as_of=None):
    as_of = as_of or date.today()
    summary = {'as_of': as_of.isoformat(), 'into_grace': 0, 'expired': 0, 'reminders': 0}
    try:
        summary['reminders'] = send_renewal_reminders(as_of)
        # Grace first, then expiry: a contract cannot skip grace, and running
        # expiry on the same pass would otherwise need a second invocation.
        summary['into_grace'] = sweep_into_grace(as_of)
        summary['expired'] = sweep_into_expired(as_of)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        logging.error('Billing sweep failed: %s', error, exc_info=True)
        summary['error'] = str(error)
    return summary
