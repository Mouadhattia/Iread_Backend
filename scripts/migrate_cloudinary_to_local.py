"""
Move every remotely-hosted image referenced by the database into our own
per-school storage, and rewrite the column to point at the new local URL.

Cloudinary was never used by the backend -- the dashboards uploaded straight
from the browser and only the resulting `https://res.cloudinary.com/...` URL was
stored. So "removing Cloudinary" is in two halves: stop writing those URLs (done
in the app code) and re-host the ones already stored. This script is the second
half, and until it has run those images are still served from Cloudinary.

What it touches, and which storage bucket each lands in:

    book.img                        -> books/covers
    pack.img                        -> packs/images
    pack_template.img               -> packs/images
    user.img                        -> general
    session.img                     -> general
    school_public_page.logo         -> general
    school_public_page.cover_image  -> general
    school_public_page.sections[].image and the same keys inside draft_data
                                    -> general

Ownership: a row's own school decides the folder. Rows with no school (platform
books, super-admins, shared pack templates) go to `platform/`. A user's school
comes from their User_shcool membership; a user in several schools is filed
under the first, since an avatar is not school-specific and the folder is only
about who pays for the bytes.

Quota is deliberately NOT enforced here. This is a migration of files a school
already has, and failing halfway through because a school is over its allowance
would leave the database half-rewritten. Check the storage report afterwards and
raise quotas as needed.

Not covered: notification categories. Those live in the separate notification
microservice (MongoDB), not in this database -- their images need the same
treatment through that service's own API.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/migrate_cloudinary_to_local.py --dry-run   # report only
    python scripts/migrate_cloudinary_to_local.py             # migrate
    python scripts/migrate_cloudinary_to_local.py --host res.cloudinary.com
    python scripts/migrate_cloudinary_to_local.py --table book --table pack

Re-runnable: a column already pointing at a local /media/ URL is skipped, so an
interrupted run can simply be started again.
"""
import argparse
import mimetypes
import os
import sys
from urllib.parse import urlparse
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from sqlalchemy.orm.attributes import flag_modified

from app import app
from apps.storage import (
    MEDIA_URL_PREFIX,
    category_dir,
    public_url,
    register_existing_file,
    relative_path_from_absolute,
)
from extensions import db
from models.book import Book
from models.pack import Pack
from models.pack_template import Pack_template
from models.school_public_page import SchoolPublicPage
from models.session import Session
from models.user import User
from models.user_shcool import User_shcool

## @brief Hosts whose images should be pulled in. Cloudinary is the one that
# matters; the flaticon/wikimedia defaults are placeholder icons that were never
# uploaded by a school, so they are left alone by default -- re-hosting them
# would spend a school's quota on a stock avatar.
DEFAULT_HOSTS = ('res.cloudinary.com', 'cloudinary.com')

DOWNLOAD_TIMEOUT_SECONDS = 60

## @brief Extension to fall back on when a URL carries none and the response
# gives no usable content type. Cloudinary serves these as images.
FALLBACK_EXTENSION = 'jpg'


class MigrationStats:
    def __init__(self):
        self.migrated = 0
        self.skipped_local = 0
        self.skipped_foreign = 0
        self.failed = 0
        self.bytes_downloaded = 0

    def report(self):
        print('\n--- summary ---')
        print('migrated:            %s' % self.migrated)
        print('already local:       %s' % self.skipped_local)
        print('left as-is (other):  %s' % self.skipped_foreign)
        print('failed:              %s' % self.failed)
        print('downloaded:          %.2f MB' % (self.bytes_downloaded / (1024 * 1024)))


## @brief True when a stored value is one of ours already.
def is_local_url(value):
    return bool(value) and ('%s/' % MEDIA_URL_PREFIX) in str(value)


## @brief True when a URL should be pulled into local storage.
def should_migrate(value, hosts):
    if not value or not isinstance(value, str):
        return False
    value = value.strip()
    if not value.lower().startswith(('http://', 'https://')):
        return False
    if is_local_url(value):
        return False
    host = (urlparse(value).hostname or '').lower()
    return any(host == candidate or host.endswith('.' + candidate) for candidate in hosts)


