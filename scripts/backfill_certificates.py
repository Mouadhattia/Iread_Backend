"""
Backfill Global Reading Passport certificates for existing readers (PRD §2).

Certificates are issued from the same milestones the achievement engine already
tracks (a CEFR band cleared, or every tracked word in a book mastered). Readers
who reached those milestones before certificates existed have no certificate
rows yet; this script reconciles them idempotently — safe to re-run, it never
duplicates (the (user_id, milestone_key) unique constraint guards that).

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/backfill_certificates.py            # every reader
    python scripts/backfill_certificates.py --user 1152
    python scripts/backfill_certificates.py --dry-run  # report only, no writes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db
from models.user import Reader
from apps.certificates import issue_certificates_for_user


def main():
    parser = argparse.ArgumentParser(description='Backfill passport certificates.')
    parser.add_argument('--user', type=int, help='Only reconcile this reader id.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be issued, then roll back without persisting.')
    args = parser.parse_args()

    with app.app_context():
        if args.user:
            reader_ids = [args.user]
        else:
            reader_ids = [reader.id for reader in Reader.query.all()]

        total_new = 0
        readers_credited = 0
        for user_id in reader_ids:
            issued = issue_certificates_for_user(user_id, commit=not args.dry_run)
            if issued:
                readers_credited += 1
                total_new += len(issued)
                titles = ', '.join(certificate['title'] for certificate in issued)
                print('reader %s: +%d certificate(s) -> %s' % (user_id, len(issued), titles))

        if args.dry_run:
            db.session.rollback()
            print('DRY RUN — rolled back. Would issue %d certificate(s) across %d of %d reader(s).'
                  % (total_new, readers_credited, len(reader_ids)))
        else:
            print('Done. Issued %d new certificate(s) across %d of %d reader(s).'
                  % (total_new, readers_credited, len(reader_ids)))


if __name__ == '__main__':
    main()
