## @file
# @brief Seat accounting for school contracts.
#
# A school buys a number of seats for a term. A seat is consumed by an
# "activated student": a student who has joined a pack. This module is the one
# place that decides which school an activation is billed to, when a seat is
# consumed, and when it comes back.
#
# Design notes worth knowing before changing anything here:
#
# * Every write goes through a SAVEPOINT (`begin_nested`). Seat bookkeeping
#   must never break the user action that triggered it -- a student redeeming
#   a pack code must not see a 500 because the billing tables are missing or a
#   contract row is malformed. A failed savepoint rolls back only the seat
#   write; the surrounding follow_pack insert survives, and the backfill
#   script can repair any gap afterwards. Without this, a un-run migration
#   would turn every pack join on the platform into a 500.
#
# * Nothing here commits. Callers already commit their own unit of work, and
#   the seat row must land in the same transaction as the Follow_pack row it
#   accounts for.
#
# * Enforcement is behind ConfigClass.SEAT_ENFORCEMENT_ENABLED, off by default.
#   Phase 1 records seats and reports usage; flipping the flag turns the same,
#   already-exercised code into a hard block at the cap.
import logging

from datetime import date, datetime

from config import ConfigClass
from extensions import db
from models.follow_pack import Follow_pack
from models.pack import Pack
from models.school_pack_instance import SchoolPackInstance
from models.school_seat_activation import SchoolSeatActivation
from models.school_subscription import (
    CONSUMING_STATUSES,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    SchoolSubscription,
)
from models.user_shcool import User_shcool

# Where an activation came from, for auditing a seat back to its cause.
SOURCE_READER_CODE = 'reader_code'
SOURCE_PARENT_CODE = 'parent_code'
SOURCE_ADMIN_ASSIGN = 'admin_assign'
SOURCE_BACKFILL = 'backfill'

# A licence that has run its course. Distinct from "never had one".
ENDED_STATUSES = (STATUS_EXPIRED, STATUS_CANCELLED)

# Usage points at which the school is warned. 100 doubles as "you are full".
SEAT_WARNING_THRESHOLDS = (80, 90, 100)


##
# @brief Which school an activation of this pack should be billed to.
#
# The rule (a product decision): a seat is consumed by the school that
# *provided* the pack -- the school that owns it, or, for a global pack, a
# school that has published it to its own readers. A reader with no school
# joining a global pack consumes nothing, which is what keeps B2C readers off
# schools' seat counts.
#
# A global pack published by two schools the student belongs to could in
# principle bill both; it bills one -- the student's default school if that
# school published it, otherwise the lowest school id -- because double-billing
# one student to two schools is a support ticket waiting to happen.
#
# @return the school id to bill, or None if this activation bills nobody.
def resolve_billing_school(pack, user_id):
    if pack is None or user_id is None:
        return None

    # A school-owned pack always bills its owner, whether or not the reader is
    # a member of that school -- the school provided the content either way
    # (e.g. a reader redeeming a code for that school's public pack).
    if not getattr(pack, 'is_global_pack', False):
        return pack.shcool_id

    memberships = User_shcool.query.filter_by(user_id=user_id).all()
    if not memberships:
        return None
    member_school_ids = [m.shcool_id for m in memberships]

    published = SchoolPackInstance.query.filter(
        SchoolPackInstance.pack_id == pack.id,
        SchoolPackInstance.shcool_id.in_(member_school_ids),
        SchoolPackInstance.active.is_(True),
    ).all()
    if not published:
        return None

    publisher_ids = {instance.shcool_id for instance in published}
    default_school_id = next(
        (m.shcool_id for m in memberships if m.is_default and m.shcool_id in publisher_ids),
        None
    )
    return default_school_id if default_school_id is not None else min(publisher_ids)


##
# @brief The contract a school is currently operating under, if any.
#
# Prefers a contract that is both consuming and covers today; falls back to the
# most recent consuming contract so that a school whose term dates are slightly
# off still resolves sensibly. Returns None for a school that has never had a
# contract -- which is every school until Phase 2 creates them, and is why
# seat activations carry a nullable subscription_id.
def get_active_subscription(school_id):
    if not school_id:
        return None
    today = date.today()
    consuming = (
        SchoolSubscription.query
        .filter(SchoolSubscription.shcool_id == school_id)
        .filter(SchoolSubscription.status.in_(CONSUMING_STATUSES))
        .order_by(SchoolSubscription.term_end.desc(), SchoolSubscription.id.desc())
        .all()
    )
    if not consuming:
        return None
    covering = next(
        (s for s in consuming if s.term_start <= today <= s.term_end),
        None
    )
    return covering or consuming[0]


