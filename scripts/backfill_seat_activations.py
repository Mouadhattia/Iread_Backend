"""
Backfill the school seat ledger from existing pack memberships.

An "activated student" is a student who has joined a pack. That relationship
has always existed in `follow_pack`, but seats were only introduced with school
contracts, so every pre-existing membership needs a ledger row before the
"remaining readers" counter tells the truth.

Attribution follows the same rule the live code uses (apps/seats.py):
a seat is billed to the school that provided the pack -- the school that owns
it, or, for a global pack, a school the student belongs to that has published
it. Readers with no school consume nothing.

Two deliberate limitations:

  * `follow_pack` has no created_at, so there is no real activation date to
    recover. Rows are stamped with the run time and marked source='backfill'
    so they are distinguishable from genuine activations for ever after.
  * Only readers are counted. Staff accounts can hold a follow_pack row
    (a school admin testing a pack, say) and must not consume a paid seat.

Idempotent: a student who already holds an open seat at a school is skipped,
so this is safe to re-run and safe to run while the app is live.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/backfill_seat_activations.py             # every school
    python scripts/backfill_seat_activations.py --school 3
    python scripts/backfill_seat_activations.py --dry-run   # report only
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db
from models.follow_pack import Follow_pack
from models.pack import Pack
from models.school_seat_activation import SchoolSeatActivation
from models.shcool import Shcool
from models.user import Reader
from apps.seats import SOURCE_BACKFILL, get_active_subscription, resolve_billing_school


def main():
    parser = argparse.ArgumentParser(description='Backfill school seat activations.')
    parser.add_argument('--school', type=int, help='Only backfill this school id.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be created, then roll back without persisting.')
    args = parser.parse_args()

    with app.app_context():
        reader_ids = {reader_id for (reader_id,) in db.session.query(Reader.id).all()}
        if not reader_ids:
            print('No readers found -- nothing to backfill.')
            return

        memberships = (
            db.session.query(Follow_pack.user_id, Follow_pack.pack_id)
            .filter(Follow_pack.user_id.in_(reader_ids))
            .all()
        )
        print('Scanning %s pack memberships across %s readers...' % (len(memberships), len(reader_ids)))

        pack_cache = {}
        subscription_cache = {}
        # (school_id, user_id) pairs this run has already accounted for, so a
        # reader following three packs from one school consumes one seat.
        seen = set()
        created_by_school = defaultdict(int)
        skipped_unattributed = 0
        now = datetime.now()

        for user_id, pack_id in memberships:
            if pack_id not in pack_cache:
                pack_cache[pack_id] = Pack.query.get(pack_id)
            pack = pack_cache[pack_id]

            school_id = resolve_billing_school(pack, user_id)
            if school_id is None:
                skipped_unattributed += 1
                continue
            if args.school and school_id != args.school:
                continue
            if (school_id, user_id) in seen:
                continue
            seen.add((school_id, user_id))

            already_open = SchoolSeatActivation.query.filter(
                SchoolSeatActivation.shcool_id == school_id,
                SchoolSeatActivation.user_id == user_id,
                SchoolSeatActivation.released_at.is_(None),
            ).first()
            if already_open is not None:
                continue

            if school_id not in subscription_cache:
                subscription_cache[school_id] = get_active_subscription(school_id)
            subscription = subscription_cache[school_id]

            db.session.add(SchoolSeatActivation(
                shcool_id=school_id,
                user_id=user_id,
                subscription_id=subscription.id if subscription else None,
                first_pack_id=pack_id,
                activated_at=now,
                source=SOURCE_BACKFILL,
            ))
            created_by_school[school_id] += 1

        total_new = sum(created_by_school.values())

        if args.dry_run:
            db.session.rollback()
            print('\nDRY RUN -- nothing was written.')
        else:
            db.session.commit()

        print('\nSeats created: %s' % total_new)
        if skipped_unattributed:
            print('Memberships billing to no school (B2C / unpublished global packs): %s'
                  % skipped_unattributed)
        for school_id, count in sorted(created_by_school.items(), key=lambda item: -item[1]):
            school = Shcool.query.get(school_id)
            print('  %-40s %s' % ((school.name if school else 'school %s' % school_id)[:40], count))


if __name__ == '__main__':
    main()
