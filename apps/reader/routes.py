## @file
# Blueprint for user readers' authentication.
# Contains routes and functions related to user authentication.
from datetime import datetime, timedelta
import os
from flask import Blueprint,request,jsonify,render_template, redirect,make_response,session,send_file
from flask_bcrypt import Bcrypt
from models.user import User,Reader,Teacher,Admin,SuperAdmin
from models.game_result import Game_result, GameEnum
from models.teacher_postulate import Teacher_postulate
from models.pack import Pack
from models.follow_pack import Follow_pack
from models.Follow_book import Follow_book
from models.notification_user import Notification_user
from models.book import Book
from models.user_shcool import User_shcool
from models.shcool import Shcool
from models.school_invitation_code import SchoolInvitationCode
from models.book_story import BookStory
from models.reader_story_progress import ReaderStoryProgress
from models.reader_notification import ReaderNotification
from models.school_book_instance import SchoolBookInstance
from models.school_pack_instance import SchoolPackInstance
from models.school_public_page import (
    SchoolPublicPage,
    default_school_public_sections,
    generate_unique_school_slug,
    normalize_school_slug
)
from models.profile import Profile
from models.book_pack import Book_pack
from models.session import Session
from models.book_text import Book_text
from models.follow_session import Follow_session
from models.audio_book import AudioBook, AudioBookPage
from apps.main.email import generate_confirmed_token,reader_confirm_token,generate_email_change_token,confirm_email_change_token
from apps.jitsi import is_online_session, serialize_jitsi_call
from apps.notifications import serialize_reader_notification
from apps.game_calendar import (
    GameCalendarError,
    game_error_response,
    get_player_game_payload,
    parse_optional_play_date,
    split_legacy_words_from_text,
)
from extensions import mail,login_manager,db
from flask_mail import Message
from config import ConfigClass
from flask_login import login_user,logout_user,current_user,login_required
from functools import wraps
import logging
import urllib.request,json,http.cookiejar
from werkzeug.utils import secure_filename
from models.code import Code ,StatusEnum 
from models.user_log import UserLog
from geoip2.database import Reader as Beader
import uuid
import requests
import time
from user_agents import parse
from sqlalchemy.orm import aliased
from flask import jsonify
from sqlalchemy import exists, and_, or_
import secrets 

from sqlalchemy.sql import func





captcha_storage = {}
## @brief Blueprint for user readers' authentication.
# This blueprint contains routes and functions related to user authentication, including login, registration,
# password hashing, and email verification.
reader = Blueprint('reader', __name__, url_prefix='/reader')


## @brief Create an instance of the Bcrypt class from flask_bcrypt for password hashing.
bcrypt=Bcrypt()

# Initialize the login manager for the authentication blueprint.
login_manager.init_app(reader)


def get_reader_notification_query():
    return (
        ReaderNotification.query
        .filter(
            ReaderNotification.user_id == current_user.id,
            or_(
                ReaderNotification.expires_at.is_(None),
                ReaderNotification.expires_at >= datetime.utcnow()
            )
        )
    )


def parse_notification_pagination():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except (TypeError, ValueError):
        page = 1
        per_page = 20
    return max(page, 1), min(max(per_page, 1), 100)