##
# @brief The most recent contract of any status, including ended ones.
#
# Distinct from get_active_subscription: a school whose licence has expired has
# no *consuming* contract, but it is emphatically not the same as a school that
# never had one. The first must stop activating students; the second has no cap
# to enforce.
def get_latest_subscription(school_id):
    if not school_id:
        return None
    return (
        SchoolSubscription.query
        .filter(SchoolSubscription.shcool_id == school_id)
        .order_by(SchoolSubscription.term_end.desc(), SchoolSubscription.id.desc())
        .first()
    )


##
# @brief Open (unreleased) seat rows for a school.
def open_activations_query(school_id):
    return SchoolSeatActivation.query.filter(
        SchoolSeatActivation.shcool_id == school_id,
        SchoolSeatActivation.released_at.is_(None),
    )


##
# @brief How many seats a school is currently consuming.
def seats_used(school_id):
    if not school_id:
        return 0
    return open_activations_query(school_id).count()


##
# @brief Does this student already hold an open seat at this school?
def get_open_activation(school_id, user_id):
    return open_activations_query(school_id).filter(
        SchoolSeatActivation.user_id == user_id
    ).first()


##
# @brief Whether a school may activate one more student right now.
#
# Returns (allowed, message). The message is caller-facing, so it is phrased
# for whoever is being refused -- a child redeeming a code should not be shown
# their school's commercial terms.
#
# Always allows when enforcement is disabled (Phase 1) or when the school has
# no contract at all, so that introducing this code cannot lock anyone out.
def check_capacity(school_id, audience='admin'):
    if not school_id:
        return True, None
    if not getattr(ConfigClass, 'SEAT_ENFORCEMENT_ENABLED', False):
        return True, None

    subscription = get_active_subscription(school_id)
    if subscription is None:
        # No live contract. An expired or cancelled one still bites -- the
        # school had a licence and it ended. A school that never had a
        # contract has no cap to enforce and is always allowed.
        latest = get_latest_subscription(school_id)
        if latest is not None and latest.status in ENDED_STATUSES:
            if audience == 'reader':
                return False, (
                    'Your school\'s reading licence has ended. '
                    'Please ask your teacher or school administrator.'
                )
            return False, (
                'This school\'s licence ended on %s. Renew it to activate more students.'
                % (latest.term_end.isoformat() if latest.term_end else 'its end date')
            )
        return True, None

    if seats_used(school_id) < subscription.seat_limit:
        return True, None

    if audience == 'reader':
        return False, 'Your school has reached its reader limit. Please ask your teacher or school administrator.'
    return False, (
        'This school has reached its licensed reader limit (%s). '
        'Upgrade the contract to activate more students.' % subscription.seat_limit
    )


##
# @brief Record that a student has become active against the school that
# provided this pack. Idempotent: a student who already holds an open seat at
# that school does not consume a second one.
#
# @return the SchoolSeatActivation row (new or pre-existing), or None if this
#         activation bills nobody or the bookkeeping failed.
def activate_seat(user_id, pack, source=None):
    school_id = None
    try:
        with db.session.begin_nested():
            school_id = resolve_billing_school(pack, user_id)
            if school_id is None:
                return None

            existing = get_open_activation(school_id, user_id)
            if existing is not None:
                return existing

            subscription = get_active_subscription(school_id)
            activation = SchoolSeatActivation(
                shcool_id=school_id,
                user_id=user_id,
                subscription_id=subscription.id if subscription else None,
                first_pack_id=pack.id,
                activated_at=datetime.now(),
                source=source,
            )
            db.session.add(activation)
    except Exception as error:
        logging.error(
            'Seat activation failed for user=%s pack=%s: %s',
            user_id, getattr(pack, 'id', None), error
        )
        return None

    # Outside the savepoint on purpose: the seat is the thing that must be
    # recorded correctly. A failure to raise the "you are nearly full" warning
    # is an annoyance, not a reason to lose the activation it was warning about.
    try:
        with db.session.begin_nested():
            notify_seat_threshold_if_crossed(school_id)
    except Exception as error:
        logging.warning('Seat threshold notification failed for school=%s: %s',
                        school_id, error)

    return activation


##
# @brief Warn a school's admins as their seat usage climbs.
#
# Fires only when a seat is newly consumed, so it cannot spam on page loads.
# Deduped per (contract, threshold) so each warning is delivered once per term,
# not once per student who tips it over.
def notify_seat_threshold_if_crossed(school_id):
    subscription = get_active_subscription(school_id)
    if subscription is None or not subscription.seat_limit:
        return None

    used = seats_used(school_id)
    percent = (used / subscription.seat_limit) * 100
    crossed = [t for t in SEAT_WARNING_THRESHOLDS if percent >= t]
    if not crossed:
        return None

    # Imported here rather than at module scope: notifications pulls in a large
    # slice of the model graph, and seats.py is imported by request paths that
    # have no interest in it.
    from apps.notifications import notify_seat_threshold_reached

    return notify_seat_threshold_reached(
        school_id, subscription, used, max(crossed)
    )


