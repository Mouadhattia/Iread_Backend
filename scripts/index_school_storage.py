"""
Reconcile the school_file index against what is actually on disk.

The index is what the storage manager reads and what every quota check is
computed from, so it drifting from the filesystem is the one thing that makes
storage reporting untrustworthy. Two ways it drifts:

  * A file exists on disk with no row -- it consumes space nobody is charged
    for and the admin cannot see or delete it from the dashboard. Happens with
    files restored from a backup, copied in by hand, or written before this
    feature existed.
  * A row exists whose file is gone -- the school is charged for space it is not
    using. Happens when a file is deleted directly on the server.

Also imports the two legacy upload trees (STORY_UPLOAD_DIR and
AUDIOBOOK_UPLOAD_DIR). Files there are still referenced by absolute path in
book_story / audio_book rows and are still served correctly, so this script
copies nothing and moves nothing -- it only indexes them where they lie, so the
space they use is finally visible. Their old layout is `<root>/<school|platform>/
<book_id>/...`, which is where the owning school is read from.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/index_school_storage.py --dry-run     # report only
    python scripts/index_school_storage.py               # write the index
    python scripts/index_school_storage.py --school 12   # one school
    python scripts/index_school_storage.py --skip-legacy # new tree only
    python scripts/index_school_storage.py --prune       # also drop dead rows

Safe to re-run: rows are matched on their path, so an existing entry has its
size refreshed rather than being duplicated.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from apps.storage import (
    LEGACY_PATH_PREFIX,
    PLATFORM_FOLDER,
    absolute_path,
    owner_folder,
    register_existing_file,
    relative_path_from_absolute,
    school_id_from_folder,
    storage_root,
)
from config import ConfigClass
from extensions import db
from models.school_file import STORAGE_CATEGORIES, SchoolFile

## @brief Where a legacy file lands in the new category scheme, chosen by the
# tree it came from and (for audiobooks) the asset folder in its path.
LEGACY_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.webm', '.ogg', '.aac'}
LEGACY_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}


def categorize_legacy_file(source_tree, file_path):
    extension = os.path.splitext(file_path)[1].lower()
    if source_tree == 'stories':
        # The story tree only ever held PDFs.
        return 'books/files'
    # Audiobook tree: a cover lives under a 'cover' folder, page assets under
    # 'pages'. Fall back on the extension when the path shape is unfamiliar.
    normalized = file_path.replace(os.sep, '/').lower()
    if '/cover' in normalized:
        return 'books/covers'
    if extension in LEGACY_AUDIO_EXTENSIONS:
        return 'stories/audio'
    if extension in LEGACY_IMAGE_EXTENSIONS:
        return 'stories/images'
    return 'general'


## @brief Owning school for a path in a legacy tree.
#
# Legacy layout is `<root>/<school_id or "platform">/<book_id>/...`, so the
# first path segment carries the owner.
def legacy_school_id(upload_root, file_path):
    relative = os.path.relpath(file_path, upload_root)
    first = relative.replace(os.sep, '/').split('/')[0]
    if first == PLATFORM_FOLDER:
        return None
    try:
        return int(first)
    except (TypeError, ValueError):
        return None


class IndexStats:
    def __init__(self):
        self.created = 0
        self.refreshed = 0
        self.pruned = 0
        self.dead = 0
        self.bytes_indexed = 0

    def report(self, pruned_enabled):
        print('\n--- summary ---')
        print('new rows indexed:   %s' % self.created)
        print('existing refreshed: %s' % self.refreshed)
        print('rows with no file:  %s' % self.dead)
        if pruned_enabled:
            print('rows pruned:        %s' % self.pruned)
        print('indexed on disk:    %.2f MB' % (self.bytes_indexed / (1024 * 1024)))


## @brief Walk the current storage tree and index anything not already recorded.
def index_storage_tree(only_school, stats, dry_run):
    root = storage_root()
    if not os.path.isdir(root):
        print('Storage root does not exist yet: %s' % root)
        return

    print('\n[storage tree] %s' % root)
    for folder_name in sorted(os.listdir(root)):
        owner_path = os.path.join(root, folder_name)
        if not os.path.isdir(owner_path):
            continue
        try:
            school_id = school_id_from_folder(folder_name)
        except Exception:
            print('  skipping unrecognised folder: %s' % folder_name)
            continue
        if only_school is not None and school_id != only_school:
            continue

        for category in STORAGE_CATEGORIES:
            category_path = os.path.join(owner_path, *category.split('/'))
            if not os.path.isdir(category_path):
                continue
            for entry in sorted(os.listdir(category_path)):
                file_path = os.path.join(category_path, entry)
                if not os.path.isfile(file_path):
                    continue
                relative = relative_path_from_absolute(file_path)
                existing = SchoolFile.query.filter_by(relative_path=relative).first()
                size = os.path.getsize(file_path)
                stats.bytes_indexed += size

                if existing:
                    if existing.file_size != size or not existing.active:
                        print('  refresh %s (%s bytes)' % (relative, size))
                        stats.refreshed += 1
                        if not dry_run:
                            existing.file_size = size
                            existing.active = True
                    continue

                print('  index   %s (%s bytes) -> %s' % (relative, size, category))
                stats.created += 1
                if not dry_run:
                    register_existing_file(school_id, category, file_path)


## @brief Index one of the pre-existing upload trees in place.
def index_legacy_tree(upload_root, source_tree, only_school, stats, dry_run):
    upload_root = os.path.abspath(upload_root)
    if not os.path.isdir(upload_root):
        return
    if upload_root == storage_root() or upload_root.startswith(storage_root() + os.sep):
        # Already covered by the storage-tree walk; indexing it twice would
        # double-count every file toward the school's usage.
        print('\n[legacy %s] inside the storage root, already indexed' % source_tree)
        return

    print('\n[legacy %s] %s' % (source_tree, upload_root))
    for current_dir, _dirs, files in os.walk(upload_root):
        for name in files:
            file_path = os.path.join(current_dir, name)
            school_id = legacy_school_id(upload_root, file_path)
            if only_school is not None and school_id != only_school:
                continue
            category = categorize_legacy_file(source_tree, file_path)
            size = os.path.getsize(file_path)

            # Legacy files live outside the storage root, so they have no
            # storage-relative path and cannot be indexed by it. Record them
            # under a reserved prefix that encodes the owner and origin, so the
            # rows are unique, re-runnable, and clearly not servable via /media.
            relative = '%s%s/%s/%s' % (
                LEGACY_PATH_PREFIX, owner_folder(school_id), source_tree,
                os.path.relpath(file_path, upload_root).replace(os.sep, '/')
            )
            existing = SchoolFile.query.filter_by(relative_path=relative).first()
            stats.bytes_indexed += size

            if existing:
                if existing.file_size != size:
                    stats.refreshed += 1
                    if not dry_run:
                        existing.file_size = size
                continue

            print('  index   %s (%s bytes) -> %s' % (relative, size, category))
            stats.created += 1
            if not dry_run:
                record = SchoolFile(
                    shcool_id=school_id,
                    category=category,
                    relative_path=relative,
                    stored_filename=name,
                    original_filename=name,
                    file_size=size,
                    title='Legacy %s file' % source_tree,
                    linked_type='legacy',
                    active=True
                )
                db.session.add(record)


## @brief Report (and optionally remove) rows whose file is gone.
def reconcile_missing(only_school, stats, dry_run, prune):
    print('\n[rows with no file on disk]')
    query = SchoolFile.query.filter(SchoolFile.active.is_(True))
    if only_school is not None:
        query = query.filter(SchoolFile.shcool_id == only_school)

    for record in query.all():
        if record.relative_path.startswith(LEGACY_PATH_PREFIX):
            # Legacy rows are bookkeeping for files outside the tree; they have
            # no /media path to resolve, so skip the existence check.
            continue
        try:
            file_path = absolute_path(record.relative_path)
        except Exception:
            file_path = None
        if file_path and os.path.isfile(file_path):
            continue

        stats.dead += 1
        print('  missing %s (row #%s, %s bytes)' % (record.relative_path, record.id, record.file_size))
        if prune and not dry_run:
            db.session.delete(record)
            stats.pruned += 1


def main():
    parser = argparse.ArgumentParser(
        description='Reconcile the school_file storage index against the filesystem.'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Report the differences without writing anything.')
    parser.add_argument('--school', type=int,
                        help='Only reconcile this school id.')
    parser.add_argument('--skip-legacy', action='store_true',
                        help='Do not index the old STORY_UPLOAD_DIR / AUDIOBOOK_UPLOAD_DIR trees.')
    parser.add_argument('--prune', action='store_true',
                        help='Delete index rows whose file no longer exists, releasing that quota.')
    args = parser.parse_args()

    stats = IndexStats()
    if args.dry_run:
        print('DRY RUN -- nothing will be written.')

    with app.app_context():
        index_storage_tree(args.school, stats, args.dry_run)

        if not args.skip_legacy:
            index_legacy_tree(ConfigClass.STORY_UPLOAD_DIR, 'stories',
                              args.school, stats, args.dry_run)
            index_legacy_tree(ConfigClass.AUDIOBOOK_UPLOAD_DIR, 'audio-books',
                              args.school, stats, args.dry_run)

        reconcile_missing(args.school, stats, args.dry_run, args.prune)

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()
            print('\nCommitted.')

    stats.report(args.prune)
    if stats.dead and not args.prune:
        print('\nRe-run with --prune to drop the rows above and release that quota.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