@reader.route('/notifications', methods=['GET'])
@login_required
def get_reader_notifications():
    try:
        page, per_page = parse_notification_pagination()
        query = get_reader_notification_query()
        notification_type = request.args.get('type')
        if notification_type:
            query = query.filter(ReaderNotification.type == notification_type)
        if str(request.args.get('unread', '')).lower() in ['1', 'true', 'yes']:
            query = query.filter(ReaderNotification.read_at.is_(None))

        total = query.order_by(None).count()
        notifications = (
            query
            .order_by(ReaderNotification.created_at.desc(), ReaderNotification.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        pages = (total + per_page - 1) // per_page if total else 0
        unread_count = get_reader_notification_query().filter(ReaderNotification.read_at.is_(None)).count()
        return jsonify({
            'notifications': [serialize_reader_notification(notification) for notification in notifications],
            'unread_count': unread_count,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pages,
                'has_next': page < pages,
                'has_prev': page > 1
            }
        }), 200
    except Exception as error:
        logging.error('Unable to get reader notifications: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/notifications/unread-count', methods=['GET'])
@login_required
def get_reader_notifications_unread_count():
    try:
        unread_count = get_reader_notification_query().filter(ReaderNotification.read_at.is_(None)).count()
        return jsonify({'unread_count': unread_count}), 200
    except Exception as error:
        logging.error('Unable to count reader notifications: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/notifications/<int:notification_id>', methods=['GET'])
@login_required
def get_reader_notification(notification_id):
    try:
        notification = get_reader_notification_query().filter(ReaderNotification.id == notification_id).first()
        if not notification:
            return jsonify({'message': 'Notification not found'}), 404
        return jsonify({'notification': serialize_reader_notification(notification)}), 200
    except Exception as error:
        logging.error('Unable to get reader notification: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/notifications/<int:notification_id>/read', methods=['PUT', 'PATCH'])
@login_required
def mark_reader_notification_read(notification_id):
    try:
        notification = get_reader_notification_query().filter(ReaderNotification.id == notification_id).first()
        if not notification:
            return jsonify({'message': 'Notification not found'}), 404
        if notification.read_at is None:
            notification.read_at = datetime.utcnow()
            db.session.commit()
        return jsonify({'notification': serialize_reader_notification(notification)}), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to mark reader notification read: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/notifications/read-all', methods=['PUT', 'PATCH'])
@login_required
def mark_all_reader_notifications_read():
    try:
        now = datetime.utcnow()
        notifications = get_reader_notification_query().filter(ReaderNotification.read_at.is_(None)).all()
        for notification in notifications:
            notification.read_at = now
        db.session.commit()
        return jsonify({'message': 'Notifications marked as read', 'updated': len(notifications)}), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to mark reader notifications read: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_reader_notification(notification_id):
    try:
        notification = get_reader_notification_query().filter(ReaderNotification.id == notification_id).first()
        if not notification:
            return jsonify({'message': 'Notification not found'}), 404
        db.session.delete(notification)
        db.session.commit()
        return jsonify({'message': 'Notification deleted'}), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to delete reader notification: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500






## @brief Load a user from the SQL database based on their unique user_id.
#
# This function is used by the login manager to load a user from the SQL database based on their unique user_id.
# The function accepts a user_id as a parameter and retrieves the corresponding user from the database using the User.query.get() method.
#
# @param user_id: The unique identifier of the user.
# @return: The user object corresponding to the provided user_id, or None if the user with the specified ID is not found.


def split_words_into_stages(words, game_types, difficulty="hard"):
    game_data = {}

    for game in game_types:
        stages = [words[i:i+3] for i in range(0, len(words), 3)]  # Split words into stages of 3

        game_data[game] = {
            "stages": stages,
            "difficulty": difficulty,
            "words": words
        }

    return game_data


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


## @brief Check if the email entered by the user already exists in the database.
#
# This function verifies if the email entered by the user already exists in the database.
# The function accepts an email as a parameter and checks if there is a user with the same email using the User.query.filter_by() method.
#
# @param email: The email entered by the user.
# @return: True if the email exists in the database, and False otherwise.
def user_email_exist(email):
    user=User.query.filter_by(email=email).first()
    if user :
        return True
    else:
        return False

def get_cookies():

    cookie_jar = http.cookiejar.CookieJar()
    cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
    opener = urllib.request.build_opener(cookie_handler)  

    return opener  

def get_geolite_city_path():
    return (
        os.environ.get('GEOLITE_CITY_DB_PATH')
        or os.path.join(os.getcwd(), 'GeoLite2-City', 'GeoLite2-City.mmdb')
    )

def generate_unique_user_id():
    return str(uuid.uuid4())  

def normalize_invitation_code(code):
    if not code:
        return None
    return str(code).strip().upper()

def add_user_to_school(user_id, school_id):
    if User_shcool.query.filter_by(user_id=user_id, shcool_id=school_id).first():
        return False
    db.session.add(User_shcool(user_id=user_id, shcool_id=school_id))
    return True

def get_user_schools(user_id):
    memberships = User_shcool.query.filter_by(user_id=user_id).all()
    schools = []
    for membership in memberships:
        school = Shcool.query.get(membership.shcool_id)
        if school:
            schools.append({'id': school.id, 'name': school.name})
    return schools

def get_valid_school_invitation(code):
    normalized_code = normalize_invitation_code(code)
    if not normalized_code:
        return None, 'Invitation code is required', 400

    invitation_code = SchoolInvitationCode.query.filter_by(code=normalized_code).first()
    if not invitation_code:
        return None, 'Invitation code not found', 404
    if not invitation_code.active:
        return None, 'Invitation code is inactive', 400
    if invitation_code.max_uses is not None and invitation_code.used_count >= invitation_code.max_uses:
        return None, 'Invitation code has reached its usage limit', 400

    school = Shcool.query.get(invitation_code.shcool_id)
    if not school:
        return None, 'Invitation school not found', 404

    return invitation_code, None, None

def redeem_school_invitation_for_user(invitation_code, user_id):
    added = add_user_to_school(user_id, invitation_code.shcool_id)
    if added:
        invitation_code.used_count = (invitation_code.used_count or 0) + 1
    return added

def serialize_school(school, joined=False):
    return {
        'id': school.id,
        'name': school.name,
        'joined': joined
    }

def build_school_public_url(slug):
    relative_url = f'/schools/{slug}'
    frontend_url = (ConfigClass.FRONT_URL or '').rstrip('/')
    return relative_url, f'{frontend_url}{relative_url}' if frontend_url else relative_url

def get_or_create_school_public_page(school):
    page = SchoolPublicPage.query.filter_by(shcool_id=school.id).first()
    if page:
        return page

    page = SchoolPublicPage(
        shcool_id=school.id,
        slug=generate_unique_school_slug(school.name),
        active=True,
        headline=f'Read with {school.name}',
        description=f'Welcome to {school.name} on IREAD.',
        sections=default_school_public_sections(school.name)
    )
    db.session.add(page)
    db.session.flush()
    return page

def serialize_public_school_page(page):
    school = page.school or Shcool.query.get(page.shcool_id)
    relative_url, full_url = build_school_public_url(page.slug)
    sections = page.sections or default_school_public_sections(school.name if school else 'this school')
    return {
        'school_id': page.shcool_id,
        'shcool_id': page.shcool_id,
        'school_name': school.name if school else None,
        'slug': page.slug,
        'active': page.active,
        'logo': page.logo,
        'cover_image': page.cover_image,
        'headline': page.headline,
        'description': page.description,
        'sections': sections,
        'hero_type': page.hero_type,
        'public_url': relative_url,
        'full_public_url': full_url
    }

def get_school_public_page_by_slug(slug, active_only=True):
    normalized_slug = normalize_school_slug(slug)
    query = SchoolPublicPage.query.filter(func.lower(SchoolPublicPage.slug) == normalized_slug.lower())
    if active_only:
        query = query.filter(SchoolPublicPage.active.is_(True))
    return query.first()

def user_belongs_to_school(user_id, school_id):
    if not user_id or not school_id:
        return False
    return User_shcool.query.filter_by(user_id=user_id, shcool_id=school_id).first() is not None

def set_selected_school_context(school_id):
    session['selected_school_id'] = school_id

def get_published_audio_book_ids_by_book(book_ids, school_id):
    if not book_ids:
        return {}
    query = (
        db.session.query(AudioBook.book_id, AudioBook.id, AudioBook.updated_at)
        .join(AudioBookPage, AudioBookPage.audio_book_id == AudioBook.id)
        .filter(
            AudioBook.book_id.in_(book_ids),
            AudioBook.active.is_(True),
            AudioBook.status == 'published',
            AudioBookPage.active.is_(True),
            AudioBookPage.alignment_status == 'approved'
        )
    )
    if school_id:
        query = query.filter(or_(AudioBook.shcool_id == school_id, AudioBook.shcool_id.is_(None)))
    else:
        query = query.filter(AudioBook.shcool_id.is_(None))

    audio_map = {}
    for book_id, audio_book_id, updated_at in query.distinct().order_by(AudioBook.updated_at.desc()).all():
        audio_map.setdefault(book_id, audio_book_id)
    return audio_map

def serialize_book_for_pack(book, audio_map=None):
    platform_book = bool(getattr(book, 'is_platform_book', False))
    audio_book_id = (audio_map or {}).get(book.id)
    return {
        'id': book.id,
        'title': book.title,
        'author': book.author,
        'release_date': book.release_date.isoformat() if book.release_date else None,
        'page_number': book.page_number,
        'category': book.category,
        'desc': book.desc,
        'img': book.img,
        'is_platform_book': platform_book,
        'source': 'platform' if platform_book else 'school',
        'read_only': platform_book,
        'has_audio_book': audio_book_id is not None,
        'audio_book_id': audio_book_id
    }

def reader_has_school_access(school_id):
    if not current_user.is_authenticated or not school_id:
        return False
    return User_shcool.query.filter_by(user_id=current_user.id, shcool_id=school_id).first() is not None

def school_has_platform_book_access(school_id, book_id):
    if not school_id or not book_id:
        return False
    if SchoolBookInstance.query.filter_by(shcool_id=school_id, book_id=book_id, active=True).first():
        return True
    return (
        db.session.query(Book_pack)
        .join(Pack, Book_pack.pack_id == Pack.id)
        .filter(Book_pack.book_id == book_id, Pack.shcool_id == school_id)
        .first()
        is not None
    )

def school_has_global_pack_access(school_id, pack_id):
    if not school_id or not pack_id:
        return False
    return SchoolPackInstance.query.filter_by(shcool_id=school_id, pack_id=pack_id, active=True).first() is not None

def reader_can_access_book_in_school(book, school_id):
    if not book or not getattr(book, 'active', True):
        return False
    if not reader_has_school_access(school_id):
        return False
    if getattr(book, 'is_platform_book', False):
        return school_has_platform_book_access(school_id, book.id)
    if book.shcool_id == school_id:
        return True
    return (
        db.session.query(Book_pack)
        .join(Pack, Book_pack.pack_id == Pack.id)
        .filter(Book_pack.book_id == book.id, Pack.shcool_id == school_id)
        .first()
        is not None
    )

def reader_can_access_platform_book_in_any_school(book):
    memberships = User_shcool.query.filter_by(user_id=current_user.id).all()
    return any(
        school_has_platform_book_access(membership.shcool_id, book.id)
        for membership in memberships
    )

def get_reader_story_progress(story_id):
    if not current_user.is_authenticated:
        return None
    return ReaderStoryProgress.query.filter_by(user_id=current_user.id, story_id=story_id).first()

def serialize_reader_story(story, include_pdf_url=False):
    progress = get_reader_story_progress(story.id)
    story_data = {
        'id': story.id,
        'book_id': story.book_id,
        'school_id': story.shcool_id,
        'title': story.title,
        'description': story.description,
        'page_count': story.page_count,
        'active': story.active,
        'completed': progress.completed if progress else False,
        'current_page': progress.current_page if progress else 1,
        'zoom': progress.zoom if progress else 1,
        'last_read_at': progress.last_read_at.isoformat() if progress and progress.last_read_at else None,
        'completed_at': progress.completed_at.isoformat() if progress and progress.completed_at else None
    }
    if include_pdf_url:
        story_data['pdf_url'] = f'/reader/stories/{story.id}/pdf'
    return story_data

def user_can_access_story(story):
    if not current_user.is_authenticated:
        return False
    if current_user.type == 'super_admin':
        return True
    book = Book.query.get(story.book_id)
    if not book:
        return False
    if story.shcool_id is not None:
        return reader_can_access_book_in_school(book, story.shcool_id)

    selected_school_id = (
        request.args.get('school')
        or request.args.get('school_id')
        or request.args.get('shcool_id')
    )
    if selected_school_id:
        try:
            selected_school_id = int(selected_school_id)
        except (TypeError, ValueError):
            return False
        return reader_can_access_book_in_school(book, selected_school_id)

    return bool(getattr(book, 'is_platform_book', False)) and reader_can_access_platform_book_in_any_school(book)

def get_accessible_story(story_id):
    story = BookStory.query.filter_by(id=story_id, active=True).first()
    if not story or not user_can_access_story(story):
        return None
    return story

def get_books_in_pack(pack_id):
    return (
        db.session.query(Book)
        .join(Book_pack, Book.id == Book_pack.book_id)
        .filter(Book_pack.pack_id == pack_id, Book.active.is_(True))
        .all()
    )

def serialize_pack_details(pack):
    enrolled = Follow_pack.query.filter_by(pack_id=pack.id).count()
    num_active_codes = Code.query.filter_by(pack_id=pack.id, status=StatusEnum.ACTIVE).count()
    books = [serialize_book_for_pack(book) for book in get_books_in_pack(pack.id)]
    global_pack = bool(getattr(pack, 'is_global_pack', False))

    return {
        'id': pack.id,
        'school_id': pack.shcool_id,
        'owner_school_id': pack.shcool_id,
        'is_global_pack': global_pack,
        'source': 'global' if global_pack else 'school',
        'read_only': global_pack,
        'title': pack.title,
        'level': pack.level,
        'age': pack.age.value if pack.age else None,
        'price': pack.price,
        'img': pack.img,
        'book_number': pack.book_number,
        'discount': pack.discount,
        'desc': pack.desc,
        'faq': pack.faq,
        'code': num_active_codes,
        'codes': num_active_codes,
        'enrolled': enrolled,
        'duration': pack.duration,
        'product_id_invoicing_api': pack.product_id_invoicing_api,
        'public': pack.public,
        'books': books,
        'books_in_pack': books
    }

def get_request_value(*keys):
    data = request.get_json(silent=True) or {}
    for key in keys:
        value = request.args.get(key)
        if value is not None:
            return value
        if key in data:
            return data.get(key)
    return None

def user_can_view_pack(pack):
    if pack.public:
        return True
    if not current_user.is_authenticated:
        return False
    if Follow_pack.query.filter_by(user_id=current_user.id, pack_id=pack.id).first():
        return True
    return User_shcool.query.filter_by(user_id=current_user.id, shcool_id=pack.shcool_id).first() is not None

def user_can_view_pack_in_school(pack, school_id):
    if not pack or not getattr(pack, 'active', True):
        return False
    if pack.public and not getattr(pack, 'is_global_pack', False):
        return True
    if not current_user.is_authenticated:
        return False
    if User_shcool.query.filter_by(user_id=current_user.id, shcool_id=school_id).first() is None:
        return False
    if getattr(pack, 'is_global_pack', False):
        return school_has_global_pack_access(school_id, pack.id)
    return pack.shcool_id == school_id

def get_pack_in_school(pack_id, school_id, public_only=False):
    pack = Pack.query.filter_by(id=pack_id, active=True).first()
    if not pack:
        return None
    if getattr(pack, 'is_global_pack', False):
        if not school_has_global_pack_access(school_id, pack.id):
            return None
        if public_only and not pack.public:
            return None
        return pack
    if pack.shcool_id != school_id:
        return None
    if public_only and not pack.public:
        return None
    return pack

def resolve_current_user_school_id():
    selected_school_id = (
        request.args.get('school')
        or request.args.get('school_id')
        or request.args.get('shcool_id')
    )
    if selected_school_id is None:
        data = request.get_json(silent=True) or {}
        selected_school_id = data.get('school') or data.get('school_id') or data.get('shcool_id')

    if selected_school_id is None:
        selected_school_id = session.get('selected_school_id')

    memberships = User_shcool.query.filter_by(user_id=current_user.id).all()
    if not memberships:
        return None, 'No school access', 403

    if selected_school_id is None:
        if len(memberships) == 1:
            return memberships[0].shcool_id, None, None
        return None, 'school_id is required', 400

    try:
        selected_school_id = int(selected_school_id)
    except (TypeError, ValueError):
        return None, 'school_id must be a number', 400

    if not any(membership.shcool_id == selected_school_id for membership in memberships):
        return None, 'You do not have access to this school', 403

    return selected_school_id, None, None

def resolve_game_school_id_from_session():
    memberships = User_shcool.query.filter_by(user_id=current_user.id).all()
    if not memberships:
        return None, 'No school access', 403

    selected_school_id = (
        request.args.get('school')
        or request.args.get('school_id')
        or request.args.get('shcool_id')
    )
    if selected_school_id is None:
        data = request.get_json(silent=True) or {}
        selected_school_id = data.get('school') or data.get('school_id') or data.get('shcool_id')

    if selected_school_id is None:
        selected_school_id = session.get('selected_school_id')

    if selected_school_id is None:
        if len(memberships) == 1:
            return memberships[0].shcool_id, None, None
        return None, 'Selected school is required before opening this game', 400

    try:
        selected_school_id = int(selected_school_id)
    except (TypeError, ValueError):
        return None, 'Selected school is invalid', 400

    if not any(membership.shcool_id == selected_school_id for membership in memberships):
        return None, 'You do not have access to this school', 403

    return selected_school_id, None, None

@reader.route('/register_school_admin', methods=['POST'])
@reader.route('/signup_school_admin', methods=['POST'])
def register_school_admin():
    try:
        data = request.get_json(silent=True) or {}
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        school_name = data.get('school_name') or data.get('shcool_name') or data.get('name')
        img = data.get('img')

        missing_fields = [
            field
            for field, value in {
                'username': username,
                'email': email,
                'password': password,
                'school_name': school_name
            }.items()
            if not value or not str(value).strip()
        ]
        if missing_fields:
            return jsonify({'message': 'Missing required fields', 'fields': missing_fields}), 400

        username = str(username).strip()
        email = str(email).strip().lower()
        school_name = str(school_name).strip()

        if user_email_exist(email):
            return jsonify({'message': 'This email is already used. Please choose another'}), 409

        existing_school = Shcool.query.filter(func.lower(Shcool.name) == school_name.lower()).first()
        if existing_school:
            return jsonify({'message': 'This school name is already used. Please choose another'}), 409

        invoicing_user_id = None
        try:
            invoicing_response = requests.post(
                f'{ConfigClass.INVOICING_API}/user/create',
                json={'appId': f'{ConfigClass.INVOICING_API_KEY}'},
                timeout=10
            )
            if invoicing_response.status_code == 201:
                invoicing_user_id = invoicing_response.json().get('_id')
        except requests.RequestException as error:
            logging.warning('Unable to create invoicing user for school admin signup: %s', error)

        password_hash = bcrypt.generate_password_hash(password)
        new_school = Shcool(name=school_name)
        db.session.add(new_school)
        db.session.flush()
        get_or_create_school_public_page(new_school)

        admin_data = {
            'username': username,
            'email': email,
            'password_hashed': password_hash,
            'created_at': datetime.now(),
            'confirmed': True,
            'approved': False,
            'user_id_invoicing_api': invoicing_user_id
        }
        if img:
            admin_data['img'] = img

        new_admin = Admin(**admin_data)
        db.session.add(new_admin)
        db.session.flush()

        db.session.add(User_shcool(user_id=new_admin.id, shcool_id=new_school.id))
        db.session.commit()

        return jsonify({
            'message': 'School admin account has been created and is pending super admin approval',
            'admin': {
                'id': new_admin.id,
                'username': new_admin.username,
                'email': new_admin.email,
                'role': new_admin.type,
                'img': new_admin.img,
                'confirmed': new_admin.confirmed,
                'approved': new_admin.approved,
                'status': 'pending_approval',
                'user_id_invoicing_api': new_admin.user_id_invoicing_api
            },
            'school': {
                'id': new_school.id,
                'name': new_school.name,
                'status': 'pending_admin_approval'
            }
        }), 201
    except Exception as error:
        db.session.rollback()
        logging.error('School admin signup failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/register_super_admin', methods=['POST'])
@reader.route('/signup_super_admin', methods=['POST'])
def register_super_admin():
    try:
        existing_super_admin = SuperAdmin.query.first()
        if existing_super_admin and not (
            current_user.is_authenticated and
            current_user.type == 'super_admin' and
            current_user.confirmed and
            current_user.approved
        ):
            return jsonify({'message': 'Super admin already exists'}), 403

        data = request.get_json(silent=True) or {}
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        img = data.get('img')

        missing_fields = [
            field
            for field, value in {
                'username': username,
                'email': email,
                'password': password
            }.items()
            if not value or not str(value).strip()
        ]
        if missing_fields:
            return jsonify({'message': 'Missing required fields', 'fields': missing_fields}), 400

        username = str(username).strip()
        email = str(email).strip().lower()

        if user_email_exist(email):
            return jsonify({'message': 'This email is already used. Please choose another'}), 409

        super_admin_data = {
            'username': username,
            'email': email,
            'password_hashed': bcrypt.generate_password_hash(password),
            'created_at': datetime.now(),
            'confirmed': True,
            'approved': True
        }
        if img:
            super_admin_data['img'] = img

        new_super_admin = SuperAdmin(**super_admin_data)
        db.session.add(new_super_admin)
        db.session.commit()
        login_user(new_super_admin)

        return jsonify({
            'message': 'Super admin account has been created successfully',
            'super_admin': {
                'id': new_super_admin.id,
                'username': new_super_admin.username,
                'email': new_super_admin.email,
                'role': new_super_admin.type,
                'img': new_super_admin.img,
                'confirmed': new_super_admin.confirmed,
                'approved': new_super_admin.approved
            }
        }), 201
    except Exception as error:
        db.session.rollback()
        logging.error('Super admin signup failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/schools/<slug>/public-page', methods=['GET'])
def get_public_school_page(slug):
    try:
        page = get_school_public_page_by_slug(slug, active_only=True)
        if not page:
            return jsonify({'message': 'School page not found'}), 404

        return jsonify({'public_page': serialize_public_school_page(page)}), 200
    except Exception as error:
        logging.error('Unable to get public school page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/schools/<slug>/register', methods=['POST'])
def register_from_school_public_page(slug):
    try:
        page = get_school_public_page_by_slug(slug, active_only=True)
        if not page:
            return jsonify({'message': 'School page not found'}), 404

        school = Shcool.query.get(page.shcool_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        missing_fields = [
            field
            for field, value in {
                'username': username,
                'email': email,
                'password': password
            }.items()
            if not value or not str(value).strip()
        ]
        if missing_fields:
            return jsonify({'message': 'Missing required fields', 'fields': missing_fields}), 400

        username = str(username).strip()
        email = str(email).strip().lower()

        if user_email_exist(email):
            return jsonify({'message': 'This email is already used. Please choose another'}), 409

        quiz_user = {'app': f'{ConfigClass.QUIZ_API_KEY}'}
        invoicing_client = {'appId': f'{ConfigClass.INVOICING_API_KEY}'}
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/client/create', json=invoicing_client)
        response = requests.post(ConfigClass.QUIZ_API, json=quiz_user)
        if response.status_code != 201 or invoicing_response.status_code != 201:
            return jsonify({'message': 'Error creation Quiz account'}), 400

        quiz_id = response.json()['_id']
        client_id = invoicing_response.json()['_id']
        password_hash = bcrypt.generate_password_hash(password)
        new_user = Reader(
            username=username,
            email=email,
            password_hashed=password_hash,
            created_at=datetime.now(),
            quiz_id=quiz_id,
            client_id_invoicing_api=client_id
        )
        db.session.add(new_user)
        db.session.flush()

        iread_school = Shcool.query.filter_by(name='IRead').first()
        if iread_school:
            add_user_to_school(new_user.id, iread_school.id)
        add_user_to_school(new_user.id, school.id)
        db.session.commit()

        confirmation_token = generate_confirmed_token(email)
        confirm_link = f'{ConfigClass.API_URL}/reader/confirm/{confirmation_token}'
        confirmation_email = render_template(
            'confirmation_email_template.html',
            username=username,
            confirm_link=confirm_link
        )
        msg = Message('Confirm your account', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
        msg.html = confirmation_email
        mail.send(msg)

        return jsonify({
            'message': 'Your account has been successfully created. Please verify your emailbox to confirm your account',
            'user': {'username': username, 'email': email},
            'school_id': school.id,
            'school': school.name,
            'dashboard_url': f'/dashboard?school_id={school.id}'
        }), 201
    except Exception as error:
        db.session.rollback()
        logging.error('School public page signup failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/schools/<slug>/login', methods=['POST'])
def login_from_school_public_page(slug):
    try:
        page = get_school_public_page_by_slug(slug, active_only=True)
        if not page:
            return jsonify({'message': 'School page not found'}), 404

        school = Shcool.query.get(page.shcool_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'message': 'Email and password are required'}), 400

        email = str(email).strip().lower()
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not bcrypt.check_password_hash(user.password_hashed, password):
            return jsonify({'message': 'Invalid email or password'}), 404
        if not user.confirmed:
            return jsonify({'message': "You don't confirm your account"}), 403
        if not user.approved:
            return jsonify({'message': 'Your are not been approved for the moment'}), 403
        if not user_belongs_to_school(user.id, school.id):
            return jsonify({'message': 'You are not joined to this school'}), 403

        login_user(user)
        set_selected_school_context(school.id)
        return jsonify({
            'message': 'Your are logged in succesfully',
            'role': user.type,
            'school_id': school.id,
            'school': school.name,
            'dashboard_url': f'/dashboard?school_id={school.id}'
        }), 200
    except Exception as error:
        logging.error('School public page login failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/select_school', methods=['POST'])
@login_required
def select_school():
    try:
        data = request.get_json(silent=True) or {}
        school_id = data.get('school_id') or data.get('shcool_id') or data.get('school')
        if school_id is None:
            return jsonify({'message': 'school_id is required'}), 400
        try:
            school_id = int(school_id)
        except (TypeError, ValueError):
            return jsonify({'message': 'school_id must be a number'}), 400

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404
        if not user_belongs_to_school(current_user.id, school.id):
            return jsonify({'message': 'You do not have access to this school'}), 403

        set_selected_school_context(school.id)
        return jsonify({
            'message': 'School selected successfully',
            'school_id': school.id,
            'school': school.name,
            'dashboard_url': f'/dashboard?school_id={school.id}'
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

## @brief Route for registering new users.
#
# This route is used for registering new users in the system. The function accepts a POST request with JSON data containing the user's username, email, and password.
# The password is encrypted using the Bcrypt object before being stored in the database.
# The new user is then added to the database.
# A confirmation token is generated for the user, encapsulating their email, and an email with a confirmation link is sent to the user.
# If the registration process is successful, a JSON object with information about the registration status and the user's details is returned.
#
# @param username: The username of the new user.
# @param email: The email of the new user.
# @param password: The password of the new user.
#
# @return: A JSON object containing information about the registration status and the user's details.

@reader.route('/register', methods=['POST'])
def register():
    try:
        username = request.json['username']
        email = request.json['email']
        password = request.json['password']
        invitation_code_value = request.json.get('invitation_code')
        invitation_code = None

        if invitation_code_value:
            invitation_code, invitation_error, invitation_status = get_valid_school_invitation(invitation_code_value)
            if invitation_error:
                return jsonify({'message': invitation_error}), invitation_status

        if user_email_exist(email):

            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:

            #Create a new user in quiz api
            quiz_user ={
                'app':f'{ConfigClass.QUIZ_API_KEY}'
            }
            invoicing_client ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}'
            }
            invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/client/create' , json=invoicing_client)  
            response = requests.post(ConfigClass.QUIZ_API, json=quiz_user)  
            if response.status_code == 201 and invoicing_response.status_code==201:
                quiz_id = response.json()['_id']
                client_id = invoicing_response.json()['_id']
                # Create a new user in your Flask application
                password_hash = bcrypt.generate_password_hash(password)
                new_user = Reader(username=username, email=email, password_hashed=password_hash, created_at=datetime.now(),quiz_id=quiz_id,client_id_invoicing_api=client_id)
                db.session.add(new_user)
                db.session.commit()
                shcool=  Shcool.query.filter_by(name="IRead").first()
                if shcool:
                    add_user_to_school(new_user.id, shcool.id)
                if invitation_code:
                    redeem_school_invitation_for_user(invitation_code, new_user.id)
                db.session.commit()
                # Send a confirmation email as before
                confirmation_token = generate_confirmed_token(email)
                confirm_link = f"{ConfigClass.API_URL}/reader/confirm/{confirmation_token}"
                confirmation_email = render_template('confirmation_email_template.html', username=username,
                                                      confirm_link=confirm_link)
                msg = Message('Confirm your account', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
                msg.html = confirmation_email
                mail.send(msg)

                return jsonify({'message': 'Your account has been successfully created. Please verify your emailbox to confirm your account',
                                'user': {'username': username, 'email': email}}), 201
            else:

                return jsonify({'message':'Error creation Quiz account'}),400

    except Exception as error:
        print(str(error))  # Print the error message for debugging
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/google-login', methods=['POST'])
def google_register():
    try:
        username = request.json['username']
        email = request.json['email']
        password = secrets.token_urlsafe(12) 
        invitation_code_value = request.json.get('invitation_code')
        invitation_code = None

        if invitation_code_value:
            invitation_code, invitation_error, invitation_status = get_valid_school_invitation(invitation_code_value)
            if invitation_error:
                return jsonify({'message': invitation_error}), invitation_status

        if user_email_exist(email):
           google_user=User.query.filter_by(email=email).first()
           accounts = User.query.filter_by(email=email).all()
           login_user(google_user)
           if invitation_code:
               redeem_school_invitation_for_user(invitation_code, google_user.id)
               db.session.commit()
           accountsData=[]
           for account in accounts:
                accountsData.append({
                    "username":account.username,  
                    "email":account.email,
                    "img":account.img
                        })          
           return jsonify({'message':'Your are logged in succesfully','accounts':accountsData}),200
        else:
            #Create a new user in quiz api
            quiz_user ={
                'app':f'{ConfigClass.QUIZ_API_KEY}'
            }
            response = requests.post(ConfigClass.QUIZ_API, json=quiz_user)  
            if response.status_code == 201:
                quiz_id = response.json()['_id']
                # Create a new user in your Flask application
                password_hash = bcrypt.generate_password_hash(password)
                new_user = Reader(username=username, email=email, password_hashed=password_hash, created_at=datetime.now(),confirmed=True,approved=True,quiz_id=quiz_id)
                db.session.add(new_user)    
                db.session.commit()
                shcool=  Shcool.query.filter_by(name="IRead").first()
                if shcool:
                    add_user_to_school(new_user.id, shcool.id)
                if invitation_code:
                    redeem_school_invitation_for_user(invitation_code, new_user.id)
                db.session.commit()
                login_user(new_user)
                return jsonify({'message':'Your are logged in succesfully','accounts':[]}),200
            else:
                print("here")
                return jsonify({'message': 'Internal server error'}), 500
    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error'}), 500

## @brief Route for confirming the account based on the received email.
#
# This route is used to confirm the user's account based on the token contained in the confirmation email sent to the user.
# The function uses the 'confirm_token' function imported from './email.py' to verify if the link is valid.
# If the link is valid, the 'confirmed' attribute of the user is set to 1 (True).
# A JSON object is returned to notify whether the confirmation process was successful or not.
#
# @param token: Token contained in the confirmation email sent to the user.
#
# @return: A JSON object to notify if the confirmation process was successful or not.
@reader.route('/confirm/<token>')
def confirmation_of_token(token):
    try:
        if reader_confirm_token(token):
             return redirect(f"{ConfigClass.FRONT_URL}/authentication/account-confirmed", code=200)
        else:
            return jsonify({'message':'Invalid or expired link'}),404
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for resending the confirmation email in case the account confirmation link has expired or is invalid.
#
# This route is used to resend the confirmation email to the user if the account confirmation link has expired or is invalid.
# The function accepts a POST request with JSON data containing the user's email for resending the confirmation link.
# If the provided email exists in the database, a new confirmation token is generated for the user.
# A confirmation link is created using the new token and sent to the user's email.
# If the email exists and the confirmation link is sent successfully, a JSON object with a success message is returned.
# If the email does not exist or the user is not yet registered, a JSON object with an error message is returned.
#
# @param email: The email for resending the confirmation link.
#
# @return: A JSON object containing information about the result of the email resend process.
@reader.route('/resend_email_confirmation_link',methods=['POST'])
def resend_email_confirmation_link():
    try:
        email=request.json['email']
        if user_email_exist(email):
            user=User.query.filter_by(email=email).first()
            username=user.username
            confirmation_token=generate_confirmed_token(email)
            confirm_link = f"{ConfigClass.API_URL}/reader/confirm/{confirmation_token}"
            confirmation_email = render_template('confirmation_email_template.html', username=username, confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
            msg.html = confirmation_email
            mail.send(msg)
        else:
            return jsonify({'message':'Invalid email or you are not already regiter?'}),404

        return jsonify({'message':'A new email has been sent !!!'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for user readers' login.
#
# This route is used for user readers' login. The function accepts a POST request with JSON data containing the user's email and password.
# The function verifies if the provided email and password match the information in the database.
# If the email and password are correct, and the user's account is confirmed, the user is logged in successfully.
# A JSON object is returned to notify whether the login process was successful or not, along with the user's 'is_admin' status.
#
# @param email: The email entered by the user for login.
# @param password: The password entered by the user for login.
#
# @return: A JSON object to notify if the login process was successful or not, along with the user's 'is_admin' status.




@reader.route('/get_cokies', methods=['GET'])
def get_cookies_fun():
    try:
          
        user_id = session.get('user_id')
        if user_id is None:
            user_id = generate_unique_user_id()
            session['user_id']=user_id
            
        
            session['start_time'] = time.time()
            session['log_saved'] = False

            



            user_agent = request.headers.get('User-Agent')
            user_agent_info = parse(user_agent)

            browser = user_agent_info.browser.family
            system = user_agent_info.os.family

            
            user_ip = request.headers.get('X-Forwarded-For')
            if user_ip is None:
                user_ip = request.remote_addr
            referer = request.headers.get('Referer')
            utm_source = request.args.get('utm_source')
            if utm_source:
                source = utm_source
            else:
                source = referer
            user_country = "Unknown"
            user_city = "Unknown"
            geolite_city_path = get_geolite_city_path()
            try:
                if os.path.exists(geolite_city_path):
                    with Beader(geolite_city_path) as test:
                        response = test.city(user_ip)
                        user_country = response.country.name
                        user_city = response.city.name
                else:
                    logging.warning('GeoLite city database not found at %s', geolite_city_path)
            except Exception as geo_error:
                logging.warning('Error looking up IP: %s', geo_error)
            
            user_log = UserLog( user_agent=user_agent, user_ip=user_ip, referer=source,
            user_country=user_country, user_city=user_city,user_cookie_id=user_id,system=system,browser=browser)
            db.session.add(user_log)
            db.session.commit()
            return jsonify({'message': 'Log saved'}), 200
        else:   
            
 
            existing_log = UserLog.query.filter_by(user_cookie_id=user_id).first()
            if existing_log:
                
               
 
                if not session.get('log_saved'):
                   

                    start_time = session.get('start_time')
                    if start_time:
                        end_time = time.time()
                        visit_duration = end_time - start_time

                        existing_log.visit_duration = visit_duration
                        db.session.commit()

                        session['log_saved'] = False

                    return jsonify({'message': 'Returning user, visit duration updated'}), 200

                return jsonify({'message': 'Returning user, log already saved in this session'}), 200
    except Exception as error:
        print(str(error))
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500






@reader.route('/login_client',methods=['POST'])
def login_client():
    try:
        email=request.json['email']
        password=request.json['password']
        user=User.query.filter_by(email=email).first()
        accounts =User.query.filter_by(email=email).all()
        print(accounts)
        if user and bcrypt.check_password_hash(user.password_hashed,password):
            if user.confirmed:
                if user.approved:
                    login_user(user)
                    pin_required = len(accounts) > 1
                    accountsData=[]
                    for account in accounts:
                        accountsData.append({
                            "username":account.username,
                            "email":account.email,
                            "img":account.img,
                            "is_primary":account.is_primary,
                            "pin_required":pin_required,
                            "has_pin":bool(account.pin_hash)
                        })
                    return jsonify({'message':'Your are logged in succesfully','accounts':accountsData,'pin_required':pin_required}),200
                else:
                    return jsonify({'message':'Your are not been approved for the moment'}),403
            else:
                return jsonify({'message':'You don\'t confirm your account'}),403 # Acces interdit
        else:  
            return jsonify({'message':'Invalid email or password'}),404
    
    except Exception as error:
        print(error)
        return jsonify({'message':'Internal server error','error':str(error)}),500

@reader.route('/login',methods=['POST'])
def login():   
    try:    
        email=request.json['email']
        password=request.json['password']
        user=User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hashed,password):
            if user.confirmed:
                if user.approved:
                    login_user(user)

                    return jsonify({'message':'Your are logged in succesfully','role':user.type,'must_change_password':bool(user.must_change_password)}),200
                else:
                    return jsonify({'message':'Your are not been approved for the moment'}),403
            else:
                return jsonify({'message':'You don\'t confirm your account'}),403 # Acces interdit
        else:
            return jsonify({'message':'Invalid email or password'}),404

    except Exception as error:
        return jsonify({'message':'Internal server error','error':str(error)}),500

## @brief Route for a logged-in user to change their own password.
#
# Verifies the current password, sets the new password hash, and clears
# must_change_password so the forced first-login reset flow stops firing.
@reader.route('/change_password',methods=['POST'])
@login_required
def change_password():
    try:
        current_password = request.json.get('current_password')
        new_password = request.json.get('new_password')
        if not current_password or not new_password:
            return jsonify({'message':'current_password and new_password are required'}),400
        if not bcrypt.check_password_hash(current_user.password_hashed,current_password):
            return jsonify({'message':'Current password is incorrect'}),403
        current_user.password_hashed = bcrypt.generate_password_hash(new_password).decode('utf-8')
        current_user.must_change_password = False
        db.session.commit()
        return jsonify({'message':'Password updated successfully'}),200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message':'Internal server error','error':str(error)}),500

PIN_MAX_ATTEMPTS = 5
PIN_LOCKOUT_MINUTES = 15

@reader.route('/select_account',methods=['POST'])
@login_required
def select_account():

    try:
        email=request.json['email']
        username=request.json['username']

        if email != current_user.email:
            return jsonify({'message':'Forbidden'}),403

        user=User.query.filter_by(email=email,username=username).first()

        if user:
            if not user.confirmed:
                return jsonify({'message':'You don\'t confirm your account'}),403
            if not user.approved:
                return jsonify({'message':'Your are not been approved for the moment'}),403

            siblings_count = User.query.filter_by(email=email).count()
            # Profiles created before the PIN feature existed (or the split
            # second between account creation and setting a PIN) have no
            # pin_hash yet: let the switch through once instead of locking the
            # profile out forever, but the frontend must prompt to set a PIN
            # right after. Ownership was already verified above, so this only
            # ever benefits someone who is already an authenticated sibling.
            if siblings_count > 1 and user.pin_hash:
                if user.pin_locked_until and user.pin_locked_until > datetime.now():
                    return jsonify({'message':'Too many incorrect PIN attempts, please try again later'}),429

                pin = request.json.get('pin')
                if not pin or not bcrypt.check_password_hash(user.pin_hash,pin):
                    user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
                    if user.pin_failed_attempts >= PIN_MAX_ATTEMPTS:
                        user.pin_locked_until = datetime.now() + timedelta(minutes=PIN_LOCKOUT_MINUTES)
                        user.pin_failed_attempts = 0
                    db.session.commit()
                    return jsonify({'message':'Invalid PIN'}),401

                user.pin_failed_attempts = 0
                user.pin_locked_until = None
                db.session.commit()

            login_user(user)
            return jsonify({'message':'Your are logged in succesfully','role':user.type,'pin_setup_required':siblings_count > 1 and not bool(user.pin_hash)}),200
        else:
            return jsonify({'message':'Invalid account'}),404

    except Exception as error:
        return jsonify({'message':'Internal server error','error':str(error)}),500
@reader.route('/create_account',methods=['POST'])
@login_required
def create_account():

    try:
        username=request.json['username']
        password = request.json['password']
        pin = request.json.get('pin')
        accounts =User.query.filter_by(email=current_user.email).all()


        if len(accounts) >= 3 :
            return jsonify({'message':'You reached the maximum number of accounts (3)'}) ,400

        if not pin or not str(pin).isdigit() or len(str(pin)) != 4:
            return jsonify({'message':'A 4-digit PIN is required for this profile'}),400

        if not current_user.pin_hash:
            return jsonify({'message':'Set a PIN for your account before adding another profile'}),400

        user=User.query.filter_by(email=current_user.email,username=username).first()
        if not bcrypt.check_password_hash(current_user.password_hashed,password):
            return jsonify({'message':'Invalid password'}) ,400
        if user:
            return jsonify({'message':'Username already  exists '}),400
        else:
            #Create a new user in quiz api
            quiz_user ={
                'app':f'{ConfigClass.QUIZ_API_KEY}'
            }
            response = requests.post(ConfigClass.QUIZ_API, json=quiz_user)
            if response.status_code == 201:
                quiz_id = response.json()['_id']
                new_account = Reader(username=username, email=current_user.email, password_hashed=current_user.password_hashed, created_at=datetime.now(),confirmed=True,approved=True,quiz_id=quiz_id,is_primary=False,pin_hash=bcrypt.generate_password_hash(str(pin)))
                db.session.add(new_account)
                db.session.commit()
                userData ={
                    "username":new_account.username,
                    "email":new_account.email,
                    "img":new_account.img
                    
                    }
                school  = Shcool.query.filter_by(name="IRead").first()
                new_user_shcool = User_shcool(
                  user_id = new_account.id,
                  shcool_id = school.id
                )
                db.session.add(new_user_shcool)
                db.session.commit()    
                return jsonify({'message':'Your account has been created','user':userData}),201
            else:
                return jsonify({'message':'Error creation Quiz account'}),400    
    
    except Exception as error:
        print(error)
        return jsonify({'message':'Internal server error','error':str(error)}),500
# get user account with email 
@reader.route('/get_accounts')
@login_required
def get_accounts():

    try:
        accounts =User.query.filter_by(email=current_user.email).all()
        pin_required = len(accounts) > 1
        accountsData=[]
        for account in accounts:

            accountsData.append({
                "username":account.username,
                "email":account.email,
                "img":account.img,
                "is_primary":account.is_primary,
                "pin_required":pin_required,
                "has_pin":bool(account.pin_hash)
                        })
        return jsonify({'accounts':accountsData,'pin_required':pin_required}),200
       

    
    except Exception as error:
        return jsonify({'message':'Internal server error','error':str(error)}),500



#current user        
@reader.route('/user_authenticated')
def user_authenticated():
    try:
      
        if current_user.is_authenticated:
     
            client_id_invoicing_api = getattr(current_user, 'client_id_invoicing_api', None)
            quiz_id = getattr(current_user, 'quiz_id', None)
            if current_user.type == "super_admin":
                schools = Shcool.query.order_by(Shcool.name.asc()).all()
                return jsonify({
                    'is_authenticated': current_user.is_authenticated,
                    'username': current_user.username,
                    'email': current_user.email,
                    'img': current_user.img,
                    'role': current_user.type,
                    'quiz_id': quiz_id,
                    'id': current_user.id,
                    'is_super_admin': True,
                    'must_change_password': bool(current_user.must_change_password),
                    'schools': [{'id': school.id, 'name': school.name} for school in schools]
                })

            if current_user.type == "admin":

                school_id = User_shcool.query.filter_by(user_id=current_user.id).first().shcool_id

                school = Shcool.query.get(school_id)

                return jsonify({
                    'is_authenticated': current_user.is_authenticated,
                    'username': current_user.username,
                    'email': current_user.email,
                    'img': current_user.img,
                    'role': current_user.type,
                    'quiz_id': quiz_id,
                    'id': current_user.id,
                    'client_id_invoicing_api': client_id_invoicing_api,
                    'school_id': school.id,
                    'school': school.name,
                    'must_change_password': bool(current_user.must_change_password)
                })

            else:
                return jsonify({
                    'is_authenticated': current_user.is_authenticated,
                    'username': current_user.username,
                    'email': current_user.email,
                    'img': current_user.img,
                    'role': current_user.type,
                    'quiz_id': quiz_id,
                    'id': current_user.id,
                    'client_id_invoicing_api': client_id_invoicing_api,
                    'schools': get_user_schools(current_user.id),
                    'is_primary': current_user.is_primary,
                    'has_pin': bool(current_user.pin_hash),
                    'must_change_password': bool(current_user.must_change_password)
                })
    except Exception as e:     
        return jsonify({'error': str(e), 'message': 'Internal server error'})

@reader.route('/get_all_schools', methods=['GET'])
def get_all_schools():
    try:
        joined_school_ids = set()
        if current_user.is_authenticated:
            memberships = User_shcool.query.filter_by(user_id=current_user.id).all()
            joined_school_ids = {membership.shcool_id for membership in memberships}

        schools = Shcool.query.order_by(Shcool.name.asc()).all()
        return jsonify({
            'schools': [serialize_school(school, school.id in joined_school_ids) for school in schools]
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/join_school', methods=['POST'])
@login_required
def join_school():
    try:
        if current_user.type in ['admin', 'super_admin']:
            return jsonify({'message': 'Admins cannot join schools from the reader join endpoint'}), 403

        data = request.get_json(silent=True) or {}
        school_ids = data.get('school_ids')
        if school_ids is None:
            school_id = data.get('school_id') or data.get('shcool_id') or data.get('id')
            if school_id is None:
                return jsonify({'message': 'school_id or school_ids is required'}), 400
            school_ids = [school_id]

        if not isinstance(school_ids, list) or not school_ids:
            return jsonify({'message': 'school_ids must be a non-empty list'}), 400

        normalized_school_ids = []
        for school_id in school_ids:
            try:
                normalized_school_id = int(school_id)
            except (TypeError, ValueError):
                return jsonify({'message': 'Each school_id must be a number'}), 400
            if normalized_school_id not in normalized_school_ids:
                normalized_school_ids.append(normalized_school_id)

        schools = Shcool.query.filter(Shcool.id.in_(normalized_school_ids)).all()
        schools_by_id = {school.id: school for school in schools}
        missing_school_ids = [school_id for school_id in normalized_school_ids if school_id not in schools_by_id]
        if missing_school_ids:
            return jsonify({'message': 'School not found', 'missing_school_ids': missing_school_ids}), 404

        joined_schools = []
        already_joined_schools = []
        for school_id in normalized_school_ids:
            school = schools_by_id[school_id]
            added = add_user_to_school(current_user.id, school_id)
            if added:
                joined_schools.append(serialize_school(school, True))
            else:
                already_joined_schools.append(serialize_school(school, True))

        db.session.commit()

        return jsonify({
            'message': 'School joined successfully' if joined_schools else 'You are already joined to selected school(s)',
            'joined_schools': joined_schools,
            'already_joined_schools': already_joined_schools,
            'schools': get_user_schools(current_user.id)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/join_school_by_invitation', methods=['POST'])
@login_required
def join_school_by_invitation():
    try:
        if current_user.type in ['admin', 'super_admin']:
            return jsonify({'message': 'Admins cannot join schools from the reader invitation endpoint'}), 403

        data = request.get_json(silent=True) or {}
        invitation_code, invitation_error, invitation_status = get_valid_school_invitation(data.get('code'))
        if invitation_error:
            return jsonify({'message': invitation_error}), invitation_status

        already_joined = User_shcool.query.filter_by(
            user_id=current_user.id,
            shcool_id=invitation_code.shcool_id
        ).first()
        school = Shcool.query.get(invitation_code.shcool_id)

        if already_joined:
            return jsonify({
                'message': 'You are already joined to this school',
                'school': {'id': school.id, 'name': school.name},
                'schools': get_user_schools(current_user.id)
            }), 200

        redeem_school_invitation_for_user(invitation_code, current_user.id)
        db.session.commit()

        return jsonify({
            'message': 'School joined successfully',
            'school': {'id': school.id, 'name': school.name},
            'schools': get_user_schools(current_user.id)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/books/<int:book_id>/stories', methods=['GET'])
@login_required
def get_reader_book_stories(book_id):
    try:
        school_id, school_error, school_status = resolve_current_user_school_id()
        if school_error:
            return jsonify({'message': school_error}), school_status

        book = Book.query.get(book_id)
        if not reader_can_access_book_in_school(book, school_id):
            return jsonify({'message': 'Book not found in this school'}), 404

        if getattr(book, 'is_platform_book', False):
            stories_query = BookStory.query.filter(
                BookStory.book_id == book_id,
                BookStory.shcool_id.is_(None),
                BookStory.active.is_(True)
            )
        else:
            stories_query = BookStory.query.filter_by(book_id=book_id, shcool_id=school_id, active=True)

        stories = stories_query.order_by(BookStory.id.desc()).all()
        return jsonify({'stories': [serialize_reader_story(story) for story in stories]}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/stories/<int:story_id>', methods=['GET'])
@login_required
def get_reader_story(story_id):
    try:
        story = get_accessible_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404
        return jsonify({'story': serialize_reader_story(story, include_pdf_url=True)}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/stories/<int:story_id>/pdf', methods=['GET'])
@login_required
def get_reader_story_pdf(story_id):
    try:
        story = get_accessible_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404
        if not story.file_path or not os.path.exists(story.file_path):
            return jsonify({'message': 'Story PDF file not found'}), 404

        return send_file(
            story.file_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=story.original_filename
        )
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/stories/<int:story_id>/progress', methods=['PUT'])
@login_required
def update_reader_story_progress(story_id):
    try:
        story = get_accessible_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404

        data = request.get_json(silent=True) or {}
        current_page = data.get('current_page')
        zoom = data.get('zoom')

        progress = ReaderStoryProgress.query.filter_by(user_id=current_user.id, story_id=story.id).first()
        if not progress:
            progress = ReaderStoryProgress(user_id=current_user.id, story_id=story.id)
            db.session.add(progress)

        if current_page is not None:
            try:
                current_page = int(current_page)
            except (TypeError, ValueError):
                return jsonify({'message': 'current_page must be a number'}), 400
            if current_page < 1:
                return jsonify({'message': 'current_page must be greater than 0'}), 400
            if story.page_count and current_page > story.page_count:
                current_page = story.page_count
            progress.current_page = current_page

        if zoom is not None:
            try:
                zoom = float(zoom)
            except (TypeError, ValueError):
                return jsonify({'message': 'zoom must be a number'}), 400
            if zoom <= 0:
                return jsonify({'message': 'zoom must be greater than 0'}), 400
            progress.zoom = zoom

        progress.last_read_at = datetime.now()
        db.session.commit()
        return jsonify({'progress': serialize_reader_story(story)}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/stories/<int:story_id>/complete', methods=['POST'])
@login_required
def complete_reader_story(story_id):
    try:
        story = get_accessible_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404

        progress = ReaderStoryProgress.query.filter_by(user_id=current_user.id, story_id=story.id).first()
        if not progress:
            progress = ReaderStoryProgress(user_id=current_user.id, story_id=story.id)
            db.session.add(progress)

        if story.page_count:
            progress.current_page = story.page_count
        progress.completed = True
        progress.completed_at = datetime.now()
        progress.last_read_at = datetime.now()
        db.session.commit()

        return jsonify({
            'message': 'Story completed',
            'progress': {
                'story_id': story.id,
                'current_page': progress.current_page,
                'zoom': progress.zoom,
                'completed': progress.completed,
                'completed_at': progress.completed_at.isoformat() if progress.completed_at else None
            }
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/create_invoice_client')
def create_invoice_client():
    try:
        user=User.query.filter_by(id=current_user.id).first()
        invoicing_client ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}'
            }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/client/create' , json=invoicing_client)  
        if  invoicing_response.status_code==201:
            client_id = invoicing_response.json()['_id']
            user.client_id_invoicing_api =client_id
            db.session.commit()

            return jsonify({'message':'user has been linked to invoicing_api'})


    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500



## @brief Route to the reader's dashboard for viewing their profile.
#
# This route is used to display the reader's dashboard and their profile information.
# The route accepts a GET request and requires the user to be logged in.
# The user's dashboard contains details such as their username and email.
# It also fetches information about the formations that the user is following, including those that have already taken place (formation_follow),
# and those that are scheduled for the future (comming_formation).
# The information is then formatted into a JSON object and returned as a response.
#
# @return: A JSON object containing the username, email, and information about the formations the user is following (formation_follow)
#          and the upcoming formations (pending_session).
@reader.route('/dashboard')
@login_required
def dashboard():
    try:
        school_id, school_error, school_status = resolve_current_user_school_id()
        if school_error:
            return jsonify({'message': school_error}), school_status

        infos = (
            db.session.query(User, Book, Session, Follow_session, Pack)
            .filter(User.id == current_user.id)
            .join(Follow_session, User.id == Follow_session.user_id)
            .join(Session, Session.id == Follow_session.session_id)
            .join(Book, Book.id == Session.book_id)
            .join(Pack, Session.pack_id == Pack.id)
            .outerjoin(
                SchoolPackInstance,
                and_(
                    SchoolPackInstance.pack_id == Pack.id,
                    SchoolPackInstance.shcool_id == school_id,
                    SchoolPackInstance.active.is_(True)
                )
            )
            .filter(
                Pack.active.is_(True),
                or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None))
            )
        )

        followed_sessions = infos.filter(
            # Session.start_date < datetime.now()
        ).all()
        pending_sessions = infos.filter(
            # Session.start_date >= datetime.now(),
            Follow_session.approved == 0
        ).all()
        current_session_followed = infos.filter(
            # Session.start_date >= datetime.now(),
            Follow_session.approved == 1
        ).all()

        followed_sessions_data = []
        for session_follow in followed_sessions:
            is_global = bool(getattr(session_follow.Pack, 'is_global_pack', False))
            followed_sessions_data.append({
                'session_name': session_follow.Session.name,
                'id': session_follow.Session.id,
                'pack_id': session_follow.Session.pack_id,
                'school_id': school_id if is_global else session_follow.Pack.shcool_id,
                'owner_school_id': session_follow.Pack.shcool_id,
                'is_global_pack': is_global,
                'source': 'global' if is_global else 'school',
                'read_only': is_global,
                'book_title': session_follow.Book.title,
                'book_id': session_follow.Book.id,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location.value,
                'date': session_follow.Session.start_date.strftime('%Y-%m-%d'),
                'approved': session_follow.Follow_session.approved,
                'video_call_available': is_online_session(session_follow.Session) and bool(session_follow.Follow_session.approved),
                'book_img':session_follow.Book.img,
                'unit_id': session_follow.Session.unit_id

            })

        pending_session_data = []
        for pending_session in pending_sessions:
            is_global = bool(getattr(pending_session.Pack, 'is_global_pack', False))
            pending_session_data.append({
                'session_name': pending_session.Session.name,
                'id': pending_session.Session.id,
                'pack_id': pending_session.Session.pack_id,
                'school_id': school_id if is_global else pending_session.Pack.shcool_id,
                'owner_school_id': pending_session.Pack.shcool_id,
                'is_global_pack': is_global,
                'source': 'global' if is_global else 'school',
                'read_only': is_global,
                'book_title': pending_session.Book.title,
                'book_id': pending_session.Book.id,
                'author': pending_session.Book.author,
                'location': pending_session.Session.location.value,
                'date': pending_session.Session.start_date.strftime('%Y-%m-%d'),
                'approved': pending_session.Follow_session.approved,
                'video_call_available': False
            })

        current_session_followed_data = []
        for session_follow in current_session_followed:
            is_global = bool(getattr(session_follow.Pack, 'is_global_pack', False))
            current_session_followed_data.append({
                'session_name': session_follow.Session.name,
                'id': session_follow.Session.id,
                'pack_id': session_follow.Session.pack_id,
                'school_id': school_id if is_global else session_follow.Pack.shcool_id,
                'owner_school_id': session_follow.Pack.shcool_id,
                'is_global_pack': is_global,
                'source': 'global' if is_global else 'school',
                'read_only': is_global,
                'book_title': session_follow.Book.title,
                'book_id': session_follow.Book.id,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location.value,
                'date': session_follow.Session.start_date.strftime('%Y-%m-%d'),
                'approved': session_follow.Follow_session.approved,
                'video_call_available': is_online_session(session_follow.Session) and bool(session_follow.Follow_session.approved),
                'unit_id': session_follow.Session.unit_id
            })

        return jsonify({
            'username': current_user.username,
            'email': current_user.email,
            'school_id': school_id,
            'followed_sessions': followed_sessions_data,
            'pending_sessions': pending_session_data,
            'current_session_followed': current_session_followed_data
        })

    except Exception as error:
        logging.error('An error occurred: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500



## @brief Route for user logout.
#
# This route is used for user logout. The route is protected, meaning that only a logged-in user can access this route.
# The function logs out the current user using the 'logout_user()' function provided by Flask-Login.
# A JSON object is returned to notify that the user has been successfully logged out.
#
# @return: A JSON object to notify that the user has been successfully logged out.
@reader.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        return jsonify({'message':'You are logged out sucessfully'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for handling forgotten passwords.
#
# This route is used for handling forgotten passwords. The function accepts a POST request with JSON data containing the user's email.
# The function checks if the provided email exists in the database using the 'user_email_exist' function.
# If an account with the provided email exists, a confirmation token is generated for the user.
# A password reset link is created using the confirmation token and sent to the user's email.
# If the email exists and the password reset link is sent successfully, a JSON object with a success message is returned.
# If no account is found with the provided email, a JSON object with an error message is returned.
#
# @param email: The email for receiving the password reset link.
#
# @return: A JSON object containing information about the result of the password reset request.
@reader.route('/forget_password',methods=['POST'])
def forget_password():
    try:
       
        email=request.json['email']
        if not user_email_exist(email):
            return jsonify({'message':' There is no account with this email'}),404
        else:
            confirmation_token=generate_confirmed_token(email)
            confirm_link = f"{ConfigClass.API_URL}/reader/password_reset/{confirmation_token}"
            #confirmation_email = render_template('proof_your_identity.html',confirm_link=confirm_link)
            msg = Message('Proof your identity', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
            msg.body=confirm_link
            #msg.html = confirmation_email
            mail.send(msg)
            return jsonify({'message':'You have received an confirmation email to proof your identity'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for resetting forgotten passwords for readers.
#
# This route is used for resetting forgotten passwords for readers. The function accepts a POST request with JSON data containing the new password.
# The function takes a 'token' as a parameter, which is used to verify if the password reset link is valid and not expired.
# The 'reader_confirm_token' function checks if the token is valid and returns True if it is, and False otherwise.
# If the token is invalid or expired, a JSON object with an error message is returned.
# If the token is valid and the request method is POST, the function generates a new password hash using the 'bcrypt' library.
# The password hash is updated in the database for the user associated with the email provided in the token.
# A success message is returned to the user indicating that the password has been successfully changed, and the user can now log in with the new password.
#
# @param token: The token contained in the password reset link received by the user's email.
# @param new_password: The new password entered by the user for resetting the forgotten password.
#
# @return: A JSON object containing information about the result of the password reset request.
@reader.route('/password_reset/<token>',methods=['POST'])
def reset_password(token):
    try:
        if not reader_confirm_token(token):
            return jsonify({'message':'Invalid or expired link'}),404
        new_password=request.json['new_password']
        password_hashed=bcrypt.generate_password_hash(new_password)
        user=User.query.filter_by(email=reader_confirm_token(token)).first()
        user.password_hashed=password_hashed
        db.session.commit()
        return jsonify({'message':f'{user.username} ,you have sucessfully changed your password.You can now login'}),200

    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for setting a new username for the current user.
#
# This route is used for setting a new username for the current user. The function accepts a POST request with JSON data containing the user's email, password, and the new username.
# The function checks if the provided email and password match a user in the database using the 'User.query.filter_by' function and the 'bcrypt.check_password_hash' function.
# If the email and password are valid, the function updates the username for the user in the database using the 'db.session.commit()' function.
# A success message is returned to the user indicating that the username has been successfully changed.
# If the email and password are invalid or do not match a user in the database, an error message is returned.
#
# @param password: The password of the current user.
# @param new_username: The new username to be set for the current user.
#
# @return: A JSON object containing information about the result of the request to set the new username.
@reader.route('/set_username',methods=['POST'])
@login_required
def set_username():
    try:
        password=request.json['password']
        new_username=request.json['new_username']

        user=User.query.filter_by(email=current_user.email,username=current_user.username).first()

        if user and bcrypt.check_password_hash(user.password_hashed,password):
            user.username=new_username
            db.session.commit()
            return jsonify({'message':f'{user.username}'' you have changed your username'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for requesting an email change for readers.
#
# This route starts an email change instead of applying it immediately. The function accepts a POST
# request with JSON data containing the user's current password and the requested new email.
# The function checks if the provided password matches the current user using 'bcrypt.check_password_hash'.
# If valid, a time-limited token embedding the user's id and the new email is generated, and a
# confirmation link built from that token is emailed to the new address. A separate notice is sent
# to the current email so the account owner is aware a change was requested even if they didn't
# initiate it. The email in the database is only updated once the new address is verified via
# the '/confirm_email_change/<token>' route.
#
# @param password: The password of the current user to confirm their identity.
# @param new_email: The new email to be set for the current user, pending verification.
#
@reader.route('/set_email',methods=['POST'])
@login_required
def set_email():
    try:
        old_email=current_user.email
        password=request.json['password']
        new_email=request.json.get('new_email','').strip().lower()

        user=User.query.filter_by(email=old_email,username=current_user.username).first()

        if not (user and bcrypt.check_password_hash(user.password_hashed,password)):
            return jsonify({'message':'Invalid email or passsword'}),404

        if not new_email:
            return jsonify({'message':'A new email is required'}),400

        if new_email==old_email.lower():
            return jsonify({'message':'This is already your current email'}),400

        change_token=generate_email_change_token(user.id,new_email)
        confirm_link=f"{ConfigClass.API_URL}/reader/confirm_email_change/{change_token}"

        verify_msg=Message('Confirm your new email address',recipients=[new_email],sender=ConfigClass.MAIL_USERNAME)
        verify_msg.body=(
            f"Hi {user.username},\n\n"
            f"Please confirm your new email address by clicking the link below:\n{confirm_link}\n\n"
            "This link expires in 20 minutes. If you did not request this change, you can ignore this email."
        )
        mail.send(verify_msg)

        notice_msg=Message('Email change requested on your account',recipients=[old_email],sender=ConfigClass.MAIL_USERNAME)
        notice_msg.body=(
            f"Hi {user.username},\n\n"
            f"A request was made to change the email on your account from {old_email} to {new_email}.\n"
            "If this was not you, please change your password immediately."
        )
        mail.send(notice_msg)

        return jsonify({'message':f'A confirmation link has been sent to {new_email}. Your current email has also been notified of this request.'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for confirming a pending email change for readers.
#
# This route is used to confirm and apply an email change requested through '/set_email'. The function
# uses the 'confirm_email_change_token' function to verify the token is valid, not expired, and matches
# an existing user, applying the new email only at that point. Once applied, a confirmation email is sent
# to both the new address (so the user knows the change succeeded) and the old address (so the previous
# owner is informed the change went through, in case the request wasn't theirs).
#
# @param token: The token contained in the confirmation link sent to the requested new email.
#
# @return: A redirect to the front-end confirmation page, or a JSON error if the link is invalid or expired.
@reader.route('/confirm_email_change/<token>')
def confirm_email_change(token):
    try:
        result=confirm_email_change_token(token)
        if not result:
            return jsonify({'message':'Invalid or expired link'}),404

        user=result['user']
        old_email=result['old_email']
        new_email=result['new_email']

        confirmed_new_msg=Message('Your email address has been changed',recipients=[new_email],sender=ConfigClass.MAIL_USERNAME)
        confirmed_new_msg.body=f"Hi {user.username},\n\nThis confirms that your account email has been changed to {new_email}."
        mail.send(confirmed_new_msg)

        if old_email and old_email!=new_email:
            confirmed_old_msg=Message('Your account email has been changed',recipients=[old_email],sender=ConfigClass.MAIL_USERNAME)
            confirmed_old_msg.body=(
                f"Hi {user.username},\n\n"
                f"This confirms that your account email was changed from {old_email} to {new_email}.\n"
                "If you did not request this, please contact support immediately."
            )
            mail.send(confirmed_old_msg)

        return redirect(f"{ConfigClass.FRONT_URL}/authentication/email-change-confirmed",code=302)
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for changing passwords for readers.
#
# This route is used for changing passwords for readers. The function accepts a POST request with JSON data containing the user's email, old password, and the new password.
# The function checks if the provided email and old password match a user in the database using the 'User.query.filter_by' function and the 'bcrypt.check_password_hash' function.
# If the email and old password are valid, the function generates a new password hash for the new password using the 'bcrypt.generate_password_hash' function and updates the password hash for the user in the database.
# A success message is returned to the user indicating that the password has been successfully changed.
# If the email and old password are invalid or do not match a user in the database, an error message is returned.
#
# @param old_password: The old password of the current user to confirm their identity.
# @param new_password: The new password to be set for the current user.
#
# @return: A JSON object containing information about the result of the request to change the password.
@reader.route('/set_password',methods=['POST'])
@login_required
def set_password():
    try:
        old_password=request.json['old_password']
        new_password=request.json['new_password']

        user=User.query.filter_by(email=current_user.email,username=current_user.username).first()

        if user and bcrypt.check_password_hash(user.password_hashed,old_password):
            user.password_hashed=bcrypt.generate_password_hash(new_password)
            db.session.commit()
            return jsonify({'message':f'{user.username} you have changed your password'}),200
        else:
            return jsonify({'message':f'Invalid  passsword'}),404
    except Exception as error:
        print(error)
        return jsonify({'message':'something wrong please try  later'}), 500

# Sets or changes the PIN used to unlock this specific profile when switching
# between the linked accounts under the same email (Netflix-profile style gate).
@reader.route('/set_pin',methods=['POST'])
@login_required
def set_pin():
    try:
        password=request.json['password']
        pin=request.json['pin']

        if not bcrypt.check_password_hash(current_user.password_hashed,password):
            return jsonify({'message':'Invalid password'}),400

        if not pin or not str(pin).isdigit() or len(str(pin)) != 4:
            return jsonify({'message':'PIN must be exactly 4 digits'}),400

        user=User.query.filter_by(email=current_user.email,username=current_user.username).first()
        user.pin_hash=bcrypt.generate_password_hash(str(pin))
        user.pin_failed_attempts=0
        user.pin_locked_until=None
        db.session.commit()
        return jsonify({'message':f'{user.username} you have set your PIN'}),200
    except Exception as error:
        print(error)
        return jsonify({'message':'something wrong please try later'}),500

@reader.route('/set_image',methods=['POST'])
@login_required
def set_image():
    try:
     
        img=request.json['img']

        user=User.query.filter_by(email=current_user.email,username=current_user.username).first()

        if user  :
            user.img= img
            db.session.commit()
            return jsonify({'message':f'{user.username} you have changed your iamge'}),200
        else:
            return jsonify({'message':f'Invalid  user'}),404
    except Exception as error:
        print(error)
        return jsonify({'message':'something wrong please try  later'}), 500        

## @brief Route for deleting a reader's account.
#
# This route allows readers to delete their own accounts. The function accepts a POST request with JSON data containing the user's email and password to confirm their identity.
# The function checks if the provided email and password match the current user's email and password using the 'current_user.email' and 'bcrypt.check_password_hash' functions.
# If the email and password are valid and match the current user's email and password, the function deletes the user's account from the database using the 'db.session.delete' function and commits the changes using the 'db.session.commit' function.
# A success message is returned to the user indicating that their account has been successfully deleted.
# If the email and password are invalid or do not match the current user's email and password, an error message is returned.
#
# @param email: The email of the current user.
# @param password: The password of the current user to confirm their identity.
#
# @return: A JSON object containing information about the result of the request to delete the account.
@reader.route('/delete_account',methods=['POST'])
@login_required
def delete_account():
    try:
        email=current_user.email
        password=request.json['password']
        if current_user.email==email and bcrypt.check_password_hash(current_user.password_hashed,password):
            follow_sessions=Follow_session.query.filter_by(user_id=current_user.id).all()
            follow_packs=Follow_pack.query.filter_by(user_id=current_user.id).all()
            notifications = Notification_user.query.filter_by(user_id=current_user.id).all()
            ReaderNotification.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
            [ db.session.delete(notification) for notification in notifications ]
            [ db.session.delete(follow_session) for follow_session in follow_sessions ]
            [ db.session.delete(follow_pack) for follow_pack in follow_packs ]
            db.session.commit()

            db.session.delete(current_user)
            db.session.commit()
            return jsonify({'message':'Your account has been  deleted succesfully'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


## @brief Route for registering for a formation.
#
# This route allows users to register for a formation with the given `title`, `author`, and `date`.
# The route checks if a formation exists with the specified details and registers the current user for the formation if found.
# The user's registration is represented by a new entry in the `Follow` table in the database.
# The `follow` attribute for the registration is set to `False` initially.
#
# @return: A JSON object containing a message to notify if the registration is successful or not.
# - 'message': A message indicating the result of the registration process.
# @retval 200: If the registration is successful and the formation is found in the database.
# @retval 404: If the formation is not found in the database.
# @retval 405: If the HTTP method is not allowed (only POST is allowed).
#
@reader.route('/sessions/<int:session_id>/video-call', methods=['GET'])
@login_required
def get_reader_session_video_call(session_id):
    try:
        school_id, school_error, school_status = resolve_current_user_school_id()
        if school_error:
            return jsonify({'message': school_error}), school_status

        session_instance = Session.query.get(session_id)
        if not session_instance:
            return jsonify({'message': 'Session not found'}), 404
        if not is_online_session(session_instance):
            return jsonify({'message': 'Video call is available only for online sessions'}), 400

        pack = get_pack_in_school(session_instance.pack_id, school_id)
        if not pack:
            return jsonify({'message': 'Session not found in this school'}), 404

        follow_session = Follow_session.query.filter_by(
            user_id=current_user.id,
            session_id=session_instance.id
        ).first()
        if not follow_session or not follow_session.approved:
            return jsonify({'message': 'You are not approved for this session'}), 403

        call_data = serialize_jitsi_call(session_instance, current_user, is_moderator=False)
        db.session.commit()
        return jsonify(call_data), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to generate reader session video call: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader.route('/register_session', methods=['POST'])
@login_required
def register_session():
    try:
        token = request.json['id']    
        session_instance = db.session.query(Session).filter(Session.id == token).first()
        if session_instance:
            print(current_user.id)
            # Assuming session_instance.id is related to pack_id and book_id
            follow_pack = Follow_pack.query.filter_by(pack_id=session_instance.pack_id, user_id=current_user.id).first()       
            if follow_pack and follow_pack.approved:
                follows_count = Follow_session.query.filter_by(session_id=session_instance.id).count()
                if session_instance.capacity> follows_count:
                    #follow book 
                    follow_book_is_excited = Follow_book.query.filter_by(user_id=current_user.id, book_id=session_instance.book_id ,pack_id=session_instance.pack_id).first()
                    if not follow_book_is_excited:
                        follow_book = Follow_book(user_id=current_user.id, book_id=session_instance.book_id ,pack_id=session_instance.pack_id)
                        db.session.add(follow_book)
                    #follow session
                    follow = Follow_session(user_id=current_user.id, session_id=session_instance.id,approved=True)
                    db.session.add(follow)
                    db.session.commit()
                else :
                    return jsonify({'message': 'Session is Full'}), 404

                return jsonify({'message': 'You are registered successfully'}), 200
            else:
                return jsonify({'message': 'No matching or approved Follow_pack found'}), 404
        else:

            return jsonify({'message': 'No session found'}), 404
    except Exception as e:
        print(e)  # Print the exception for debugging purposes
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/add_user_to__session', methods=['POST'])

def add_user_to__session():
    try:
        token = request.json['token']
        user_id = request.json['user_id']
        
        session_instance = db.session.query(Session).filter(Session.id == token).first()


    
        if session_instance:
            # Assuming session_instance.id is related to pack_id and book_id
            follow_pack = Follow_pack.query.filter_by(pack_id=session_instance.pack_id, user_id=user_id).first()
           
            if follow_pack and follow_pack.approved:
                follows_count = Follow_session.query.filter_by(session_id=session_instance.id).count()
                if session_instance.capacity> follows_count:
                    #follow book 
                    follow_book_is_excited = Follow_book.query.filter_by(user_id=user_id, book_id=session_instance.book_id ,pack_id=session_instance.pack_id).first()
                    if not follow_book_is_excited:
                        follow_book = Follow_book(user_id=user_id, book_id=session_instance.book_id ,pack_id=session_instance.pack_id)
                        db.session.add(follow_book)
                    #follow session
                    follow = Follow_session(user_id=user_id, session_id=session_instance.id,approved=True)
                    db.session.add(follow)
                    db.session.commit()
                else :
                    return jsonify({'message': 'Session is Full'}), 404

                return jsonify({'message': 'User added successfully'}), 200
            else:
                return jsonify({'message': 'No matching or approved Follow_pack found'}), 404
        else:

            return jsonify({'message': 'No session found'}), 404
    except Exception as e:
        print(e)  # Print the exception for debugging purposes
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/remove_user_from_session', methods=['POST'])
def remove_user_from_session():
    try:
        token=request.json['token']
        user_id = request.json['user_id']
        

        
        session=db.session.query(Session).filter(Session.id == token).first()
        if session:
            follow_session = Follow_session.query.filter_by(user_id=user_id, session_id=session.id).first()
            follow_book  = Follow_book.query.filter_by(user_id=user_id, book_id=session.book_id).first()
            if follow_session:
                
                db.session.delete(follow_session)
                db.session.delete(follow_book)
                db.session.commit()


                return jsonify({'message': 'You have successfully canceled your registration for this session'}), 200
            else:
                return jsonify({'message': 'Subscription not found'}), 404
        else:
            return jsonify({'message': 'No session found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/cancel_register_session', methods=['POST'])
@login_required
def cancel_register_session():
    try:
        token=request.json['id']
        
        session=Session.query.filter_by(token=token).first()
        if session:
            follow_session = Follow_session.query.filter_by(user_id=current_user.id, session_id=session.id).first()

            if follow_session:
                db.session.delete(follow_session)
                db.session.commit()
                return jsonify({'message': 'You have successfully canceled your registration for this session'}), 200
            else:
                return jsonify({'message': 'You have not registered for this session'}), 404
        else:
            return jsonify({'message': 'No session found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500
    

@reader.route('/follow_pack', methods=['POST'])
@login_required
def follow_pack():
    try:
        token = request.json['id']
        code = request.json['code']
        code_to_use = Code.query.filter_by(code=code).first()
        code_id = code_to_use.pack_id
    
        
        if code_to_use:
            if code_id != int(token):
                return jsonify({'message': 'Code does not correspond to the specified pack'}), 400
            if code_to_use.status == StatusEnum.USED:
                return jsonify({'message': 'Code has already been used'}), 400

            # Change code status to 'used' (assuming StatusEnum is an Enum)
            code_to_use.user_id = current_user.id
            code_to_use.status = StatusEnum.USED
            db.session.commit()

            pack = Pack.query.filter_by(id=token).first()
            if pack:
                existing_pack = Follow_pack.query.filter_by(user_id=current_user.id, pack_id=pack.id).first()
                if not existing_pack:
                    follow_pack = Follow_pack(user_id=current_user.id, pack_id=pack.id,approved=True)
                    db.session.add(follow_pack)
                    db.session.commit()

                    followed_pack = {
                        'approved': follow_pack.approved,
                        'id': pack.id,
                        'level': pack.level,
                        'book_number': pack.book_number,
                        'price': pack.price,
                        'title': pack.title
                    }
                    return jsonify({'message': 'Pack is successfully added to your pack list', 'followed_pack': followed_pack}), 200
                else:
                    return jsonify({'message': 'You are already followed this pack'}), 200
            else:
                return jsonify({'message': 'Pack not found'}), 404
        else:
            return jsonify({'message': 'Code not found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500

        
@reader.route('/link_code', methods=['POST'])

def link_code():
    try:
        user_id = request.json['user_id']
        code = request.json['code']
        print(user_id,code)
        code_to_use = Code.query.filter_by(code=code).first()
        user =User.query.filter_by(id=user_id).first()
        print(code_to_use,user)
        if code_to_use :
            if not user :
                return jsonify({'message': 'User not found'}), 400

            # Change code status to 'used' (assuming StatusEnum is an Enum)
            code_to_use.user_id = user_id
            db.session.commit()
            return jsonify({'message': 'Code Linked successfuly'}), 200
        else:
            return jsonify({'message': 'Code not found'}), 404
    except Exception as error:
        return jsonify({'message': 'Internal server error','error':error}), 500


@reader.route('/get_followed_pack_list')
@login_required
def get_followed_pack_list():
    try:
        school_id, school_error, school_status = resolve_current_user_school_id()
        if school_error:
            return jsonify({'message': school_error}), school_status

        packs = (
            db.session.query(Pack, Follow_pack.approved)
            .join(Follow_pack)
            .outerjoin(
                SchoolPackInstance,
                and_(
                    SchoolPackInstance.pack_id == Pack.id,
                    SchoolPackInstance.shcool_id == school_id,
                    SchoolPackInstance.active.is_(True)
                )
            )
            .filter(
                Pack.id == Follow_pack.pack_id,
                Follow_pack.user_id == current_user.id,
                Pack.active.is_(True),
                or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None))
            )
        )
        followed_pack_list = []

        for followed_pack, approved in packs:
            is_global = bool(getattr(followed_pack, 'is_global_pack', False))
            followed_pack_list.append({'title': followed_pack.title, 'id': followed_pack.id, 'school_id': school_id if is_global else followed_pack.shcool_id, 'owner_school_id': followed_pack.shcool_id, 'is_global_pack': is_global, 'source': 'global' if is_global else 'school', 'read_only': is_global, 'approved': approved ,'level':followed_pack.level,'price':followed_pack.price,'book_number':followed_pack.book_number,'img':followed_pack.img})

        if followed_pack_list:
            return jsonify({'school_id': school_id, 'followed_pack_list': followed_pack_list}), 200
        else:
            return jsonify({'school_id': school_id, 'followed_pack_list': []}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@reader.route('/get_unfollowed_books')
@login_required
def get_unfollowed_books():
    try:
        school_id, school_error, school_status = resolve_current_user_school_id()
        if school_error:
            return jsonify({'message': school_error}), school_status

        # Get the packs that the user is following
        followed_packs = (
            db.session.query(Pack, Follow_pack.approved)
            .join(Follow_pack)
            .outerjoin(
                SchoolPackInstance,
                and_(
                    SchoolPackInstance.pack_id == Pack.id,
                    SchoolPackInstance.shcool_id == school_id,
                    SchoolPackInstance.active.is_(True)
                )
            )
            .filter(
                Pack.id == Follow_pack.pack_id,
                Follow_pack.user_id == current_user.id,
                Pack.active.is_(True),
                or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None))
            )
        )

        unfollowed_books_list = []

        # Iterate through each followed pack
        for followed_pack, approved in followed_packs:
            # Alias for the b  table to avoid conflicts in the join
            follow_book_alias = aliased(Follow_book)
            session_alias = aliased(Session)

            # Get the books in the followed pack that the user has not followed and has a session with a specific book_id
            unfollowed_books = db.session.query(Book, Book_pack, follow_book_alias).join(
                Book_pack,
                Book.id == Book_pack.book_id
            ).outerjoin(
                follow_book_alias,
                and_(
                    follow_book_alias.book_id == Book.id,
                    follow_book_alias.user_id == current_user.id,
                    follow_book_alias.pack_id == followed_pack.id
                )
            ).outerjoin(
                session_alias,
                and_(
                    session_alias.book_id == Book.id,
                    session_alias.pack_id == followed_pack.id
                )
            ).filter(
                Book_pack.pack_id == followed_pack.id,
                follow_book_alias.book_id.is_(None),
                session_alias.book_id.isnot(None)
            ).all()

            # Append the information to the list
            for book, book_pack, follow_book in unfollowed_books:
                is_global = bool(getattr(followed_pack, 'is_global_pack', False))
                unfollowed_books_list.append({
                    'title': book.title,
                    'book_id': book.id,
                    'pack_id': followed_pack.id,
                    'school_id': school_id if is_global else followed_pack.shcool_id,
                    'owner_school_id': followed_pack.shcool_id,
                    'is_global_pack': is_global,
                    'source': 'global' if is_global else 'school',
                    'read_only': is_global,
                    'pack_title': followed_pack.title,
                    'approved': approved,
                    'level': followed_pack.level,
                    'price': followed_pack.price,
                    'book_number': followed_pack.book_number,
                    'img': followed_pack.img
                })

        if unfollowed_books_list:
            return jsonify({'school_id': school_id, 'unfollowed_books_list': unfollowed_books_list}), 200
        else:
            return jsonify({'message': 'No unfollowed books found'}), 404
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/unfollowed_pack', methods=['POST'])
@login_required
def unfollowed_pack():
    try:
        token=request.json['id']
        
        pack=Pack.query.filter_by(token=token).first()
        if pack:
            unfollow_pack=db.session.query(Follow_pack).join(Pack).filter(Pack.id==Follow_pack.pack_id,Follow_pack.user_id==current_user.id).first()
            db.session.delete(unfollow_pack)
            db.session.commit()
            return jsonify({'message': 'This pack has been removed from your followed pack list'}), 200
        else:
            return jsonify({'message': 'You are not followed this pack'}), 400
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/apply_for_teacher_job',methods=['POST'])
@login_required
def apply_for_teacher_job():
    try:
        email=current_user.email
        description=request.json['description']
        study_level=request.json['study_level']

        user=User.query.filter_by(email=email).first()

        if user.type=='reader':
            teacher_submit=Teacher_postulate(id=user.id,description=description,study_level=study_level)
            db.session.add(teacher_submit)
            db.session.commit()
            return jsonify({'message':'Your are postulate successfully to the teacher post.You will receive a message when you will accepted'}),200
        else:
            return jsonify({'message':'You are not suscestible to been teacher'}),401
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/show_state_of_teacher_job_postulate')
@login_required
def show_state_of_teacher_job_postulate():
    try:
        teacher_submit=Teacher_postulate.query.filter_by(id=current_user.id).first()
        teacher=Teacher.query.filter_by(email=current_user.email).first()

        if teacher_submit:
            if not teacher_submit.selected:
                return jsonify({'message':'Your request treatement is in progress'}),200
        elif teacher:
                return jsonify({'message':'Congratulation you are now teacher'}),200
        else:
            return jsonify({'message':'You hadn\'t postulated to a teacher job or  your request has been rejected'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500




@reader.route('/set_profile', methods=['POST'])
@login_required
def create_or_update_profile():
    try:
        existing_profile = Profile.query.filter_by(user_id=current_user.id).first()
        data = request.get_json()
        if 'birth_day' in data:
            data['birth_day'] = datetime.strptime(data['birth_day'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d')
        if existing_profile:
            # If a profile with the user_id already exists, update it
            for field in ['first_name', 'last_name', 'phone', 'birth_day', 'address_1', 'address_2', 'state', 'country']:
                if field in data:
                    setattr(existing_profile, field, data[field])
            db.session.commit()
            profile = {
                'user_id': existing_profile.user_id,
                'first_name': existing_profile.first_name,
                'last_name': existing_profile.last_name,
                'phone': existing_profile.phone,
                'birth_day': existing_profile.birth_day,
                'address_1': existing_profile.address_1,
                'address_2': existing_profile.address_2,
                'state': existing_profile.state,
                'country': existing_profile.country
            }
            return jsonify({'message': 'Profile updated successfully','profile':profile})
        else:
            # If no profile with the user_id exists, create a new one
            new_profile = Profile(user_id=current_user.id)
            
            # Update only the fields that are present in the JSON data
            for field in ['first_name', 'last_name', 'phone', 'birth_day', 'address_1', 'address_2', 'state', 'country']:
                if field in data:
                    setattr(new_profile, field, data[field])
            
            db.session.add(new_profile)

            profile = {
                'user_id': new_profile.user_id,
                'first_name': new_profile.first_name,
                'last_name': new_profile.last_name,
                'phone': new_profile.phone,
                'birth_day': new_profile.birth_day,
                'address_1': new_profile.address_1,
                'address_2': new_profile.address_2,
                'state': new_profile.state,
                'country': new_profile.country
            }
            db.session.commit()
            return jsonify({'message': 'Profile created or updated successfully','profile':profile}), 201
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@reader.route('/my__profile', methods=['GET'])
@login_required
def get_profile():
    try:
        profile = Profile.query.filter_by(user_id=current_user.id).first()
        if profile:
            return jsonify({
                'user_id': profile.user_id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'phone': profile.phone,
                'birth_day': profile.birth_day,
                'address_1': profile.address_1,
                'address_2': profile.address_2,
                'state': profile.state,
                'country': profile.country
            })
        else:
            return jsonify({'message': 'Profile not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


        # get quiz

@reader.route('/get_all_quizs', methods=['GET'])
def get_quizs():
    try:

        url = f'{ConfigClass.QUIZ_API}quiz/quiz-list'
        req = urllib.request.Request(url) 
        response = urllib.request.urlopen(req)
        response_data = json.loads(response.read().decode('utf-8'))
        quizs = response_data  
        
        return jsonify(quizs)
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/start_quiz', methods=['POST'])
def start_quizs():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/start-quiz/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/first_question', methods=['POST'])
def first_question():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/first-question/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    question_id=data['question_id']
    user_answer =data['user_answer']

    registration_data = {
        'user_id': user_id,
        'user_answer':user_answer,
        'question_id':question_id

    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/submit/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/result', methods=['POST'])
def result():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/result/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/assigned', methods=['POST'])
def assigned():
    data = request.get_json()
    user_id = data['user_id']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/assignment'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/teacher_quiz', methods=['POST'])
def teacher_quiz():
    data = request.get_json()
    user_id = data['user_id']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/teacher_quiz'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400



@reader.route('/quiz_by_token', methods=['POST'])
def quiz_by_token():
    data = request.get_json()
    token = data['token']
    registration_data = {
        'token': token,
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/quiz-by-token'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        response_data = json.loads(response.read().decode('utf-8'))
        quiz = response_data 
        return jsonify(quiz)

    except urllib.error.HTTPError as e:
        # Handle HTTP errors (e.g., 404, 500) here
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print("API Error:", error_message)
        return jsonify({'message': error_message}), e.code
    except Exception as ex:
        # Handle other exceptions here
        print("Exception:", ex)
        return jsonify({'message': 'Internal Server Error'}), 500



@reader.route('/assign_quiz_to_user', methods=['POST'])
def assign_quiz_to_user():
    data = request.get_json()
    assigned_by = data['assigned_by']
    email =data['email']
    quiz_token =data['quiz_token']

    registration_data = {
        'assigned_by': assigned_by,
        'email': email,
        'quiz_token':quiz_token
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/assign_quiz_to_user'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 201:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/get-essay-answer', methods=['POST'])
def get_essay_answer():
    data = request.get_json()
    token = data['token']
    user_id =data['user_id']
  

    registration_data = {
        'user_id': user_id,   
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/get-essay-answer/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400     

@reader.route('/validate-essay-answer', methods=['POST'])
def validate_essay_answer():
    data = request.get_json()
    answer_token =data['answer_token']
    teacher_approval = data['teacher_approval']
    teacher_comments =data['teacher_comments']
    teacher_checked =data['teacher_checked']
    score =data['score']
    user_id =data['user_id']
  

    registration_data = {
        'user_id': user_id,   
        'answer_token':answer_token,
        'teacher_approval':teacher_approval,
        'teacher_comments':teacher_comments,
        'teacher_checked':teacher_checked,
        'score':score

    }
    print(registration_data)
    try:
        
        url = f'{ConfigClass.QUIZ_API}user/validate-essay-answer'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400   

from flask import request, jsonify
import urllib.request
import json

@reader.route('/import-quiz-json', methods=['POST'])
def import_quiz_json():
    try:
        # Check if the request contains a file
        if 'json_file' not in request.files:
            return jsonify({'error': 'No JSON file provided'}), 400

        jsonFile = request.files['json_file']

        try:
            url = f'{ConfigClass.QUIZ_API}quiz/json/{ConfigClass.QUIZ_API_KEY}'
            files = {'file': (jsonFile.filename, jsonFile.stream, 'application/json')}

            response = requests.post(url, files=files, timeout=30)

            if response.status_code == 201:
                try:
                    quiz = response.json()
                except ValueError:
                    print(f"Quiz created but response body was not JSON: {response.text!r}")
                    quiz = {}
                return jsonify(quiz), 201
            else:
                print(f"API Error: {response.status_code} - {response.reason} - {response.text}")
                try:
                    error_body = response.json()
                except ValueError:
                    error_body = {'error': response.text or 'An error occurred during the API request'}
                return jsonify(error_body), response.status_code
        except requests.exceptions.RequestException as e:
            print(f"Quiz API request failed: {str(e)}")
            return jsonify({'error': f'Could not reach the quiz service: {str(e)}'}), 502

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@reader.route('/get_packs_by_school')
def get_packs_by_shcoo():
    try:
        age_filter = request.args.get('age') 
        title_search = request.args.get('title') 
        school = int(request.args.get('school'))    
        all = int(request.args.get('all'))    
        age_enum_values = [age.value for age in StatusEnum]
        packs_query = (
            Pack.query
            .outerjoin(
                SchoolPackInstance,
                and_(
                    SchoolPackInstance.pack_id == Pack.id,
                    SchoolPackInstance.shcool_id == school,
                    SchoolPackInstance.active.is_(True)
                )
            )
            .filter(
                Pack.active.is_(True),
                or_(Pack.shcool_id == school, SchoolPackInstance.id.isnot(None))
            )
        )
        if age_filter and age_filter in age_enum_values:
            packs_query = packs_query.filter(Pack.age == age_filter)
        if title_search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{title_search}%'))
        if not school :
            
            return jsonify({'message': 'No School ID'}),400
        if all != 1:
            packs_query = packs_query.filter(Pack.public.is_(True))

        packs = packs_query.distinct().all()

        
       
        if packs:
            packs_info = []
            for pack in packs:
                enrolled = Follow_pack.query.filter_by(pack_id=pack.id).count()
                num_active_codes = Code.query.filter_by(pack_id=pack.id, status=StatusEnum.ACTIVE).count()
                pack_info = {
                    'id': pack.id,
                    'title': pack.title,
                    'level': pack.level,
                    'age': pack.age.value,
                    'price': pack.price,
                    'img': pack.img,
                    'book_number': pack.book_number,
                    'discount': pack.discount,
                    'faq': pack.faq,
                    'codes': num_active_codes ,
                    'enrolled' :enrolled,
                    'duration':pack.duration
                }
                is_global = bool(getattr(pack, 'is_global_pack', False))
                pack_info['owner_school_id'] = pack.shcool_id
                pack_info['school_id'] = school if is_global else pack.shcool_id
                pack_info['is_global_pack'] = is_global
                pack_info['source'] = 'global' if is_global else 'school'
                pack_info['read_only'] = is_global
                packs_info.append(pack_info)

            return jsonify({'packs': packs_info}), 200
        else:
            return jsonify({'message': 'No packs available'}),200
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@reader.route('/get_pack_details', methods=['GET', 'POST'])
def get_school_pack_details():
    try:
        pack_id = get_request_value('id', 'pack_id')
        school_id = get_request_value('school', 'school_id', 'shcool_id')

        if pack_id is None:
            return jsonify({'message': 'Pack ID is required'}), 400
        if school_id is None:
            return jsonify({'message': 'School ID is required'}), 400

        try:
            pack_id = int(pack_id)
            school_id = int(school_id)
        except (TypeError, ValueError):
            return jsonify({'message': 'Pack ID and School ID must be numbers'}), 400

        pack = get_pack_in_school(pack_id, school_id)
        if not pack:
            return jsonify({'message': 'Pack not found in this school'}), 404
        if not user_can_view_pack_in_school(pack, school_id):
            return jsonify({'message': 'You do not have access to this pack'}), 403

        pack_details = serialize_pack_details(pack)
        if getattr(pack, 'is_global_pack', False):
            pack_details['school_id'] = school_id
            pack_details['shcool_id'] = school_id
        return jsonify({'pack': pack_details, **pack_details}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@reader.route('/get_books_from_pack', methods=['GET', 'POST'])
def get_school_books_from_pack():
    try:
        pack_id = get_request_value('id', 'pack_id')
        school_id = get_request_value('school', 'school_id', 'shcool_id')

        if pack_id is None:
            return jsonify({'message': 'Pack ID is required'}), 400
        if school_id is None:
            return jsonify({'message': 'School ID is required'}), 400

        try:
            pack_id = int(pack_id)
            school_id = int(school_id)
        except (TypeError, ValueError):
            return jsonify({'message': 'Pack ID and School ID must be numbers'}), 400

        pack = get_pack_in_school(pack_id, school_id)
        if not pack:
            return jsonify({'message': 'Pack not found in this school'}), 404
        if not user_can_view_pack_in_school(pack, school_id):
            return jsonify({'message': 'You do not have access to this pack'}), 403

        books_in_pack = get_books_in_pack(pack.id)
        audio_map = get_published_audio_book_ids_by_book(
            [book.id for book in books_in_pack], school_id
        )
        books = [serialize_book_for_pack(book, audio_map) for book in books_in_pack]
        return jsonify({'school_id': school_id, 'pack_id': pack.id, 'books_in_pack': books, 'books': books}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500





@reader.route('/get_book_games/<int:book_id>/<game_type>')
@login_required
def get_book_games_for_type(book_id, game_type):
    try:
        school_id, school_error, school_status = resolve_game_school_id_from_session()
        if school_error:
            return jsonify({'message': school_error, 'code': 'SCHOOL_CONTEXT_REQUIRED'}), school_status

        book = Book.query.get(book_id)
        if not reader_can_access_book_in_school(book, school_id):
            return jsonify({'message': 'Book not found', 'code': 'BOOK_NOT_FOUND'}), 404

        school = Shcool.query.get(school_id)
        play_date = parse_optional_play_date(request.args.get('date'), 'date')
        payload = get_player_game_payload(school_id, book.id, game_type, play_date=play_date, school=school)
        return jsonify(payload), 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Get book game payload failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@reader.route('/get_book_games/<book_id>')
def get_book_games(book_id):
    try:
        book_text = Book_text.query.filter_by(book_id=book_id).first()

        if book_text and book_text.text:
            words_list = split_legacy_words_from_text(book_text.text)
            return jsonify({'words': words_list, 'deprecated': True}), 200
        else:
            return jsonify({'message': 'No text available'}), 200
    except Exception as e:
        logging.error('Legacy get_book_games failed: %s', e, exc_info=True)
        return jsonify({'message': 'Internal server error'}), 500


def normalize_game_result_enum(value):
    if value is None:
        raise ValueError('game is required')
    normalized = str(value).strip()
    aliases = {
        'word-explorer': 'Word-explorer',
        'Word Explorer': 'Word-explorer',
        'word_explorer': 'Word-explorer',
        'intellect_link': 'intellect-link',
        'think_word': 'think-word',
        'bee_genius': 'bee-genius',
    }
    normalized = aliases.get(normalized, normalized)
    return GameEnum(normalized)


def parse_result_day(value):
    if not value:
        return datetime.now().date()
    if hasattr(value, 'date') and not isinstance(value, str):
        return value
    return datetime.strptime(str(value), '%Y-%m-%d').date()


def parse_non_negative_seconds(value):
    if value in (None, ''):
        return 0
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, seconds)


def serialize_game_result(result, rank=None, current_user_id=None):
    user = User.query.get(result.user_id) if result.user_id else None
    return {
        'id': result.id,
        'rank': rank,
        'book_id': result.book_id,
        'score': result.score,
        'game': result.game.value,
        'user_id': result.user_id,
        'username': user.username if user else None,
        'user_img': user.img if user else None,
        'day': result.day.isoformat() if result.day else None,
        'completed': result.completed,
        'words_learned': result.words_learned or [],
        'time_spent_seconds': result.time_spent_seconds or 0,
        'is_current_user': bool(current_user_id and result.user_id == current_user_id),
    }


@reader.route('/game-result', methods=['POST'])
@reader.route('/game-result/', methods=['POST'])
def create_game_result():
    try:
        data = request.get_json()
       
     
        # Validate required fields
        if not data or 'score' not in data or 'game' not in data or 'book_id' not in data:
        
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Validate game enum
        try:
            game_status = normalize_game_result_enum(data['game'])  # Convert string to enum
        except ValueError:
       
            return jsonify({'error': 'Invalid game status'}), 400
   
        # Validate user existence
        user_id = data.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'User not found'}), 404

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if a game result already exists for the same user and day
        result_day = parse_result_day(data.get('day'))
        existing_result = Game_result.query.filter_by(user_id=user_id, day=result_day,game=game_status,book_id=data['book_id']).first()

        if existing_result:
            result_data = serialize_game_result(existing_result, current_user_id=user_id)
         
            if existing_result.completed:
                return jsonify({'message': 'You have already finished the game today. Come back tomorrow!', 'result': result_data}), 200
            else:
                return jsonify({'message': 'You already played the game. Do you want to continue?', 'result': result_data}), 200

        # If no existing result, create a new one
        new_result = Game_result(
            score=data['score'],
            book_id=data['book_id'],
            game=game_status,
            user_id=user_id,
            day=result_day,
            time_spent_seconds=parse_non_negative_seconds(data.get('time_spent_seconds')),
        )

        db.session.add(new_result)
        db.session.commit()

        result_data = serialize_game_result(new_result, current_user_id=user_id)

        return jsonify({'message': 'Game result created successfully', 'result': result_data}), 201

    except Exception as e:
        db.session.rollback()  # Rollback in case of an error
        return jsonify({'error': str(e)}), 500




@reader.route('/game-result/<int:result_id>', methods=['PUT'])
def update_game_result(result_id):
    try:
        data = request.get_json()
      
        # Fetch the existing game result
        game_result = Game_result.query.get(result_id)
        if not game_result:
            return jsonify({'error': 'Game result not found'}), 404
        
        # Validate and update fields
        if 'score' in data:
            game_result.score = data['score']
        
        if  'words_learned' in data :
            game_result.words_learned = data['words_learned']
        
        if 'completed' in data:
            game_result.completed = data['completed']

        if 'time_spent_seconds' in data:
            game_result.time_spent_seconds = parse_non_negative_seconds(data.get('time_spent_seconds'))
        
        

        db.session.commit()
   
        return jsonify({
            'message': 'Game result updated successfully',
            'result': serialize_game_result(game_result, current_user_id=game_result.user_id)
        }), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    

@reader.route('/game-results', methods=['GET'])
def get_game_results():
    try:
        game = request.args.get('game')
        book_id= request.args.get('book_id')
        
        if not game:
            return jsonify({'error': 'Game query parameter is required'}), 400
        
        try:
            game_enum = normalize_game_result_enum(game)
        except ValueError:
            return jsonify({'error': 'Invalid game type'}), 400
        
        results = (db.session.query(
                Game_result.user_id,
                func.sum(Game_result.score).label('total_score')
            )
            .filter_by(game=game_enum,book_id=book_id)
            .group_by(Game_result.user_id)
            .order_by(func.sum(Game_result.score).desc())
            .all()
        )
        
        response = []
        for rank, (user_id, total_score) in enumerate(results):
            username = User.query.get(user_id).username if user_id else None
            response.append({
                'username': username,
                'score': total_score,
                'rank': rank + 1
            })
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@reader.route('/game-results-all', methods=['GET'])
def get_ranked_game_results():
     
     
    try:
        book_id= request.args.get('book_id')
        
        results = db.session.query(
            Game_result.user_id,
            func.sum(Game_result.score).label('total_score')
        
        ).filter_by(book_id=book_id).group_by(Game_result.user_id).order_by(func.sum(Game_result.score).desc()).all()

        ranked_results = [
            {"username": User.query.get(user_id).username if user_id else None, "score": total_score, "rank": rank + 1}
            for rank, (user_id, total_score) in enumerate(results)
        ]

        return jsonify(ranked_results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500   


@reader.route('/game-leaderboard', methods=['GET'])
def get_daily_game_leaderboard():
    try:
        game = request.args.get('game')
        book_id = request.args.get('book_id') or request.args.get('id')
        day = parse_result_day(request.args.get('day') or request.args.get('date'))
        limit = request.args.get('limit', 50)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 100))

        if not game:
            return jsonify({'error': 'game query parameter is required'}), 400
        if not book_id:
            return jsonify({'error': 'book_id query parameter is required'}), 400

        try:
            book_id = int(book_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'book_id must be a number'}), 400

        try:
            game_enum = normalize_game_result_enum(game)
        except ValueError:
            return jsonify({'error': 'Invalid game type'}), 400

        current_user_id = current_user.id if current_user.is_authenticated else None
        query = (
            Game_result.query
            .filter_by(book_id=book_id, game=game_enum, day=day, completed=True)
            .order_by(Game_result.id.asc())
        )
        all_results = sorted(
            query.all(),
            key=lambda result: (
                not bool(result.time_spent_seconds and result.time_spent_seconds > 0),
                result.time_spent_seconds or 0,
                result.id
            )
        )
        entries = []
        current_user_entry = None

        for index, result in enumerate(all_results, start=1):
            serialized = serialize_game_result(result, rank=index, current_user_id=current_user_id)
            if index <= limit:
                entries.append(serialized)
            if current_user_id and result.user_id == current_user_id:
                current_user_entry = serialized

        return jsonify({
            'book_id': book_id,
            'game': game_enum.value,
            'day': day.isoformat(),
            'total_players': len(all_results),
            'entries': entries,
            'current_user_entry': current_user_entry
        }), 200
    except Exception as e:
        logging.error('Get game leaderboard failed: %s', e, exc_info=True)
        return jsonify({'error': str(e)}), 500   
'''




    Followed session

'''