##
# @brief Close a student's open seat at a school, returning it to the pool.
#
# @return the number of seats released.
def release_seat(user_id, school_id, reason=None):
    try:
        with db.session.begin_nested():
            activations = open_activations_query(school_id).filter(
                SchoolSeatActivation.user_id == user_id
            ).all()
            now = datetime.now()
            for activation in activations:
                activation.released_at = now
                activation.release_reason = reason
                db.session.add(activation)
            return len(activations)
    except Exception as error:
        logging.error(
            'Seat release failed for user=%s school=%s: %s', user_id, school_id, error
        )
        return 0


##
# @brief Release a student's seat only if they no longer hold any pack
# attributable to that school.
#
# Used when a single pack is dropped: a student who still follows another of
# that school's packs is still an activated student and keeps the seat.
def release_seat_if_no_packs_remain(user_id, school_id, reason=None):
    try:
        remaining = (
            db.session.query(Follow_pack.pack_id)
            .filter(Follow_pack.user_id == user_id)
            .all()
        )
        for (pack_id,) in remaining:
            pack = Pack.query.get(pack_id)
            if resolve_billing_school(pack, user_id) == school_id:
                return 0
    except Exception as error:
        logging.error(
            'Seat re-check failed for user=%s school=%s: %s', user_id, school_id, error
        )
        return 0
    return release_seat(user_id, school_id, reason=reason)


##
# @brief Release every seat a student holds, across all schools.
# Used when the student's account itself goes away.
def release_all_seats(user_id, reason=None):
    try:
        school_ids = [
            row.shcool_id for row in
            SchoolSeatActivation.query
            .filter(SchoolSeatActivation.user_id == user_id,
                    SchoolSeatActivation.released_at.is_(None))
            .all()
        ]
    except Exception as error:
        logging.error('Seat lookup failed for user=%s: %s', user_id, error)
        return 0
    return sum(release_seat(user_id, school_id, reason=reason) for school_id in set(school_ids))


##
# @brief Attach a school's un-attributed open seats to a contract.
#
# Activations recorded before the school had any contract -- everything the
# backfill imports, plus anyone who joined a pack between contracts -- carry a
# NULL subscription_id. When a contract is created they belong to it, otherwise
# the contract would report zero usage on day one while the school is visibly
# full of activated students.
#
# @return the number of seats attached.
def attach_orphan_activations(school_id, subscription):
    if not school_id or subscription is None:
        return 0
    try:
        with db.session.begin_nested():
            orphans = open_activations_query(school_id).filter(
                SchoolSeatActivation.subscription_id.is_(None)
            ).all()
            for activation in orphans:
                activation.subscription_id = subscription.id
                db.session.add(activation)
            return len(orphans)
    except Exception as error:
        logging.error(
            'Attaching orphan activations failed for school=%s: %s', school_id, error
        )
        return 0


##
# @brief Everything a dashboard needs to render "remaining readers" for one
# school, whether or not that school has a contract yet.
def seat_summary(school_id):
    used = seats_used(school_id)
    subscription = get_active_subscription(school_id)
    if subscription is None:
        # An ended licence is still shown -- a school whose term lapsed needs
        # to see why it can no longer activate students, rather than a blank
        # "no contract" panel identical to a school that never had one.
        latest = get_latest_subscription(school_id)
        if latest is not None and latest.status in ENDED_STATUSES:
            subscription = latest

    if subscription is None:
        return {
            'seats_used': used,
            'seat_limit': None,
            'seats_remaining': None,
            'usage_percent': None,
            'has_contract': False,
            'status': None,
            'term_start': None,
            'term_end': None,
            'plan_name': None,
            'enforcement_enabled': bool(getattr(ConfigClass, 'SEAT_ENFORCEMENT_ENABLED', False)),
        }

    limit = subscription.seat_limit or 0
    return {
        'seats_used': used,
        'seat_limit': limit,
        'seats_remaining': max(limit - used, 0),
        'usage_percent': round((used / limit) * 100, 1) if limit else None,
        'has_contract': True,
        'status': subscription.status,
        'term_start': subscription.term_start.isoformat() if subscription.term_start else None,
        'term_end': subscription.term_end.isoformat() if subscription.term_end else None,
        'plan_name': subscription.plan.name if subscription.plan else None,
        'enforcement_enabled': bool(getattr(ConfigClass, 'SEAT_ENFORCEMENT_ENABLED', False)),
    }
