"""
Advance school contracts through their lifecycle and send renewal reminders.

Intended to run once a day from cron / Task Scheduler:

    python scripts/run_billing_sweep.py

Idempotent — running it twice in one day is a no-op the second time, so it is
safe to re-run after a failure. Use --as-of to rehearse a future date without
waiting for it.

    python scripts/run_billing_sweep.py --as-of 2027-09-02 --dry-run
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db
from apps.billing_lifecycle import run_billing_sweep


def main():
    parser = argparse.ArgumentParser(description='Run the daily billing sweep.')
    parser.add_argument('--as-of', help='Pretend today is this date (YYYY-MM-DD).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change, then roll back.')
    args = parser.parse_args()

    as_of = None
    if args.as_of:
        try:
            as_of = datetime.strptime(args.as_of, '%Y-%m-%d').date()
        except ValueError:
            print('--as-of must be YYYY-MM-DD')
            return 2

    with app.app_context():
        summary = run_billing_sweep(as_of)
        if args.dry_run:
            db.session.rollback()
            print('DRY RUN — nothing was written.')

        print('Billing sweep for %s' % summary['as_of'])
        print('  renewal reminders sent : %s' % summary['reminders'])
        print('  contracts into grace   : %s' % summary['into_grace'])
        print('  contracts expired      : %s' % summary['expired'])
        if summary.get('error'):
            print('  ERROR: %s' % summary['error'])
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
