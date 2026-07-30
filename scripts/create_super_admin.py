"""
Create (or reset) a super-admin account directly against the database.

Needed whenever there is no super admin to log in as: a freshly rebuilt
database, or a forgotten password on the only platform account. The HTTP
bootstrap route (POST /reader/register_super_admin) only works while *no* super
admin exists, so once one is there this script is the way back in.

Why a script rather than a couple of INSERT statements:

  * The password is bcrypt-hashed. A plaintext value written straight into
    user.password_hashed can never log in -- the login route compares with
    bcrypt.check_password_hash, which fails closed on a non-hash.
  * SuperAdmin is single-table-inheritance across two tables: a row in `user`
    carrying type='super_admin', and a matching row in `super_admin` with the
    same id. Insert only the first and the account exists but cannot be loaded
    as a super admin; insert only the second and it is orphaned.
  * confirmed and approved must both be true, and is_active must not be false --
    is_super_admin() checks all of them, and app.py's before_request logs out
    any session whose account is inactive.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/create_super_admin.py --email you@example.com --password 'S3cret!'
    python scripts/create_super_admin.py --email you@example.com --password 'S3cret!' --username admin
    python scripts/create_super_admin.py --email you@example.com --password 'N3w!' --reset
    python scripts/create_super_admin.py --list

Safe to re-run: an existing address is refused unless --reset is passed, so a
second run cannot quietly create a duplicate login.
"""
import argparse
import getpass
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from apps.reader.routes import bcrypt
from extensions import db
from models.user import SuperAdmin, User
from models.user_shcool import User_shcool
from models.shcool import Shcool

MIN_PASSWORD_LENGTH = 8


## @brief Store the hash as text.
#
# flask_bcrypt returns bytes on some versions and str on others; the column is a
# String, and check_password_hash accepts either. Normalising here keeps the row
# from ever holding a b'...' repr, which would compare unequal forever.
def hash_password(raw_password):
    hashed = bcrypt.generate_password_hash(raw_password)
    if isinstance(hashed, bytes):
        return hashed.decode('utf-8')
    return hashed


def list_super_admins():
    admins = SuperAdmin.query.order_by(SuperAdmin.id.asc()).all()
    if not admins:
        print('No super admin exists yet.')
        return
    print('%-5s %-24s %-34s %-9s %-8s %s' % (
        'id', 'username', 'email', 'confirmed', 'approved', 'active'))
    for admin in admins:
        print('%-5s %-24s %-34s %-9s %-8s %s' % (
            admin.id, admin.username, admin.email,
            admin.confirmed, admin.approved, admin.is_active))


def main():
    parser = argparse.ArgumentParser(
        description='Create or reset a super-admin account.')
    parser.add_argument('--email', help='Sign-in email address.')
    parser.add_argument('--password',
                        help='Sign-in password. Omit to be prompted without echo.')
    parser.add_argument('--username',
                        help='Display name. Defaults to the part before the @.')
    parser.add_argument('--reset', action='store_true',
                        help='If the email already exists, reset its password and '
                             're-approve it instead of refusing.')
    parser.add_argument('--list', action='store_true',
                        help='List existing super admins and exit.')
    args = parser.parse_args()

    with app.app_context():
        if args.list:
            list_super_admins()
            return 0

        if not args.email:
            parser.error('--email is required (or use --list)')

        email = args.email.strip().lower()

        password = args.password
        if not password:
            # Prompted rather than passed as an argument so the credential does
            # not end up in shell history or the process list.
            password = getpass.getpass('Password: ')
            if password != getpass.getpass('Confirm password: '):
                print('Passwords do not match.')
                return 1

        if len(password) < MIN_PASSWORD_LENGTH:
            print('Password must be at least %d characters.' % MIN_PASSWORD_LENGTH)
            return 1

        existing = User.query.filter(User.email == email).first()
        if existing:
            if not args.reset:
                print('A user with %s already exists (id=%s, type=%s).'
                      % (email, existing.id, existing.type))
                print('Re-run with --reset to reset its password, or use a different email.')
                return 1
            if existing.type != 'super_admin':
                # Changing type would leave the row without its matching subclass
                # table entry, so this has to be refused rather than coerced.
                print('%s belongs to a %s account, not a super admin. '
                      'Refusing to convert it -- use a different email.'
                      % (email, existing.type))
                return 1

            existing.password_hashed = hash_password(password)
            existing.confirmed = True
            existing.approved = True
            existing.is_active = True
            existing.suspended_at = None
            existing.suspended_by = None
            existing.suspended_reason = None
            existing.must_change_password = False
            if args.username:
                existing.username = args.username.strip()
            db.session.commit()
            print('Super admin %s reset (id=%s).' % (email, existing.id))
            return 0

        username = (args.username or email.split('@')[0]).strip()

        super_admin = SuperAdmin(
            username=username,
            email=email,
            password_hashed=hash_password(password),
            created_at=datetime.now(),
            confirmed=True,
            approved=True,
            is_active=True
        )
        db.session.add(super_admin)
        db.session.commit()

        # Super admins are otherwise schoolless. This membership is what lets the
        # same account use the school-admin-scoped endpoints (get_current_school_id)
        # -- including the storage manager's school scope. Only applies if the
        # default "IRead" school exists; on a fresh database it usually does not,
        # which is fine: the platform scope works without it.
        default_school = Shcool.query.filter_by(name='IRead').first()
        if default_school:
            membership = User_shcool.query.filter_by(
                user_id=super_admin.id, shcool_id=default_school.id).first()
            if not membership:
                db.session.add(User_shcool(
                    user_id=super_admin.id, shcool_id=default_school.id))
                db.session.commit()
            print('Linked to the default "IRead" school (id=%s).' % default_school.id)
        else:
            print('No default "IRead" school found -- the account is platform-scoped only.')

        print('\nSuper admin created.')
        print('  id:       %s' % super_admin.id)
        print('  username: %s' % super_admin.username)
        print('  email:    %s' % super_admin.email)
        print('\nSign in at the dashboard with that email and the password you set.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
