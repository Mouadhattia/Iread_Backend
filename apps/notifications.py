from datetime import datetime, timedelta
import logging

from extensions import db
from models.book import Book
from models.book_pack import Book_pack
from models.follow_pack import Follow_pack
from models.follow_session import Follow_session
from models.pack import Pack
from models.reader_notification import ReaderNotification
from models.school_pack_instance import SchoolPackInstance
from models.session import Session
from models.user import User
from models.user_shcool import User_shcool


TYPE_ICONS = {
    'online_session_created': 'fe fe-video',
    'online_session_updated': 'fe fe-video',
    'session_created': 'fe fe-calendar',
    'session_updated': 'fe fe-calendar',
    'session_deleted': 'fe fe-calendar',
    'session_follow_approved': 'fe fe-check-circle',
    'online_session_follow_approved': 'fe fe-check-circle',
    'pack_follow_approved': 'fe fe-check-circle',
    'daily_game': 'fe fe-play-circle',
    'pack_book_added': 'fe fe-book-open',
    'school_pack_created': 'fe fe-layers',
    'global_pack_created': 'fe fe-globe',
    'word_suggestion_submitted': 'fe fe-edit-3',
    'word_suggestion_approved': 'fe fe-check-circle',
    'word_suggestion_rejected': 'fe fe-x-circle',
}


def _unique_ids(user_ids):
    seen = set()
    result = []
    for user_id in user_ids or []:
        if user_id and user_id not in seen:
            seen.add(user_id)
            result.append(user_id)
    return result


def _school_id_for_pack(pack):
    if not pack:
        return None
    return pack.shcool_id


def _session_school_id(session):
    pack = Pack.query.get(session.pack_id) if session and session.pack_id else None
    return _school_id_for_pack(pack)


ONLINE_SESSION_TYPES = (
    'online_session_created', 'online_session_updated', 'online_session_follow_approved'
)
SESSION_TYPES = ONLINE_SESSION_TYPES + ('session_created', 'session_updated', 'session_follow_approved')


def _notification_link(notification_type, pack_id=None, session_id=None, book_id=None, game_type=None):
    pack_query = f'?pack_id={pack_id}' if pack_id else ''

    if notification_type in ONLINE_SESSION_TYPES and book_id and session_id:
        return f'/student/online_session/{book_id}?session_id={session_id}'

    if notification_type in SESSION_TYPES or notification_type == 'session_deleted':
        if book_id:
            return f'/student/book-details/{book_id}{pack_query}'
        return '/student/student-sessions'

    if notification_type == 'daily_game' and book_id:
        return f'/games/{book_id}'

    if notification_type == 'pack_book_added' and book_id:
        return f'/student/book-details/{book_id}{pack_query}'

    if notification_type == 'school_pack_created' and pack_id:
        return f'/student/pack-books/{pack_id}'

    if pack_id:
        return f'/student/pack-books/{pack_id}'

    return None


def serialize_reader_notification(notification):
    created_at = notification.created_at.isoformat() if notification.created_at else None
    read = notification.read_at is not None
    # Recomputed from the stored type/pack_id/session_id/book_id/game_type rather than trusting
    # notification.link as-is, so notifications created before a route mapping fix self-heal on
    # read instead of staying dead links forever (falls back to the stored value for notification
    # types _notification_link doesn't recognize, e.g. staff-facing word-suggestion links).
    computed_link = _notification_link(
        notification.type,
        pack_id=notification.pack_id,
        session_id=notification.session_id,
        book_id=notification.book_id,
        game_type=notification.game_type,
    )
    return {
        'id': notification.id,
        '_id': notification.id,
        'user_id': notification.user_id,
        'school_id': notification.shcool_id,
        'shcool_id': notification.shcool_id,
        'type': notification.type,
        'title': notification.title,
        'message': notification.message,
        'desc': notification.message,
        'link': computed_link or notification.link,
        'pack_id': notification.pack_id,
        'session_id': notification.session_id,
        'book_id': notification.book_id,
        'game_type': notification.game_type,
        'play_date': notification.play_date.isoformat() if notification.play_date else None,
        'payload': notification.payload or {},
        'is_read': read,
        'isRead': read,
        'read_at': notification.read_at.isoformat() if notification.read_at else None,
        'created_at': created_at,
        'createdAt': created_at,
        'expires_at': notification.expires_at.isoformat() if notification.expires_at else None,
        'cat': {
            'title': notification.type,
            'img': (notification.payload or {}).get('icon_url') or '',
            'icon': TYPE_ICONS.get(notification.type, 'fe fe-bell')
        }
    }


