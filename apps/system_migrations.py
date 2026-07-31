## @file
# @brief Inspect and apply database migrations from the super-admin UI.
#
# Why this exists: the production host is deployed over FTP with no shell, so
# `flask db upgrade` cannot be run there. Without this, applying a migration
# means hand-pasting generated SQL into phpMyAdmin, which is error-prone and
# easy to do half-way.
#
# This is a privileged operation reachable over HTTP, so it is deliberately
# constrained:
#
#   * super-admin only, on top of the normal session auth;
#   * OFF unless ConfigClass.ALLOW_WEB_MIGRATIONS is explicitly enabled, so it
#     is not a permanent piece of attack surface;
#   * upgrade only -- never downgrade, which is the destructive direction;
#   * it always reports what *would* run before anything is applied;
#   * every run is written to the admin audit log.
#
# Turn ALLOW_WEB_MIGRATIONS back off once the deploy is done.
import logging
from io import StringIO

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app

from config import ConfigClass
from extensions import db


class MigrationsDisabled(Exception):
    """Raised when web migrations are not enabled on this server."""


class UnknownRevision(Exception):
    """
    Raised when the database points at a revision this codebase does not have.

    This is its own failure rather than a generic error because the remedy is
    completely different from "a migration failed": nothing is wrong with the
    schema, the bookmark is wrong, and running an upgrade cannot fix it.
    """


##
# @brief The message an operator needs when the pointer is unresolvable.
#
# Kept in one place so the API, the audit trail and the console script all say
# the same thing.
def unknown_revision_message(revision):
    return (
        "The database is stamped with revision '%s', which exists in no file "
        "under migrations/versions/. Alembic cannot place the database on its "
        "migration graph, so it will not report or apply anything until this is "
        "corrected. This usually means a dump was restored from a server that "
        "had a migration file this codebase does not, or that an applied "
        "migration was later deleted from git. The schema itself is normally "
        "fine -- only the pointer is wrong. Diagnose and repair it with: "
        "python scripts/repair_alembic_version.py" % revision
    )


def web_migrations_enabled():
    return bool(getattr(ConfigClass, 'ALLOW_WEB_MIGRATIONS', False))


def _alembic_config():
    extension = current_app.extensions.get('migrate')
    if extension is None:
        raise RuntimeError('Flask-Migrate is not initialised on this app.')
    migrate = getattr(extension, 'migrate', extension)
    return migrate.get_config()


##
# @brief The revision the database currently reports.
# @return the revision string, or None if the database has never been migrated.
def get_current_revision():
    with db.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


##
# @brief What the code expects the database to be at.
def get_head_revision():
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


##
# @brief Whether a revision id actually exists in migrations/versions/.
#
# Everything else here walks the migration graph, and every one of those walks
# raises if the starting point is not on it. Checking first is what turns an
# unreadable 500 into a status the UI can explain.
def revision_exists(script, revision):
    if not revision:
        return False
    try:
        return script.get_revision(revision) is not None
    except Exception:
        # alembic raises ResolutionError here, but older versions raise a bare
        # CommandError; either way the answer is the same.
        return False


##
# @brief Migrations that exist in the code but are not yet applied, oldest
# first -- i.e. exactly what an upgrade would run.
#
# Returns [] when the database's revision is unresolvable: there is no honest
# answer to "what is pending" from a starting point that is not on the graph,
# and an empty list next to unknown_revision=True is less misleading than an
# exception the caller has to translate.
def get_pending_revisions():
    script = ScriptDirectory.from_config(_alembic_config())
    current = get_current_revision()
    head = script.get_current_head()

    if current == head:
        return []

    if current is not None and not revision_exists(script, current):
        return []

    pending = []
    for revision in script.walk_revisions(base=current or 'base', head=head or 'head'):
        # walk_revisions yields newest first and includes the current revision
        # itself when one is set; that one is already applied.
        if revision.revision == current:
            continue
        pending.append({
            'revision': revision.revision,
            'down_revision': revision.down_revision,
            'description': revision.doc,
        })
    pending.reverse()
    return pending


##
# @brief Everything the UI needs to decide whether to offer the button.
def get_migration_status():
    script = ScriptDirectory.from_config(_alembic_config())
    current = get_current_revision()
    head = script.get_current_head()
    unknown = current is not None and not revision_exists(script, current)
    pending = [] if unknown else get_pending_revisions()
    return {
        'current_revision': current,
        'head_revision': head,
        # An unresolvable revision is never "up to date", whatever it happens to
        # equal -- the state is unknown, not good.
        'up_to_date': current == head and not unknown,
        'pending': pending,
        'pending_count': len(pending),
        'enabled': web_migrations_enabled(),
        'never_migrated': current is None,
        'unknown_revision': unknown,
        'diagnosis': unknown_revision_message(current) if unknown else None,
    }


##
# @brief Apply every pending migration, up to head.
#
# Alembic reports progress through the logging module rather than by returning
# anything useful, so a handler is attached for the duration of the run and the
# captured output is handed back to the caller -- otherwise a failure halfway
# through would leave the operator with a bare 500 and no idea which revision
# broke.
#
# @return a dict describing what changed, including the captured log.
def run_upgrade():
    if not web_migrations_enabled():
        raise MigrationsDisabled(
            'Web migrations are disabled. Set ALLOW_WEB_MIGRATIONS=1 in the '
            'server environment to enable them, and turn it off afterwards.'
        )

    from flask_migrate import upgrade as flask_migrate_upgrade

    before = get_current_revision()

    # Stop before alembic does, so the operator gets the remedy instead of
    # "Can't locate revision identified by ...". An upgrade cannot fix this and
    # would only produce a confusing failure.
    script = ScriptDirectory.from_config(_alembic_config())
    if before is not None and not revision_exists(script, before):
        raise UnknownRevision(unknown_revision_message(before))

    planned = get_pending_revisions()

    if not planned:
        return {
            'applied': [],
            'revision_before': before,
            'revision_after': before,
            'log': 'Database is already up to date; nothing to apply.',
            'changed': False,
        }

    buffer = StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(message)s'))
    alembic_logger = logging.getLogger('alembic')
    previous_level = alembic_logger.level
    alembic_logger.addHandler(handler)
    alembic_logger.setLevel(logging.INFO)

    try:
        flask_migrate_upgrade()
    finally:
        alembic_logger.removeHandler(handler)
        alembic_logger.setLevel(previous_level)

    after = get_current_revision()
    return {
        'applied': planned,
        'revision_before': before,
        'revision_after': after,
        'log': buffer.getvalue().strip(),
        'changed': before != after,
    }