## @brief Best guess at a file extension for a downloaded URL.
def guess_extension(url, content_type):
    path_ext = os.path.splitext(urlparse(url).path)[1].lstrip('.').lower()
    if path_ext and len(path_ext) <= 5 and path_ext.isalnum():
        return path_ext
    if content_type:
        guessed = mimetypes.guess_extension((content_type or '').split(';')[0].strip())
        if guessed:
            return guessed.lstrip('.').lower()
    return FALLBACK_EXTENSION


## @brief Download one remote image into a school's bucket and index it.
#
# @return the new public URL, or None when the download failed.
def fetch_into_storage(url, school_id, category, linked_type, linked_id, stats, dry_run):
    if dry_run:
        print('    would fetch %s -> %s/%s' % (url, school_id if school_id else 'platform', category))
        stats.migrated += 1
        return None

    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as error:
        print('    FAILED %s: %s' % (url, error))
        stats.failed += 1
        return None

    content = response.content
    if not content:
        print('    FAILED %s: empty response' % url)
        stats.failed += 1
        return None

    extension = guess_extension(url, response.headers.get('Content-Type'))
    original_filename = os.path.basename(urlparse(url).path) or ('image.%s' % extension)
    stored_filename = '%s-%s.%s' % (category.replace('/', '-'), uuid4().hex, extension)
    destination = os.path.join(category_dir(school_id, category), stored_filename)

    with open(destination, 'wb') as handle:
        handle.write(content)

    register_existing_file(
        school_id,
        category,
        destination,
        original_filename=original_filename,
        title=None,
        linked_type=linked_type,
        linked_id=linked_id,
        mime_type=(response.headers.get('Content-Type') or '').split(';')[0].strip() or None
    )

    stats.migrated += 1
    stats.bytes_downloaded += len(content)
    new_url = public_url(relative_path_from_absolute(destination))
    print('    %s -> %s' % (url, new_url))
    return new_url


## @brief Rewrite one string column across a table.
def migrate_column(model, column_name, category, linked_type, school_id_getter,
                   hosts, stats, dry_run, label=None):
    label = label or '%s.%s' % (model.__tablename__, column_name)
    print('\n[%s]' % label)
    rows = model.query.all()
    for row in rows:
        value = getattr(row, column_name, None)
        if is_local_url(value):
            stats.skipped_local += 1
            continue
        if not should_migrate(value, hosts):
            if value:
                stats.skipped_foreign += 1
            continue

        print('  #%s' % row.id)
        new_url = fetch_into_storage(
            value, school_id_getter(row), category, linked_type, row.id, stats, dry_run
        )
        if new_url:
            setattr(row, column_name, new_url)


## @brief Rewrite the image keys inside a public page's JSON section lists.
#
# The published `sections` and the unpublished `draft_data` both carry section
# images, and an admin who has a draft open would otherwise see the old
# Cloudinary URL reappear the moment they publish.
def migrate_public_page_sections(hosts, stats, dry_run):
    print('\n[school_public_page.sections / draft_data]')
    for page in SchoolPublicPage.query.all():
        changed = False

        def migrate_section_list(sections):
            nonlocal changed
            if not isinstance(sections, list):
                return sections
            for section in sections:
                if not isinstance(section, dict):
                    continue
                value = section.get('image')
                if is_local_url(value):
                    stats.skipped_local += 1
                    continue
                if not should_migrate(value, hosts):
                    if value:
                        stats.skipped_foreign += 1
                    continue
                print('  page #%s section image' % page.id)
                new_url = fetch_into_storage(
                    value, page.shcool_id, 'general', 'public_page', page.id, stats, dry_run
                )
                if new_url:
                    section['image'] = new_url
                    changed = True
            return sections

        page.sections = migrate_section_list(page.sections)

        if isinstance(page.draft_data, dict):
            draft = dict(page.draft_data)
            draft['sections'] = migrate_section_list(draft.get('sections'))
            for key in ('logo', 'cover_image'):
                value = draft.get(key)
                if is_local_url(value):
                    stats.skipped_local += 1
                    continue
                if not should_migrate(value, hosts):
                    if value:
                        stats.skipped_foreign += 1
                    continue
                print('  page #%s draft %s' % (page.id, key))
                new_url = fetch_into_storage(
                    value, page.shcool_id, 'general', 'public_page', page.id, stats, dry_run
                )
                if new_url:
                    draft[key] = new_url
                    changed = True
            if changed:
                page.draft_data = draft
                flag_modified(page, 'draft_data')

        if changed:
            # SQLAlchemy cannot see edits made in place inside a JSON column's
            # Python structure, so without this the rewritten section images are
            # silently dropped at commit and the page still shows Cloudinary.
            flag_modified(page, 'sections')


