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
# @brief Migrations that exist in the code but are not yet applied, oldest
# first -- i.e. exactly what an upgrade would run.
def get_pending_revisions():
    script = ScriptDirectory.from_config(_alembic_config())
    current = get_current_revision()
    head = script.get_current_head()

    if current == head:
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
    current = get_current_revision()
    head = get_head_revision()
    pending = get_pending_revisions()
    return {
        'current_revision': current,
        'head_revision': head,
        'up_to_date': current == head,
        'pending': pending,
        'pending_count': len(pending),
        'enabled': web_migrations_enabled(),
        'never_migrated': current is None,
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
