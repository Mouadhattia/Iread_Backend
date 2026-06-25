import time
import uuid
from urllib.parse import quote

import jwt

from config import ConfigClass
from extensions import db
from models.session import Location


def get_session_location_value(session):
    location = getattr(session, 'location', None)
    if isinstance(location, Location):
        return location.value
    if location is None:
        return None
    return str(location).lower()


def is_online_session(session):
    return get_session_location_value(session) == Location.ONLINE.value


def get_jitsi_domain():
    return ConfigClass.JITSI_DOMAIN


def build_jitsi_room(session):
    if not getattr(session, 'id', None):
        db.session.flush()
    suffix = (getattr(session, 'token', None) or uuid.uuid4().hex)[:8]
    return f'iread-session-{session.id}-{suffix}'


def build_jitsi_meet_url(room, token=None):
    url = f'https://{get_jitsi_domain()}/{quote(room)}'
    if token:
        url = f'{url}?jwt={token}'
    return url


def ensure_jitsi_room(session):
    if not is_online_session(session):
        if getattr(session, 'jitsi_room', None):
            old_room_url = build_jitsi_meet_url(session.jitsi_room)
            if getattr(session, 'meet_link', None) == old_room_url:
                session.meet_link = None
            session.jitsi_room = None
        return None

    if not getattr(session, 'jitsi_room', None):
        session.jitsi_room = build_jitsi_room(session)
    session.meet_link = build_jitsi_meet_url(session.jitsi_room)
    return session.jitsi_room


def generate_jitsi_token(user, room, is_moderator):
    now = int(time.time())
    payload = {
        'aud': ConfigClass.JITSI_AUD,
        'iss': ConfigClass.JITSI_APP_ID,
        'sub': ConfigClass.JITSI_DOMAIN,
        'room': room,
        'nbf': now - 10,
        'exp': now + ConfigClass.JITSI_TOKEN_TTL_SECONDS,
        'context': {
            'user': {
                'id': str(uuid.uuid4()),
                'name': user.username,
                'email': user.email,
                'moderator': bool(is_moderator)
            },
            'features': {
                'livestreaming': True,
                'transcription': False,
                'recording': True
            }
        }
    }
    return jwt.encode(payload, ConfigClass.CALL_JWT_SECRET, algorithm='HS256')


def serialize_jitsi_call(session, user, is_moderator):
    room = ensure_jitsi_room(session)
    token = generate_jitsi_token(user, room, is_moderator)
    return {
        'session_id': session.id,
        'room': room,
        'domain': get_jitsi_domain(),
        'token': token,
        'url': build_jitsi_meet_url(room, token),
        'meet_link': build_jitsi_meet_url(room),
        'is_moderator': bool(is_moderator),
        'location': get_session_location_value(session)
    }
