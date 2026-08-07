"""
Find out why POST /admin/global-books/<id>/games/<game>/calendar/generate 500s.

The endpoint answers `{'message': 'Internal server error'}` and nothing else --
the real exception only ever reaches the process log. On a server where reading
that log is awkward, this script reproduces the same call in the same app
context and prints the traceback, plus the schema facts that explain it.

It writes nothing. The generate runs inside a transaction that is always rolled
back, so it is safe to run against production.

Scope, learned the hard way: this exercises the *service* layer, not the route.
The first production 500 it was written for turned out to be in the route body
above `generate_calendar_entries` -- a shadowed `parse_bool_value` -- so this
script reported everything healthy. If it does that again, the fault is in the
route, and `pm2 logs iread --err` is the faster answer.

Usage (from the project root, with the venv active). Keep both streams -- the
report goes to stdout and the tracebacks to stderr:

    python scripts/diagnose_global_game_calendar.py 2>&1 | tee /tmp/gamecal.txt
    python scripts/diagnose_global_game_calendar.py --book 1 --game bee-genius

What it checks, in the order a request hits them:

  1. the migration pointer, and whether a1c4e7b930d2 actually ran;
  2. the two tables the feature needs -- that they exist, are real tables
     rather than views, carry AUTO_INCREMENT on `id`, and hold no NOT NULL
     column the model does not know how to fill. Each of those breaks INSERT
     while leaving SELECT working, which is exactly the reported symptom:
     the book list and the calendar read fine, only generate fails;
  3. that the book is schedulable and has text to generate from;
  4. an INSERT of one row, rolled back -- this catches privileges, a full
     disk, and a foreign key pointing somewhere unexpected;
  5. the real generate_calendar_entries() call, rolled back.
"""
import argparse
import os
import sys
import traceback
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app import app
from extensions import db

from apps.game_calendar import (
    SUPPORTED_GAME_TYPES,
    GameCalendarError,
    generate_calendar_entries,
)
from models.book import Book
from models.book_text import Book_text
from models.global_game_calendar_entry import GlobalGameCalendarEntry
from models.global_game_setting import GlobalGameSetting


REVISION = 'a1c4e7b930d2'

# What the model will actually send on an INSERT. Anything NOT NULL in the live
# table and absent from this set has no value to receive and no default to fall
# back on, so every INSERT fails while every SELECT keeps working.
MODEL_COLUMNS = {
    'global_game_calendar_entry': {
        'id', 'book_id', 'game_type', 'play_date', 'words',
        'created_at', 'updated_at',
    },
    'global_game_setting': {
        'id', 'game_type', 'timer_seconds', 'timer_enabled', 'max_hints',
        'created_at', 'updated_at',
    },
}


def heading(title):
    print()
    print(title)
    print('-' * len(title))


def show_environment(connection):
    heading('Environment')
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if '@' in uri:
        # Mask the password, keep the host and database name -- those are the
        # parts worth confirming when a server turns out to be pointed at the
        # wrong database.
        scheme, _, rest = uri.partition('://')
        creds, _, hostpart = rest.rpartition('@')
        user = creds.split(':')[0]
        uri = '%s://%s:***@%s' % (scheme, user, hostpart)
    print('  database uri  : %s' % uri)
    for label, statement in (
        ('server        ', 'SELECT VERSION()'),
        ('sql_mode      ', 'SELECT @@sql_mode'),
        ('connected user', 'SELECT CURRENT_USER()'),
    ):
        try:
            print('  %s: %s' % (label, connection.execute(text(statement)).scalar()))
        except Exception as error:
            print('  %s: unavailable (%s)' % (label, error))


def show_migration_pointer(connection):
    heading('Migration pointer')
    inspector = inspect(connection)
    if 'alembic_version' not in inspector.get_table_names():
        print('  alembic_version table is missing -- this database was not built by migrations')
        return
    stamped = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
    print('  alembic_version says : %s' % stamped)
    print('  %s applied : %s' % (
        REVISION,
        'yes' if 'global_game_calendar_entry' in inspector.get_table_names() else 'NO -- run flask db upgrade'
    ))