def create_notifications_for_users(
    user_ids,
    notification_type,
    title,
    message,
    link=None,
    school_id=None,
    pack_id=None,
    session_id=None,
    book_id=None,
    game_type=None,
    play_date=None,
    payload=None,
    dedupe_key=None,
    expires_at=None,
):
    user_ids = _unique_ids(user_ids)
    if not user_ids:
        return []

    existing_user_ids = set()
    if dedupe_key:
        existing_user_ids = {
            user_id for (user_id,) in
            db.session.query(ReaderNotification.user_id)
            .filter(
                ReaderNotification.user_id.in_(user_ids),
                ReaderNotification.dedupe_key == dedupe_key
            )
            .all()
        }

    notifications = []
    for user_id in user_ids:
        if user_id in existing_user_ids:
            continue
        notification = ReaderNotification(
            user_id=user_id,
            shcool_id=school_id,
            type=notification_type,
            title=title,
            message=message,
            link=link,
            pack_id=pack_id,
            session_id=session_id,
            book_id=book_id,
            game_type=game_type,
            play_date=play_date,
            payload=payload or {},
            dedupe_key=dedupe_key,
            expires_at=expires_at,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        notifications.append(notification)
    return notifications


def commit_notification_event(callback, *args, **kwargs):
    try:
        callback(*args, **kwargs)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        logging.error('Notification event failed: %s', error, exc_info=True)


def get_school_reader_ids(school_id):
    if not school_id:
        return []
    return [
        user_id for (user_id,) in
        db.session.query(User.id)
        .join(User_shcool, User_shcool.user_id == User.id)
        .filter(User_shcool.shcool_id == school_id, User.type == 'reader')
        .all()
    ]


def get_school_staff_ids(school_id):
    if not school_id:
        return []
    return [
        user_id for (user_id,) in
        db.session.query(User.id)
        .join(User_shcool, User_shcool.user_id == User.id)
        .filter(User_shcool.shcool_id == school_id, User.type.in_(['admin', 'teacher']))
        .all()
    ]


def get_all_school_staff_ids(roles=('admin', 'teacher')):
    return [
        user_id for (user_id,) in
        db.session.query(User.id)
        .join(User_shcool, User_shcool.user_id == User.id)
        .filter(User.type.in_(roles))
        .distinct()
        .all()
    ]


def get_super_admin_ids():
    return [
        user_id for (user_id,) in
        db.session.query(User.id).filter(User.type == 'super_admin').all()
    ]


def get_pack_follower_ids(pack_id):
    if not pack_id:
        return []
    return [
        user_id for (user_id,) in
        db.session.query(Follow_pack.user_id)
        .join(User, User.id == Follow_pack.user_id)
        .filter(
            Follow_pack.pack_id == pack_id,
            Follow_pack.approved.is_(True),
            User.type == 'reader'
        )
        .all()
    ]


def get_session_follower_ids(session_id):
    if not session_id:
        return []
    return [
        user_id for (user_id,) in
        db.session.query(Follow_session.user_id)
        .join(User, User.id == Follow_session.user_id)
        .filter(
            Follow_session.session_id == session_id,
            Follow_session.approved.is_(True),
            User.type == 'reader'
        )
        .all()
    ]


def get_global_pack_school_reader_ids(pack_id):
    school_ids = [
        school_id for (school_id,) in
        db.session.query(SchoolPackInstance.shcool_id)
        .filter(SchoolPackInstance.pack_id == pack_id, SchoolPackInstance.active.is_(True))
        .all()
    ]
    reader_ids = []
    for school_id in school_ids:
        reader_ids.extend(get_school_reader_ids(school_id))
    return reader_ids


def get_session_audience_ids(session):
    if not session:
        return []
    pack = Pack.query.get(session.pack_id) if session.pack_id else None
    user_ids = []
    user_ids.extend(get_session_follower_ids(session.id))
    user_ids.extend(get_pack_follower_ids(session.pack_id))
    if pack and pack.is_global_pack:
        user_ids.extend(get_global_pack_school_reader_ids(pack.id))
    return _unique_ids(user_ids)


def get_book_pack_follower_ids(school_id, book_id):
    if not school_id or not book_id:
        return []
    pack_ids = [
        pack_id for (pack_id,) in
        db.session.query(Pack.id)
        .join(Book_pack, Book_pack.pack_id == Pack.id)
        .filter(
            Book_pack.book_id == book_id,
            Pack.shcool_id == school_id,
            Pack.active.is_(True)
        )
        .all()
    ]
    user_ids = []
    for pack_id in pack_ids:
        user_ids.extend(get_pack_follower_ids(pack_id))
    return _unique_ids(user_ids)


def notify_school_pack_created(pack):
    school_id = pack.shcool_id
    create_notifications_for_users(
        get_school_reader_ids(school_id),
        'school_pack_created',
        'New reading pack',
        f'{pack.title} is now available in your school.',
        link=_notification_link('school_pack_created', pack_id=pack.id),
        school_id=school_id,
        pack_id=pack.id,
        dedupe_key=f'school-pack-created:{pack.id}'
    )


def notify_global_pack_created(pack):
    # Admins and teachers land on different dashboards, so each role needs its own
    # destination — /admin/global-packs only exists for admins, and there is no
    # teacher-facing global-packs page today, so teachers fall back to their dashboard home.
    title = 'New IRead global pack'
    message = f'IRead published a global pack: {pack.title}.'
    dedupe_key = f'global-pack-created:{pack.id}'
    create_notifications_for_users(
        get_all_school_staff_ids(roles=('admin',)),
        'global_pack_created',
        title,
        message,
        link='/admin/global-packs',
        pack_id=pack.id,
        dedupe_key=dedupe_key
    )
    create_notifications_for_users(
        get_all_school_staff_ids(roles=('teacher',)),
        'global_pack_created',
        title,
        message,
        link='/teacher-dashboard/sessions',
        pack_id=pack.id,
        dedupe_key=dedupe_key
    )


def notify_book_added_to_pack(pack, book):
    school_id = pack.shcool_id
    user_ids = get_pack_follower_ids(pack.id)
    if pack.is_global_pack:
        user_ids.extend(get_global_pack_school_reader_ids(pack.id))
    create_notifications_for_users(
        user_ids,
        'pack_book_added',
        'New book in your pack',
        f'{book.title} was added to {pack.title}.',
        link=_notification_link('pack_book_added', pack_id=pack.id, book_id=book.id),
        school_id=school_id,
        pack_id=pack.id,
        book_id=book.id,
        dedupe_key=f'pack-book-added:{pack.id}:{book.id}'
    )


def notify_session_created(session):
    location_value = getattr(session.location, 'value', session.location)
    online = location_value == 'online'
    title = 'Online session created' if online else 'New session created'
    message = f'{session.name} was added to your reading schedule.'
    if online:
        message = f'{session.name} is online and ready for video call access.'
    notification_type = 'online_session_created' if online else 'session_created'
    create_notifications_for_users(
        get_session_audience_ids(session),
        notification_type,
        title,
        message,
        link=_notification_link(
            notification_type, pack_id=session.pack_id, session_id=session.id, book_id=session.book_id
        ),
        school_id=_session_school_id(session),
        pack_id=session.pack_id,
        session_id=session.id,
        book_id=session.book_id,
        dedupe_key=f'session-created:{session.id}'
    )


def notify_session_updated(session, became_online=False):
    notification_type = 'online_session_updated' if became_online else 'session_updated'
    title = 'Session is now online' if became_online else 'Session updated'
    message = f'{session.name} was updated.'
    if became_online:
        message = f'{session.name} is now an online session.'
    create_notifications_for_users(
        get_session_audience_ids(session),
        notification_type,
        title,
        message,
        link=_notification_link(
            notification_type, pack_id=session.pack_id, session_id=session.id, book_id=session.book_id
        ),
        school_id=_session_school_id(session),
        pack_id=session.pack_id,
        session_id=session.id,
        book_id=session.book_id
    )


def notify_session_deleted(session_data, user_ids):
    create_notifications_for_users(
        user_ids,
        'session_deleted',
        'Session removed',
        f"{session_data.get('name', 'A session')} was removed from your schedule.",
        link=_notification_link(
            'session_deleted', pack_id=session_data.get('pack_id'), book_id=session_data.get('book_id')
        ),
        school_id=session_data.get('school_id'),
        pack_id=session_data.get('pack_id'),
        session_id=None,
        book_id=session_data.get('book_id'),
        payload={'deleted_session_id': session_data.get('id')}
    )


def notify_pack_follow_approved(pack, user_id):
    create_notifications_for_users(
        [user_id],
        'pack_follow_approved',
        'Pack request approved',
        f'You now have access to {pack.title}.',
        link=_notification_link('pack_follow_approved', pack_id=pack.id),
        school_id=pack.shcool_id,
        pack_id=pack.id,
        dedupe_key=f'pack-follow-approved:{pack.id}:{user_id}'
    )


def notify_session_follow_approved(session, user_id):
    location_value = getattr(session.location, 'value', session.location)
    online = location_value == 'online'
    notification_type = 'online_session_follow_approved' if online else 'session_follow_approved'
    title = 'Online session approved' if online else 'Session approved'
    message = f'You are approved for {session.name}.'
    if online:
        message = f'You are approved for {session.name} — the video call is ready to join.'
    create_notifications_for_users(
        [user_id],
        notification_type,
        title,
        message,
        link=_notification_link(
            notification_type, pack_id=session.pack_id, session_id=session.id, book_id=session.book_id
        ),
        school_id=_session_school_id(session),
        pack_id=session.pack_id,
        session_id=session.id,
        book_id=session.book_id,
        dedupe_key=f'session-follow-approved:{session.id}:{user_id}'
    )


def clear_old_daily_game_notifications(school_id, book_id, game_type, play_date):
    ReaderNotification.query.filter(
        ReaderNotification.type == 'daily_game',
        ReaderNotification.shcool_id == school_id,
        ReaderNotification.book_id == book_id,
        ReaderNotification.game_type == game_type,
        ReaderNotification.play_date != play_date
    ).delete(synchronize_session=False)


def notify_word_suggestion_submitted(suggestion, sense):
    school_name = suggestion.school.name if suggestion.school else 'A school'
    create_notifications_for_users(
        get_super_admin_ids(),
        'word_suggestion_submitted',
        'New word suggestion',
        f'{school_name} suggested a change for "{sense.lemma}" — review it in Word Suggestions.',
        link='/dashboard/word-suggestions',
        school_id=suggestion.school_id,
        payload={
            'suggestion_id': suggestion.id,
            'word_sense_id': sense.id,
            'lemma': sense.lemma,
            'suggestion_type': suggestion.suggestion_type,
        },
    )


def notify_word_suggestion_reviewed(suggestion, sense, approved):
    if approved:
        title = 'Suggestion approved'
        message = f'Your suggestion for "{sense.lemma}" was approved and is now live.'
    else:
        title = 'Suggestion rejected'
        message = f'Your suggestion for "{sense.lemma}" was rejected.'
        if suggestion.review_note:
            message += f' Note: {suggestion.review_note}'
    create_notifications_for_users(
        [suggestion.suggested_by],
        'word_suggestion_approved' if approved else 'word_suggestion_rejected',
        title,
        message,
        link='/dashboard/word-review',
        school_id=suggestion.school_id,
        payload={
            'suggestion_id': suggestion.id,
            'word_sense_id': sense.id,
            'lemma': sense.lemma,
            'suggestion_type': suggestion.suggestion_type,
        },
    )


def notify_daily_game_created(school_id, book, game_type, play_date):
    clear_old_daily_game_notifications(school_id, book.id, game_type, play_date)
    expires_at = datetime.combine(play_date, datetime.max.time()) + timedelta(days=1)
    user_ids = get_book_pack_follower_ids(school_id, book.id) or get_school_reader_ids(school_id)
    create_notifications_for_users(
        user_ids,
        'daily_game',
        'New daily game',
        f'{game_type.replace("-", " ").title()} is ready for {book.title}.',
        link=_notification_link('daily_game', book_id=book.id, game_type=game_type),
        school_id=school_id,
        book_id=book.id,
        game_type=game_type,
        play_date=play_date,
        expires_at=expires_at,
        dedupe_key=f'daily-game:{school_id}:{book.id}:{game_type}:{play_date.isoformat()}'
    )
