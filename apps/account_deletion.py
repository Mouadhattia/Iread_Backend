## @file
# @brief Deleting a user account and everything in the schema that points at it.
#
# Before this module every deletion path hand-listed the tables it had to clear
# first, and each list had drifted:
#
#   * `/reader/delete_account` cleared four tables. A reader who had ever
#     finished a game still had `game_result` and `practice_play` rows, MySQL
#     refused the DELETE (every FK to `user.id` in this schema is RESTRICT --
#     there is not one `ondelete` in `models/`), and the bare `except:` turned
#     the IntegrityError into a flat 500. In practice no real account could be
#     deleted at all, which is an App Store 5.1.1(v) / Play user-data failure.
#   * `/admin/delete_user` cleared nothing.
#   * `delete_super_user_dependencies` cleared eleven tables and was still
#     missing `practice_play`, `certificate`, `chat` and `reader.parent_id`.
#
# So which columns to clear is derived from `db.metadata` instead of being
# written out by hand: every FK pointing at the user identity tables is found
# at runtime, and a model added next month is seen without anyone remembering
# to come back here. What to *do* with each one is a decision, not a guess:
#
#   * listed in `OWNED_BY_USER` -> the rows are that person's own data, so
#     they are deleted. This is the list a deletion request is really about.
#   * nullable, unlisted -> the column only records who did something, so it
#     is set NULL and the row survives (`book.created_by`, `session.teacher_id`,
#     `user_logs.user_id`, ...).
#   * NOT NULL, unlisted -> refuse, naming the table (`blocking_references`).
#
# That last rule is why this is not a one-line "delete everything that points
# at the user". Six NOT NULL columns in this schema hang *school* content off
# whoever uploaded it -- `audio_book.created_by_id`, `book_story.uploaded_by`,
# `school_pack_instance.created_by`, and friends. Deleting those rows to get a
# teacher's account out of the way would take a school's audiobooks and stories
# with it, and would then fail anyway on the next FK in the chain, back to the
# same opaque 500 this module exists to remove. Refusing with a message an
# operator can act on is the only honest option.
#
# Readers and parents never author school content, so the reader-facing flow
# never meets that case; it is the admin deletion paths that do.
import logging

from sqlalchemy import inspect as sa_inspect

from config import ConfigClass
from extensions import db
from models.user import Reader, User


## @brief Raised when the account cannot be deleted. The message is safe to show.
class AccountDeletionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


## @brief The columns whose rows belong to the user, and go when they go.
#
# Everything a person accumulates by using iRead. A row here is deleted
# outright; nothing else in the schema is, so adding to this list is how a new
# per-user table joins the deletion. If you add a model with a user FK and
# forget, `blocking_references` says so by name the first time someone tries to
# delete an account that has one.
OWNED_BY_USER = frozenset({
    ('profile', 'user_id'),                     # name, phone, address, birthday
    ('user_shcool', 'user_id'),                 # school memberships
    ('school_seat_activation', 'user_id'),      # the seat they occupied
    ('follow_pack', 'user_id'),                 # pack, book and session enrolments
    ('follow_book', 'user_id'),
    ('follow_session', 'user_id'),
    ('game_result', 'user_id'),                 # Daily Run and practice history
    ('practice_play', 'user_id'),
    ('word_progress', 'user_id'),               # vocabulary evidence and CEFR state
    ('self_reported_word', 'user_id'),
    ('user_streak', 'user_id'),
    ('user_achievement', 'user_id'),            # trophies
    ('certificate', 'user_id'),                 # Reading Passport certificates
    ('reader_story_progress', 'user_id'),       # where they are in each story
    ('audio_book_progress', 'user_id'),         # and in each audiobook
    ('notification_user', 'user_id'),           # their notification feed
    ('reader_notification', 'user_id'),
    ('chat', 'sender_id'),                      # messages typed in a live session
    ('teacher_postulate', 'id'),                # their application to teach
    ('global_teacher', 'teacher_id'),           # their own global-teacher record
    ('word_sense_suggestion', 'suggested_by'),  # vocabulary they proposed
})


## @brief The tables the user identity is spread across (single-table and
# joined-table inheritance on `user`): user, reader, parent, teacher, admin,
# super_admin, assistant.
def identity_tables():
    tables = {}
    for mapper in sa_inspect(User).self_and_descendants:
        table = mapper.local_table
        if table is not None:
            tables[table.name] = table
    return tables


## @brief `(table, column)` pairs that link a subclass row to its `user` row.
# Skipped by the sweep: `db.session.delete(user)` removes both halves itself,
# and nulling or deleting them here would break the inheritance join.
def inheritance_columns():
    base = sa_inspect(User).local_table
    return {
        (table.name, 'id')
        for name, table in identity_tables().items()
        if table is not base
    }


## @brief Every FK column in the schema pointing at a user identity table.
# @return an iterator of (table, column, action) triples -- action is 'delete',
# 'null' or 'block' -- ordered so that dependent tables come before the tables
# they depend on.
def user_reference_columns():
    identity = set(identity_tables())
    inherited = inheritance_columns()

    for table in reversed(db.metadata.sorted_tables):
        for column in table.columns:
            if not any(fk.column.table.name in identity for fk in column.foreign_keys):
                continue
            if (table.name, column.name) in inherited:
                continue

            if (table.name, column.name) in OWNED_BY_USER:
                action = 'delete'
            elif column.nullable and not column.primary_key:
                action = 'null'
            else:
                action = 'block'
            yield table, column, action


