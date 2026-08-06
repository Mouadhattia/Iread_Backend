"""
Repair an `alembic_version` pointer that names a revision the code does not have.

The symptom is always the same line, from `flask db upgrade` in CI and from the
super-admin Database page:

    Can't locate revision identified by 'eafac216fc6e'

What it means: `alembic_version.version_num` in the database holds a revision id
that exists in no file under `migrations/versions/`. Alembic cannot place the
database on its graph, so it refuses to do anything at all -- it will not even
tell you what is pending, which is why the status endpoint 500s too.

How a database gets into that state:

  * a dump was restored that was taken from a server whose `migrations/versions/`
    held a file this repository does not. `flask db migrate` run directly on the
    server does exactly this, and the deploy workflow's `rsync --delete` then
    removes the generated file on the next deploy while the row it wrote stays
    behind in the database;
  * a migration file was deleted or rewritten in git after it had been applied
    somewhere.

Either way the schema itself is usually fine. Only the bookmark is wrong, and
the fix is to move the bookmark to a revision that exists -- *without* guessing.

This script does not guess. It reads the real schema and checks, revision by
revision along the migration chain, whether that revision's tables and columns
are actually present. The newest revision whose marker -- and every marker
before it -- is present is the revision the database is genuinely at.

Usage (from the project root, with the venv active):

    python scripts/repair_alembic_version.py              # diagnose, change nothing
    python scripts/repair_alembic_version.py --apply      # write the detected revision
    python scripts/repair_alembic_version.py --check      # CI: exit 2 if the pointer is broken
    python scripts/repair_alembic_version.py --to REV --apply   # override the detection

`--apply` only rewrites the pointer. It never touches a table. Afterwards, run
`flask db upgrade` to apply whatever is genuinely missing.

Back up the database first anyway. It costs a minute and this is the file you
will wish you had.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app import app
from extensions import db


# One marker per revision, keyed by revision id.
#
# A marker is the cheapest piece of schema that revision introduces and nothing
# before it has: a table it creates, a column it adds, or an index it builds.
# Presence of the marker means "this revision ran".
#
# Kinds:
#   ('table', name)          -- the table exists
#   ('column', table, name)  -- the table has that column
#   ('index', table, name)   -- the table has that index
#
# Order does not matter here; the chain order is read from the migration files
# themselves, so this map cannot drift out of sequence with them.
MARKERS = {
    'a335f2c4499a': ('table', 'user'),
    'cca2296b8c96': ('column', 'game_result', 'day'),
    '29ca84dad37b': ('column', 'game_result', 'completed'),
    '634199115db3': ('column', 'game_result', 'book_id'),
    '8c2f7d9e4a11': ('table', 'school_invitation_code'),
    'c7b2a8f4d1e9': ('table', 'super_admin'),
    'd4a7c9b2e6f1': ('column', 'book', 'shcool_id'),
    'e9f3b1c8a742': ('table', 'book_story'),
    'f6b8c2d4a901': ('table', 'school_book_instance'),
    'a7c9e2f4b6d8': ('table', 'school_pack_instance'),
    'c2b7e9a4d8f1': ('table', 'school_public_page'),
    'e4a1d2c9b7f6': ('column', 'session', 'jitsi_room'),
    'f9b6c3d2a8e1': ('table', 'school_game_setting'),
    'b7e4d2a9c6f3': ('column', 'school_game_setting', 'timer_enabled'),
    'c1f4e8a9b2d7': ('column', 'game_result', 'time_spent_seconds'),
    'd9a4c1b7e8f2': ('table', 'audio_book'),
    'e5b8c2a4d9f7': ('column', 'audio_book', 'book_id'),
    'f4d2c8b9a7e1': ('table', 'reader_notification'),
    'a8e7c4d2f9b1': ('index', 'audio_book_page', 'ix_audio_book_page_book_active_page'),
    'b3c9e1a7d524': ('column', 'book', 'archived'),
    'c7e2a9f04d36': ('column', 'school_public_page', 'hero_type'),
    'd3f7a1c9b5e2': ('column', 'user', 'pin_hash'),
    'e1a5f7c3d9b4': ('column', 'user', 'must_change_password'),
    'f3c8a1d92b56': ('table', 'word_sense'),
    'a4d7f1c9b358': ('table', 'word_progress'),
    'c8a3e5f1d962': ('table', 'word_sense_suggestion'),
    'd1e9a4c7f203': ('column', 'shcool', 'is_active'),
    'a1c4e7d2f9b3': ('table', 'parent'),
    'b2d5f8e3a1c6': ('column', 'user', 'account_setup_complete'),
    'c3d6a9f2b5e8': ('column', 'user', 'display_name'),
    'd4e7b0a3c9f1': ('table', 'practice_play'),
    'e5f8c1a2d740': ('table', 'certificate'),
    'b3f7d9a1c6e2': ('column', 'school_pack_instance', 'public'),
    'a1c4f8e2b7d3': ('column', 'school_public_page', 'show_public_packs'),
    'b8e3c1a7f2d9': ('table', 'admin_audit_logs'),
    'c9a2e5f81b34': ('table', 'contract_plan'),
    'd1b4f7c3a982': ('column', 'shcool', 'trial_seats'),
    'e2c8b4d1f036': ('table', 'school_file'),
    'a1c4e7b930d2': ('table', 'global_game_calendar_entry'),
}

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BROKEN_POINTER = 2


class SchemaProbe:
    """
    Reads the live schema once, up front, then answers marker questions from
    memory.

    Reflection is eager rather than lazy on purpose: the probe outlives the
    connection it was built from, so anything left unread here would fail later
    with "This Connection is closed" instead of returning an answer. Only the
    tables named in MARKERS are reflected, which is a fraction of the schema.
    """

    def __init__(self, connection):
        inspector = inspect(connection)
        self.tables = set(inspector.get_table_names())
        self._columns = {}
        self._indexes = {}

        for marker in MARKERS.values():
            table = marker[1]
            if table not in self.tables or table in self._columns:
                continue
            self._columns[table] = {
                column['name'] for column in inspector.get_columns(table)
            }
            self._indexes[table] = {
                index['name'] for index in inspector.get_indexes(table)
            }

    def has(self, marker):
        kind = marker[0]
        if kind == 'table':
            return marker[1] in self.tables
        if kind == 'column':
            return marker[2] in self._columns.get(marker[1], set())
        if kind == 'index':
            return marker[2] in self._indexes.get(marker[1], set())
        raise ValueError('Unknown marker kind: %s' % kind)


def describe(marker):
    kind = marker[0]
    if kind == 'table':
        return 'table %s' % marker[1]
    if kind == 'column':
        return 'column %s.%s' % (marker[1], marker[2])
    return 'index %s on %s' % (marker[2], marker[1])


def migration_chain():
    """Every revision from base to head, in the order an upgrade applies them."""
    from alembic.script import ScriptDirectory

    extension = app.extensions.get('migrate')
    migrate = getattr(extension, 'migrate', extension)
    script = ScriptDirectory.from_config(migrate.get_config())
    head = script.get_current_head()
    revisions = list(script.walk_revisions(base='base', head=head or 'head'))
    revisions.reverse()  # walk_revisions yields newest first
    return script, head, revisions


def revision_is_known(script, revision):
    from alembic.script.revision import ResolutionError

    if not revision:
        return False
    try:
        return script.get_revision(revision) is not None
    except (ResolutionError, KeyError):
        return False
    except Exception:
        # Older alembic raises a bare CommandError for an unresolvable id.
        return False


def read_stamped_revision(connection):
    """What the database says it is at, or None if it has never been migrated."""
    inspector = inspect(connection)
    if 'alembic_version' not in inspector.get_table_names():
        return None, False
    row = connection.execute(text('SELECT version_num FROM alembic_version')).fetchone()
    return (row[0] if row else None), True


def detect_true_revision(probe, revisions):
    """
    Walk the chain forwards. The database is at the last revision whose marker,
    and every marker before it, is present.

    Anything present *after* the first missing marker is reported separately
    rather than silently swallowed -- it means the schema was changed outside
    migrations, and stamping would then skip a migration that is genuinely
    needed.
    """
    results = []
    detected = None
    first_gap = None
    ahead = []

    for revision in revisions:
        marker = MARKERS.get(revision.revision)
        if marker is None:
            # No marker recorded (a data-only migration, or one added after this
            # script was written). Carry the previous verdict forward rather
            # than inventing one -- and keep it eligible as the stamp target, so
            # a markerless head still resolves.
            results.append((revision, None, None))
            if first_gap is None:
                detected = revision.revision
            continue

        present = probe.has(marker)
        results.append((revision, marker, present))

        if first_gap is None:
            if present:
                detected = revision.revision
            else:
                first_gap = revision.revision
        elif present:
            ahead.append(revision.revision)

    return detected, first_gap, ahead, results


def report(stamped, table_exists, known, detected, first_gap, ahead, head, results,
           verbose):
    print('Migration pointer')
    print('  alembic_version says : %s' % (
        stamped or ('<empty table>' if table_exists else '<no alembic_version table>')
    ))
    print('  code head            : %s' % (head or '<none>'))
    print('  pointer resolves     : %s' % ('yes' if known else 'NO'))
    print()

    print('Schema probe')
    if verbose:
        for revision, marker, present in results:
            if marker is None:
                state = '  ?  '
            else:
                state = ' yes ' if present else ' NO  '
            print('  [%s] %-14s %s' % (
                state, revision.revision, describe(marker) if marker else '(no marker)'
            ))
    print('  newest revision fully present : %s' % (detected or '<none>'))
    if first_gap:
        print('  first revision not applied    : %s' % first_gap)
    if ahead:
        print('  applied out of order          : %s' % ', '.join(ahead))
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Diagnose and repair a broken alembic_version pointer.'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Write the detected revision into alembic_version.'
    )
    parser.add_argument(
        '--check', action='store_true',
        help='Report only, and exit 2 if the pointer names a revision that does '
             'not exist. For use in CI before flask db upgrade.'
    )
    parser.add_argument(
        '--to', dest='target', default=None,
        help='Stamp this revision instead of the detected one. Only use this if '
             'you know why the detection is wrong.'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Rewrite the pointer even though it already resolves. Almost never '
             'the right thing to do.'
    )
    parser.add_argument(
        '--quiet', action='store_true',
        help='Skip the per-revision probe table.'
    )
    args = parser.parse_args()

    with app.app_context():
        script, head, revisions = migration_chain()

        with db.engine.connect() as connection:
            stamped, table_exists = read_stamped_revision(connection)
            known = revision_is_known(script, stamped)
            probe = SchemaProbe(connection)

        detected, first_gap, ahead, results = detect_true_revision(probe, revisions)
        report(stamped, table_exists, known, detected, first_gap, ahead, head,
               results, not args.quiet)

        if stamped and known and not args.force:
            print('The pointer is valid -- %s exists in migrations/versions/.' % stamped)
            print('Nothing to repair. Run `flask db upgrade` as normal.')
            return EXIT_OK

        if not stamped:
            # No row at all -- either no alembic_version table, or an empty one.
            # Alembic treats both as "never migrated" and will happily upgrade
            # from base, so this is not the broken-pointer failure and must not
            # be reported as one.
            if table_exists:
                print('The alembic_version table exists but holds no row.')
            else:
                print('This database has never been migrated (no alembic_version table).')
            print('Alembic reads that as "never migrated" and would upgrade from base.')
            print()
            if detected is None:
                print('The schema is empty too, which is consistent -- run `flask db upgrade`.')
                return EXIT_OK
            print('But the schema is already at %s, so upgrading from base would try'
                  % detected)
            print('to re-create tables that exist, and fail. Stamp it first.')
            print()
        elif known:
            # Only reachable with --force, which is the one way past the
            # "nothing to repair" exit above.
            print('The pointer resolves, but --force was given, so it will be')
            print('rewritten anyway. This is rarely the right thing to do.')
            print()
        else:
            # The pointer is broken: it names a revision this codebase does not
            # have.
            print('BROKEN: the database points at %r, which exists in no migration file.'
                  % stamped)
            print('Alembic cannot proceed until this is corrected -- that is the')
            print('"Can\'t locate revision identified by" error.')
            print()

        if ahead:
            print('WARNING: some revisions look applied out of order (%s).' % ', '.join(ahead))
            print('That usually means schema was changed outside migrations. Read the')
            print('probe table above before stamping anything.')
            print()

        target = args.target or detected
        if not target:
            print('Could not determine a safe revision to stamp -- not even the first')
            print('migration\'s tables are present. Do not stamp. Check you are pointed')
            print('at the right database.')
            return EXIT_ERROR

        if args.check:
            print('Suggested repair:')
            print('    python scripts/repair_alembic_version.py --apply')
            print('which would set alembic_version to %s, followed by:' % target)
            print('    flask db upgrade')
            return EXIT_BROKEN_POINTER

        if not args.apply:
            print('Would set alembic_version to %s.' % target)
            if target != head:
                pending = _pending_after(revisions, target)
                print('`flask db upgrade` would then apply %s migration(s): %s'
                      % (len(pending), ', '.join(pending) or 'none'))
            else:
                print('That is the head revision -- `flask db upgrade` would be a no-op.')
            print()
            print('Re-run with --apply to write it. Back up the database first.')
            return EXIT_OK

        if not revision_is_known(script, target):
            print('Refusing to stamp %r: it is not a revision in migrations/versions/.'
                  % target)
            return EXIT_ERROR

        with db.engine.begin() as connection:
            connection.execute(text(
                'CREATE TABLE IF NOT EXISTS alembic_version ('
                'version_num VARCHAR(32) NOT NULL, '
                'CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))'
            ))
            connection.execute(text('DELETE FROM alembic_version'))
            connection.execute(
                text('INSERT INTO alembic_version (version_num) VALUES (:revision)'),
                {'revision': target}
            )

        print('alembic_version is now %s (was %r).' % (target, stamped))
        print('Next: run `flask db upgrade` to apply what is genuinely missing.')
        return EXIT_OK


def _pending_after(revisions, target):
    seen = False
    pending = []
    for revision in revisions:
        if seen:
            pending.append(revision.revision)
        if revision.revision == target:
            seen = True
    return pending


if __name__ == '__main__':
    sys.exit(main())