## @brief A user's owning school, for filing their avatar.
def user_school_id(user):
    membership = User_shcool.query.filter_by(user_id=user.id).first()
    return membership.shcool_id if membership else None


## @brief A session's owning school.
#
# The session table has no school column of its own, so ownership comes from its
# pack, falling back to its book. Without this every session cover would land in
# the platform folder and be billed to nobody.
def session_school_id(session):
    if session.pack_id:
        pack = Pack.query.get(session.pack_id)
        if pack and getattr(pack, 'shcool_id', None):
            return pack.shcool_id
    if session.book_id:
        book = Book.query.get(session.book_id)
        if book and book.shcool_id:
            return book.shcool_id
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Re-host remotely-stored images into per-school local storage.'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be migrated without downloading or writing.')
    parser.add_argument('--host', action='append', dest='hosts',
                        help='Hostname to migrate from (repeatable). Defaults to Cloudinary.')
    parser.add_argument('--table', action='append', dest='tables',
                        help='Limit to these targets (repeatable): book, pack, pack_template, '
                             'user, session, public_page. Defaults to all.')
    args = parser.parse_args()

    hosts = tuple(host.lower().lstrip('.') for host in (args.hosts or DEFAULT_HOSTS))
    targets = set(args.tables or
                  ['book', 'pack', 'pack_template', 'user', 'session', 'public_page'])
    stats = MigrationStats()

    print('Migrating image URLs from: %s' % ', '.join(hosts))
    print('Targets: %s' % ', '.join(sorted(targets)))
    if args.dry_run:
        print('DRY RUN -- nothing will be downloaded or written.')

    with app.app_context():
        if 'book' in targets:
            migrate_column(Book, 'img', 'books/covers', 'book',
                           lambda row: row.shcool_id, hosts, stats, args.dry_run)
        if 'pack' in targets:
            migrate_column(Pack, 'img', 'packs/images', 'pack',
                           lambda row: getattr(row, 'shcool_id', None),
                           hosts, stats, args.dry_run)
        if 'pack_template' in targets:
            # Templates are platform-level, so their images belong to nobody's quota.
            migrate_column(Pack_template, 'img', 'packs/images', 'pack_template',
                           lambda row: None, hosts, stats, args.dry_run)
        if 'user' in targets:
            migrate_column(User, 'img', 'general', 'user',
                           user_school_id, hosts, stats, args.dry_run)
        if 'session' in targets:
            migrate_column(Session, 'img', 'general', 'session',
                           session_school_id, hosts, stats, args.dry_run)
        if 'public_page' in targets:
            migrate_column(SchoolPublicPage, 'logo', 'general', 'public_page',
                           lambda row: row.shcool_id, hosts, stats, args.dry_run)
            migrate_column(SchoolPublicPage, 'cover_image', 'general', 'public_page',
                           lambda row: row.shcool_id, hosts, stats, args.dry_run)
            migrate_public_page_sections(hosts, stats, args.dry_run)

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()
            print('\nCommitted.')

    stats.report()

    if stats.failed:
        print('\n%s download(s) failed -- those columns still point at the old host. '
              'Re-run to retry them.' % stats.failed)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