## @brief Rows that stop these users being deleted, and are not theirs to lose.
#
# A NOT NULL FK that is not in OWNED_BY_USER means somebody else's record is
# hanging off this account -- usually school content they uploaded. Counted
# rather than deleted so the caller can say what is in the way.
#
# @return a {table.column: rows} map, empty when the account can be deleted.
def blocking_references(user_ids):
    blockers = {}
    for table, column, action in user_reference_columns():
        if action != 'block':
            continue
        count = db.session.execute(
            db.select(db.func.count()).select_from(table).where(column.in_(user_ids))
        ).scalar()
        if count:
            blockers[f'{table.name}.{column.name}'] = count
    return blockers


## @brief Clear every reference to these users, so the `user` rows can go.
#
# Runs at Core level (no model imports, no ORM loading) because it has to cover
# tables this module has never heard of. Does not commit -- the caller owns the
# transaction.
#
# @param user_ids ids whose references should be removed.
# @return a {table.column: rows_affected} map of what was actually touched.
# @throws AccountDeletionError if another party's records reference the account.
def purge_user_references(user_ids):
    ids = [int(user_id) for user_id in user_ids if user_id is not None]
    if not ids:
        return {}

    blockers = blocking_references(ids)
    if blockers:
        raise AccountDeletionError(
            'This account still owns content that other people use: '
            + ', '.join(f'{count} in {name}' for name, count in blockers.items())
            + '. Reassign or remove it first.',
            status=409
        )

    touched = {}
    for table, column, action in user_reference_columns():
        if action == 'delete':
            statement = table.delete().where(column.in_(ids))
        elif action == 'null':
            statement = table.update().where(column.in_(ids)).values({column.name: None})
        else:
            continue

        result = db.session.execute(statement)
        if result.rowcount:
            touched[f'{table.name}.{column.name}'] = result.rowcount

    return touched


## @brief The profiles that go away when `user` is deleted.
#
# A household is one email address: a Parent row plus up to three child Reader
# rows sharing that email and password (see `create_account`). The Parent owns
# the household -- it holds the billing client id, and a child profile is
# reachable only through it -- so deleting a Parent deletes the children too.
# Deleting one child Reader deletes only that child.
#
# @return (profiles_to_delete, children) -- `children` is the extra profiles
# beyond `user`, so callers can name them in a confirmation prompt.
def household_profiles(user):
    if getattr(user, 'type', None) != 'parent':
        return [user], []

    children = Reader.query.filter_by(parent_id=user.id).all()
    return [user] + children, children


## @brief Best-effort removal of the quiz microservice's copy of a reader.
#
# The reader's quiz answers live in quiz_api's MongoDB keyed by `User.quiz_id`,
# outside this database entirely, so deleting the MySQL row alone would leave
# them behind. Failures are logged and swallowed: a deletion the user has
# already confirmed must not be blocked by another service being down. Anything
# left behind is orphaned data with no route back to a person.
def forget_quiz_accounts(quiz_ids):
    import requests

    for quiz_id in [quiz_id for quiz_id in quiz_ids if quiz_id]:
        try:
            response = requests.delete(
                f'{ConfigClass.QUIZ_API}user/{quiz_id}', timeout=10
            )
            if response.status_code >= 400:
                logging.warning(
                    'Quiz account %s not deleted (status %s)', quiz_id, response.status_code
                )
        except Exception as error:
            logging.warning('Quiz account %s not deleted: %s', quiz_id, error)


## @brief Confirm to the address on the account that the deletion happened.
#
# Sent after the commit, to the email the account used to have -- the one place
# left that can say so, and the only signal a household would get if someone
# else in it deleted the account. Best-effort like every other send here: the
# account is already gone, and a mail failure must not be reported as one.
#
# @param email the address the deleted account used.
# @param profiles [{name, role}] of every profile removed.
def send_account_deleted_email(email, profiles):
    from apps.emailer import send_html_email

    names = [profile.get('name') for profile in profiles if profile.get('name')]
    return send_html_email(
        'Your iRead account has been deleted',
        [email],
        'account_deleted.html',
        category='Account deletion email',
        profile_names=names,
        is_household=len(names) > 1,
        support_url=f'{ConfigClass.FRONT_URL}/contact-us/',
        site_url=ConfigClass.FRONT_URL
    )


## @brief Delete these user rows and everything that references them.
#
# Does not commit; the caller decides what else belongs in the transaction.
#
# @param users the User rows to delete (see household_profiles).
# @return a {table.column: rows} map describing what the sweep cleared.
def delete_users(users):
    from apps.seats import release_all_seats

    user_ids = [user.id for user in users]

    # Hand every seat back to its school before the activation rows are swept,
    # so the school's used-seat count is decremented rather than silently
    # dropping to a lower number the next time it is recomputed.
    for user_id in user_ids:
        release_all_seats(user_id, reason='account_deleted')
    db.session.flush()

    touched = purge_user_references(user_ids)

    # The sweep ran as Core DML, so the session's loaded objects (and their
    # cascade collections) are stale. Expire them or the ORM delete below will
    # try to cascade to rows it still believes exist.
    db.session.expire_all()

    for user in users:
        db.session.delete(db.session.get(User, user.id))

    return touched