def check_table(connection, table_name):
    """Report anything about the live table that would break INSERT alone."""
    inspector = inspect(connection)
    if table_name not in inspector.get_table_names():
        if table_name in inspector.get_view_names():
            print('  %s: exists as a VIEW, not a table -- SELECT works, INSERT cannot' % table_name)
        else:
            print('  %s: MISSING' % table_name)
        return

    columns = inspector.get_columns(table_name)
    by_name = {column['name']: column for column in columns}
    print('  %s: present (%d columns)' % (table_name, len(columns)))

    identity = by_name.get('id') or {}
    if not identity.get('autoincrement'):
        print('    id is NOT AUTO_INCREMENT -- every INSERT that omits id fails under strict mode')

    unfillable = [
        name for name, column in by_name.items()
        if name not in MODEL_COLUMNS[table_name]
        and not column.get('nullable', True)
        and column.get('default') is None
    ]
    if unfillable:
        print('    NOT NULL columns the model never sets, with no default: %s' % ', '.join(sorted(unfillable)))
        print('    (a table copied from game_calendar_entry keeps shcool_id, which does this)')

    missing = sorted(MODEL_COLUMNS[table_name] - set(by_name))
    if missing:
        print('    columns the model expects but the table lacks: %s' % ', '.join(missing))

    try:
        create_sql = connection.execute(text('SHOW CREATE TABLE `%s`' % table_name)).fetchone()[1]
        print('    --- SHOW CREATE TABLE ---')
        for line in create_sql.splitlines():
            print('    %s' % line)
    except Exception as error:
        print('    SHOW CREATE TABLE failed: %s' % error)


def check_book(book_id):
    heading('Book %s' % book_id)
    book = db.session.get(Book, book_id)
    if not book:
        print('  no book with that id')
        return None
    print('  title            : %s' % book.title)
    print('  active           : %s' % getattr(book, 'active', None))
    print('  is_platform_book : %s' % getattr(book, 'is_platform_book', None))

    rows = Book_text.query.filter_by(book_id=book_id).all()
    if not rows:
        print('  book text        : NONE -- generate answers 404 BOOK_TEXT_NOT_FOUND, not 500')
        return book
    lengths = ', '.join(str(len(row.text or '')) for row in rows)
    print('  book text        : %d row(s), lengths %s' % (len(rows), lengths))
    return book


def try_single_insert(book_id):
    """One row, then roll back. Isolates privileges, disk and foreign keys."""
    heading('INSERT probe (rolled back)')
    try:
        db.session.add(GlobalGameCalendarEntry(
            book_id=book_id,
            game_type='bee-genius',
            play_date=date(1970, 1, 1),
            words=['probe', 'probe', 'probe'],
        ))
        db.session.flush()
        print('  INSERT succeeded')
    except Exception:
        print('  INSERT FAILED:')
        traceback.print_exc()
    finally:
        db.session.rollback()


def try_generate(book_id, game_types, start_date):
    heading('generate_calendar_entries (rolled back)')
    for game_type in game_types:
        try:
            result = generate_calendar_entries(None, book_id, game_type, start_date)
            db.session.flush()
            print('  %-15s ok -- would create %s day(s), %s to %s' % (
                game_type, result['created'], result['start_date'], result['end_date']))
        except GameCalendarError as error:
            print('  %-15s refused: %s (%s -> HTTP %s)' % (
                game_type, error.message, error.code, error.status_code))
        except Exception:
            print('  %-15s RAISED -- this is the 500:' % game_type)
            traceback.print_exc()
        finally:
            db.session.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', type=int, default=1, help='book id from the failing URL (default 1)')
    parser.add_argument('--game', action='append', dest='games',
                        help='game type to test; repeatable, defaults to all four')
    parser.add_argument('--start-date', default=date.today().isoformat(),
                        help='start date to generate from (default today)')
    args = parser.parse_args()
    game_types = args.games or list(SUPPORTED_GAME_TYPES)

    with app.app_context():
        connection = db.session.connection()
        show_environment(connection)
        show_migration_pointer(connection)

        heading('Tables')
        check_table(connection, 'global_game_calendar_entry')
        check_table(connection, 'global_game_setting')

        heading('Platform game settings')
        try:
            settings = GlobalGameSetting.query.all()
            print('  configured: %s' % (
                ', '.join(sorted(setting.game_type for setting in settings)) or 'none'
            ))
        except Exception as error:
            # Reported, not raised: the checks below are the ones that identify
            # the 500, and a missing settings table must not hide them.
            db.session.rollback()
            print('  could not read: %s' % str(error).splitlines()[0])

        book = check_book(args.book)
        if book is None:
            return 1

        try_single_insert(args.book)
        try_generate(args.book, game_types, args.start_date)

    print()
    print('Nothing above was written -- every transaction was rolled back.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
