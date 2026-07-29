## @file
# Blueprint for user readers' management.
# Contains routes and functions related to reader management.

import os
from uuid import uuid4

from flask import Blueprint,jsonify,abort,render_template,request,Response
from flask_login import logout_user,login_required,current_user
from extensions import login_manager,mail,db
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from models.user import User,Reader,Teacher,Admin,Assistant,SuperAdmin
from models.book_pack import Book_pack
from models.book_story import BookStory
from models.audio_book import AudioBook
from models.game_calendar_entry import GameCalendarEntry
from models.reader_story_progress import ReaderStoryProgress
from models.school_book_instance import SchoolBookInstance
from models.school_game_setting import SchoolGameSetting
from models.school_pack_instance import SchoolPackInstance
from models.global_teacher import GlobalTeacher
from models.school_public_page import (
    SchoolPublicPage,
    DEFAULT_HERO_TYPE,
    default_school_public_sections,
    generate_unique_school_slug,
    normalize_hero_type,
    normalize_public_page_sections,
    normalize_school_slug
)
from models.shcool import Shcool
from models.school_invitation_code import SchoolInvitationCode
from models.book import Book
from models.unit import Unit
from models.user_shcool import User_shcool
from models.Follow_book import Follow_book
from models.game_result import Game_result
from models.user_log import UserLog
from models.admin_audit_log import AdminAuditLog
from models.contract_plan import ContractPlan
from models.school_billing_profile import SchoolBillingProfile
from models.school_invoice import (
    INVOICE_DRAFT,
    INVOICE_OPEN,
    INVOICE_PAID,
    SchoolInvoice,
)
from models.school_seat_activation import SchoolSeatActivation
from models.school_subscription import (
    ALL_SUBSCRIPTION_STATUSES,
    CONSUMING_STATUSES,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    SchoolSubscription,
)
from models.word_progress import WordProgress, UserAchievement
from models.session import Session,Location
from models.pack_template import Pack_template
from models.pack import Pack, StatusEnum as PackAgeEnum
from models.code import Code ,StatusEnum
from models.follow_session import Follow_session
from models.teacher_postulate import Teacher_postulate
from models.follow_pack import Follow_pack
from models.session_quiz import Session_quiz
from models.about_book import About_Book
from models.book_text import Book_text
from models.word_sense import WordSense
from models.word_occurrence import WordOccurrence
from models.chapter import Chapter
from models.word_sense_suggestion import (
    SUGGESTION_TYPE_CEFR,
    SUGGESTION_TYPE_DICTIONARY,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    WordSenseSuggestion,
)
from models.platform_settings import PlatformSettings
from apps.progress_engine import (
    get_achievement_status,
    get_progress_summary,
    serialize_reader_progress,
)
from models.notification_user import Notification_user
from models.reader_notification import ReaderNotification
from models.profile import Profile
from models.chat import Chat
import logging
import requests
from apps.main.email import generate_confirmed_token
from config import ConfigClass
from flask_mail import Message
from functools import wraps
from datetime import datetime, timedelta, date
import calendar
from sqlalchemy import func, or_, and_, case, extract
from apps.main.email import admin_confirm_token, reader_confirm_token
from apps.jitsi import ensure_jitsi_room, is_online_session, serialize_jitsi_call
from apps.game_calendar import (
    GameCalendarError,
    SUPPORTED_GAME_TYPES,
    build_calendar_export_payload,
    build_calendar_template_payload,
    delete_calendar_entry,
    game_error_response,
    generate_calendar_entries,
    get_calendar_entries_query,
    get_import_setting_values,
    get_or_create_game_setting,
    get_school_game_settings,
    import_calendar_payload,
    normalize_game_type,
    parse_bool_value,
    parse_optional_play_date,
    parse_play_date,
    preview_calendar_import_payload,
    serialize_calendar_entry,
    serialize_game_setting,
    upsert_calendar_entry,
)
from apps.account_email import (
    get_parent_for_reader,
    send_removed_from_school_emails,
)
from apps.notifications import (
    commit_notification_event,
    get_session_audience_ids,
    notify_reader_removed_from_school,
    notify_book_added_to_pack,
    notify_daily_game_created,
    notify_global_pack_created,
    notify_pack_follow_approved,
    notify_school_pack_created,
    notify_session_created,
    notify_session_deleted,
    notify_session_follow_approved,
    notify_session_updated,
    notify_word_suggestion_reviewed,
    notify_word_suggestion_submitted,
)
import secrets
import string
import json
import webcolors
import random
import spacy
from apps.seats import (
    SOURCE_ADMIN_ASSIGN,
    activate_seat,
    attach_orphan_activations,
    check_capacity,
    get_active_subscription,
    release_seat,
    resolve_billing_school,
    seat_summary,
    seats_used,
)
from apps.stripe_billing import (
    StripeNotConfigured,
    create_and_send_invoice,
    void_invoice,
)
from apps.stripe_billing import is_configured as stripe_is_configured
from apps.system_migrations import (
    MigrationsDisabled,
    get_migration_status,
    run_upgrade,
)
from apps.admin.paserStory import get_tenses_words
from apps.admin.graphDBscripts.db import Neo4jDriver,DataSetDB
import nltk
from nltk.corpus import wordnet
from googletrans import Translator

translator = Translator()
ADMIN_ROLES = {'admin', 'super_admin'}
GAME_MANAGER_ROLES = ADMIN_ROLES | {'teacher'}
DEFAULT_SUPER_ADMIN_PER_PAGE = 20
MAX_SUPER_ADMIN_PER_PAGE = 100

def is_admin_role():
    return (
        current_user.is_authenticated and
        current_user.type in ADMIN_ROLES and
        current_user.confirmed and
        current_user.approved
    )

def is_game_manager_role():
    return (
        current_user.is_authenticated and
        current_user.type in GAME_MANAGER_ROLES and
        current_user.confirmed and
        current_user.approved
    )

def is_super_admin():
    return (
        current_user.is_authenticated and
        current_user.type == 'super_admin' and
        current_user.confirmed and
        current_user.approved
    )

def get_positive_int_arg(name, default_value):
    value = request.args.get(name, default_value)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number')
    if value < 1:
        raise ValueError(f'{name} must be greater than 0')
    return value

def get_super_admin_pagination_params():
    page = get_positive_int_arg('page', 1)
    per_page = get_positive_int_arg('per_page', DEFAULT_SUPER_ADMIN_PER_PAGE)
    return page, min(per_page, MAX_SUPER_ADMIN_PER_PAGE)

def get_optional_school_filter_arg():
    school_id = request.args.get('school') or request.args.get('school_id') or request.args.get('shcool_id')
    if not school_id:
        return None
    try:
        school_id = int(school_id)
    except (TypeError, ValueError):
        raise ValueError('school_id must be a number')
    if school_id < 1:
        raise ValueError('school_id must be greater than 0')
    return school_id

def get_optional_bool_arg(name):
    value = request.args.get(name)
    if value is None or value == '':
        return None

    value = str(value).strip().lower()
    if value in ['true', '1', 'yes', 'approved']:
        return True
    if value in ['false', '0', 'no', 'pending', 'unapproved']:
        return False
    raise ValueError(f'{name} must be true or false')

def parse_bool_value(value, name):
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f'{name} is required')

    value = str(value).strip().lower()
    if value in ['true', '1', 'yes', 'approved']:
        return True
    if value in ['false', '0', 'no', 'pending', 'unapproved']:
        return False
    raise ValueError(f'{name} must be true or false')

def normalize_optional_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None

def school_name_exists(name, exclude_school_id=None):
    query = Shcool.query.filter(func.lower(Shcool.name) == str(name).strip().lower())
    if exclude_school_id:
        query = query.filter(Shcool.id != exclude_school_id)
    return query.first() is not None

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
        show_public_packs=True,
        headline=f'Read with {school.name}',
        description=f'Welcome to {school.name} on IREAD.',
        sections=default_school_public_sections(school.name)
    )
    db.session.add(page)
    db.session.flush()
    return page

def serialize_school_public_page(page):
    school = page.school or Shcool.query.get(page.shcool_id)
    relative_url, full_url = build_school_public_url(page.slug)
    sections = page.sections or default_school_public_sections(school.name if school else 'this school')
    draft = page.draft_data

    return {
        'id': page.id,
        'school_id': page.shcool_id,
        'shcool_id': page.shcool_id,
        'school_name': school.name if school else None,
        'slug': page.slug,
        'active': page.active,
        'show_public_packs': page.show_public_packs,
        'logo': page.logo,
        'cover_image': page.cover_image,
        'headline': page.headline,
        'description': page.description,
        'sections': sections,
        'hero_type': page.hero_type,
        'public_url': relative_url,
        'full_public_url': full_url,
        'created_at': page.created_at.isoformat() if page.created_at else None,
        'updated_at': page.updated_at.isoformat() if page.updated_at else None,
        'published_at': page.published_at.isoformat() if page.published_at else None,
        'has_unpublished_changes': draft is not None,
        'draft': {
            'logo': draft.get('logo'),
            'cover_image': draft.get('cover_image'),
            'headline': draft.get('headline'),
            'description': draft.get('description'),
            'hero_type': draft.get('hero_type'),
            'sections': draft.get('sections')
        } if draft is not None else None
    }

CONTENT_FIELDS = ['logo', 'cover_image', 'headline', 'description']

def normalize_public_page_content_fields(data):
    fields = {}

    for field in CONTENT_FIELDS:
        if field in data:
            fields[field] = normalize_optional_text(data.get(field))

    if 'hero_type' in data:
        fields['hero_type'] = normalize_hero_type(data.get('hero_type'))

    if 'sections' in data:
        fields['sections'] = normalize_public_page_sections(data.get('sections'))

    return fields

def live_content_snapshot(page):
    return {
        'logo': page.logo,
        'cover_image': page.cover_image,
        'headline': page.headline,
        'description': page.description,
        'hero_type': page.hero_type,
        'sections': page.sections
    }

def apply_content_to_live(page, fields):
    for key, value in fields.items():
        setattr(page, key, value)
    page.updated_at = datetime.now()
    db.session.add(page)
    return page

def apply_content_to_draft(page, fields):
    if not fields:
        return page
    current_draft = dict(page.draft_data) if page.draft_data else live_content_snapshot(page)
    current_draft.update(fields)
    page.draft_data = current_draft
    page.updated_at = datetime.now()
    db.session.add(page)
    return page

def apply_school_public_page_payload(page, data, allow_slug=False):
    if 'active' in data:
        page.active = parse_bool_value(data.get('active'), 'active')

    if 'show_public_packs' in data:
        page.show_public_packs = parse_bool_value(data.get('show_public_packs'), 'show_public_packs')

    apply_content_to_live(page, normalize_public_page_content_fields(data))

    if allow_slug and 'slug' in data:
        requested_slug = normalize_school_slug(data.get('slug'))
        existing_page = SchoolPublicPage.query.filter(
            func.lower(SchoolPublicPage.slug) == requested_slug.lower(),
            SchoolPublicPage.id != page.id
        ).first()
        if existing_page:
            raise ValueError('This public page slug is already used')
        page.slug = requested_slug

    page.updated_at = datetime.now()
    db.session.add(page)
    return page

def get_positive_int_value(value, name):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number')
    if value < 1:
        raise ValueError(f'{name} must be greater than 0')
    return value

def normalize_pack_ids(value):
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]

    pack_ids = []
    for raw_pack_id in value:
        if isinstance(raw_pack_id, dict):
            raw_pack_id = raw_pack_id.get('id') or raw_pack_id.get('pack_id')
        pack_id = get_positive_int_value(raw_pack_id, 'pack_id')
        if pack_id not in pack_ids:
            pack_ids.append(pack_id)
    return pack_ids

def normalize_school_ids(value):
    if value is None:
        return None
    if not isinstance(value, list):
        value = [value]

    school_ids = []
    for raw_school_id in value:
        if isinstance(raw_school_id, dict):
            raw_school_id = raw_school_id.get('id') or raw_school_id.get('school_id') or raw_school_id.get('shcool_id')
        school_id = get_positive_int_value(raw_school_id, 'school_id')
        if school_id not in school_ids:
            school_ids.append(school_id)

    if not school_ids:
        raise ValueError('school_ids cannot be empty')

    existing_school_ids = {
        school.id
        for school in Shcool.query.filter(Shcool.id.in_(school_ids)).all()
    }
    missing_school_ids = [school_id for school_id in school_ids if school_id not in existing_school_ids]
    if missing_school_ids:
        raise ValueError(f'Invalid school_id: {missing_school_ids[0]}')

    return school_ids

def replace_user_school_memberships(user_id, school_ids):
    User_shcool.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    for school_id in school_ids:
        db.session.add(User_shcool(user_id=user_id, shcool_id=school_id))

def get_school_admin_approved_email_body(user):
    schools = get_user_schools_for_super(user.id)
    school_names = ', '.join([school['name'] for school in schools if school.get('name')]) or 'your school'
    return (
        f'Hello {user.username},\n\n'
        f'Your school admin account for {school_names} has been approved.\n'
        f'You can now sign in to the IRead admin dashboard.\n\n'
        # The admin dashboard, not FRONT_URL -- that is the reader site, which
        # has no sign-in an approved school admin can use.
        f'{ConfigClass.ADMIN_FRONT_URL}'
    )

def send_school_admin_approved_email(user):
    try:
        msg = Message(
            'Your IRead school admin account has been approved',
            recipients=[user.email],
            sender=ConfigClass.MAIL_USERNAME
        )
        msg.body = get_school_admin_approved_email_body(user)
        mail.send(msg)
        return True, None
    except Exception as error:
        logging.error('Unable to send school admin approval email: %s', error, exc_info=True)
        return False, str(error)

def get_school_welcome_email_body(user, school, password):
    return (
        f'Hello,\n\n'
        f'A dashboard account for {school.name} has been created on IRead.\n\n'
        f'Login email: {user.email}\n'
        f'Temporary password: {password}\n\n'
        f'Please sign in at {ConfigClass.FRONT_URL} — you will be asked to choose '
        f'a new password on your first login.\n'
    )

def send_school_welcome_email(user, school, password):
    try:
        msg = Message(
            'Your IRead school account has been created',
            recipients=[user.email],
            sender=ConfigClass.MAIL_USERNAME
        )
        msg.body = get_school_welcome_email_body(user, school, password)
        mail.send(msg)
        return True, None
    except Exception as error:
        logging.error('Unable to send school welcome email: %s', error, exc_info=True)
        return False, str(error)

def delete_super_user_dependencies(user_id):
    Follow_book.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Follow_session.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Follow_pack.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Notification_user.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ReaderNotification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Game_result.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Profile.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Teacher_postulate.query.filter_by(id=user_id).delete(synchronize_session=False)
    User_shcool.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    # Seats held by a deleted account return to their school. Deleted rather
    # than released because the FK to user.id goes away with the account; the
    # invoice already raised for the term is the durable billing record.
    SchoolSeatActivation.query.filter_by(user_id=user_id).delete(synchronize_session=False)

    UserLog.query.filter_by(user_id=user_id).update({'user_id': None}, synchronize_session=False)
    Code.query.filter_by(user_id=user_id).update({'user_id': None}, synchronize_session=False)
    SchoolInvitationCode.query.filter_by(created_by=user_id).update({'created_by': None}, synchronize_session=False)
    Session.query.filter_by(teacher_id=user_id).update({'teacher_id': None}, synchronize_session=False)
    Session_quiz.query.filter_by(teacher=user_id).update({'teacher': None}, synchronize_session=False)

def paginate_super_admin_query(query, serializer, collection_name):
    page, per_page = get_super_admin_pagination_params()
    total = query.order_by(None).count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total else 0

    return {
        collection_name: [serializer(item) for item in items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'max_per_page': MAX_SUPER_ADMIN_PER_PAGE
        }
    }

## @brief Decorator to enforce admin access for a view function.
#
# This decorator checks if the current user is an admin before allowing access to the decorated view function.
# If the current user is not an admin, the function returns a 404 error using the 'abort' function.
#
# @param f: The view function to be decorated.
# @return: The decorated function that enforces admin access.
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_role():
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function

def is_admin_or_assistant_role():
    return (
        current_user.is_authenticated and
        current_user.type in (ADMIN_ROLES | {'assistant'}) and
        current_user.confirmed and
        current_user.approved
    )

## @brief Decorator to enforce admin-or-assistant access for a view function.
#
# Assistants share the school-scoped user/book/pack/session management pages with
# admins (see Dashboard-iread-last-version's DashboardAssistant nav), so these routes
# need to allow both roles rather than admin_required's admin/super_admin-only check.
#
# @param f: The view function to be decorated.
# @return: The decorated function that enforces admin-or-assistant access.
def admin_or_assistant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_or_assistant_role():
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function

## @brief Records an admin/assistant/super-admin action for accountability.
#
# Best-effort: a logging failure must never break the action it is recording,
# so errors are swallowed after rolling back the (separate) failed insert.
#
# @param action: short verb describing what happened, e.g. 'delete', 'create', 'suspend'.
# @param target_type: the kind of entity acted on, e.g. 'user', 'school', 'pack'.
# @param target_id: the primary key of the affected entity, if any.
# @param details: optional short human-readable context (already-serialized string).
def log_admin_action(action, target_type, target_id=None, details=None):
    try:
        actor = current_user if current_user.is_authenticated else None
        entry = AdminAuditLog(
            actor_id=actor.id if actor else None,
            actor_username=getattr(actor, 'username', None),
            actor_role=getattr(actor, 'type', None),
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Failed to write admin audit log: {str(e)}")

def get_current_school_id():
    membership = User_shcool.query.filter_by(user_id=current_user.id).first()
    return membership.shcool_id if membership else None

def get_current_school_user_ids():
    school_id = get_current_school_id()
    if not school_id:
        return []
    memberships = User_shcool.query.filter_by(shcool_id=school_id).all()
    return [membership.user_id for membership in memberships]

def user_belongs_to_current_school(user_id):
    school_id = get_current_school_id()
    if not school_id or not user_id:
        return False
    return User_shcool.query.filter_by(user_id=user_id, shcool_id=school_id).first() is not None

def get_school_user(user_id):
    if not user_belongs_to_current_school(user_id):
        return None
    return User.query.get(user_id)

def get_school_pack(pack_id):
    school_id = get_current_school_id()
    if not school_id or not pack_id:
        return None
    return Pack.query.filter_by(id=pack_id, shcool_id=school_id, is_global_pack=False, active=True).first()

def is_global_pack(pack):
    return bool(getattr(pack, 'is_global_pack', False))

def get_school_global_pack_instance(school_id, pack_id, active_only=True):
    if not school_id or not pack_id:
        return None
    query = SchoolPackInstance.query.filter_by(shcool_id=school_id, pack_id=pack_id)
    if active_only:
        query = query.filter_by(active=True)
    return query.first()

def school_has_global_pack_access(school_id, pack_id):
    return get_school_global_pack_instance(school_id, pack_id) is not None

def create_or_reactivate_school_pack_instance(school_id, pack_id):
    instance = get_school_global_pack_instance(school_id, pack_id, active_only=False)
    if instance:
        instance.active = True
        instance.updated_at = datetime.now()
        db.session.add(instance)
        return instance, False

    instance = SchoolPackInstance(
        shcool_id=school_id,
        pack_id=pack_id,
        created_by=current_user.id,
        active=True
    )
    db.session.add(instance)
    db.session.flush()
    return instance, True

def get_global_pack_or_404(pack_id):
    return Pack.query.filter_by(id=pack_id, is_global_pack=True, active=True).first()

def school_accessible_pack_query():
    school_id = get_current_school_id()
    if not school_id:
        return Pack.query.filter(False)
    return (
        db.session.query(Pack)
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
            or_(
                Pack.shcool_id == school_id,
                SchoolPackInstance.id.isnot(None)
            )
        )
        .distinct()
    )

def get_school_accessible_pack(pack_id):
    if not pack_id:
        return None
    return school_accessible_pack_query().filter(Pack.id == pack_id).first()

def get_school_user_ids_for_school(school_id):
    return [
        user_id for (user_id,) in
        db.session.query(User_shcool.user_id).filter(User_shcool.shcool_id == school_id).all()
    ]

def remove_global_pack_from_school(instance, school_id):
    school_user_ids = get_school_user_ids_for_school(school_id)
    if school_user_ids:
        global_session_ids = [
            session_id for (session_id,) in
            db.session.query(Session.id).filter(Session.pack_id == instance.pack_id).all()
        ]
        if global_session_ids:
            Follow_session.query.filter(
                Follow_session.user_id.in_(school_user_ids),
                Follow_session.session_id.in_(global_session_ids)
            ).delete(synchronize_session=False)
        Follow_book.query.filter(
            Follow_book.user_id.in_(school_user_ids),
            Follow_book.pack_id == instance.pack_id
        ).delete(synchronize_session=False)
        Follow_pack.query.filter(
            Follow_pack.user_id.in_(school_user_ids),
            Follow_pack.pack_id == instance.pack_id
        ).delete(synchronize_session=False)

    instance.active = False
    instance.updated_at = datetime.now()
    db.session.add(instance)

def school_session_query():
    school_id = get_current_school_id()
    if not school_id:
        return Session.query.filter(False)
    return (
        db.session.query(Session)
        .join(Pack, Session.pack_id == Pack.id)
        .filter(Pack.shcool_id == school_id, Pack.is_global_pack.is_(False), Pack.active.is_(True))
    )

def get_school_session(session_id):
    if not session_id:
        return None
    return school_session_query().filter(Session.id == session_id).first()

def school_accessible_session_query():
    school_id = get_current_school_id()
    if not school_id:
        return Session.query.filter(False)
    return (
        db.session.query(Session)
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
            or_(
                Pack.shcool_id == school_id,
                SchoolPackInstance.id.isnot(None)
            )
        )
    )

def get_school_accessible_session(session_id):
    if not session_id:
        return None
    return school_accessible_session_query().filter(Session.id == session_id).first()

def code_belongs_to_current_school(code):
    if not code:
        return False
    if get_school_pack(code.pack_id):
        return True
    school_id = get_current_school_id()
    return bool(school_id and school_has_global_pack_access(school_id, code.pack_id))

def get_school_code(code_id):
    code = Code.query.get(code_id)
    if not code_belongs_to_current_school(code):
        return None
    return code

def get_school_code_by_value(code_value):
    code = Code.query.filter_by(code=code_value).first()
    if not code_belongs_to_current_school(code):
        return None
    return code

def is_platform_book(book):
    return bool(getattr(book, 'is_platform_book', False))

def get_school_platform_instance(school_id, book_id, active_only=True):
    if not school_id or not book_id:
        return None
    query = SchoolBookInstance.query.filter_by(shcool_id=school_id, book_id=book_id)
    if active_only:
        query = query.filter_by(active=True)
    return query.first()

def school_has_platform_book_access(school_id, book_id):
    if get_school_platform_instance(school_id, book_id):
        return True
    return (
        db.session.query(Book_pack)
        .join(Pack, Book_pack.pack_id == Pack.id)
        .filter(Book_pack.book_id == book_id, Pack.shcool_id == school_id)
        .first()
        is not None
    )

def create_or_reactivate_school_book_instance(school_id, book_id):
    instance = get_school_platform_instance(school_id, book_id, active_only=False)
    if instance:
        instance.active = True
        instance.updated_at = datetime.now()
        db.session.add(instance)
        return instance, False

    instance = SchoolBookInstance(
        shcool_id=school_id,
        book_id=book_id,
        created_by=current_user.id,
        active=True
    )
    db.session.add(instance)
    db.session.flush()
    return instance, True

def remove_platform_book_from_school(instance, school_id):
    school_pack_ids = [
        pack_id for (pack_id,) in db.session.query(Pack.id).filter(Pack.shcool_id == school_id).all()
    ]
    removed_pack_links = 0
    if school_pack_ids:
        links = Book_pack.query.filter(
            Book_pack.book_id == instance.book_id,
            Book_pack.pack_id.in_(school_pack_ids)
        ).all()
        for link in links:
            Follow_book.query.filter_by(book_id=instance.book_id, pack_id=link.pack_id).delete(synchronize_session=False)
            pack = Pack.query.get(link.pack_id)
            if pack and pack.book_number and pack.book_number > 0:
                pack.book_number -= 1
                db.session.add(pack)
            db.session.delete(link)
            removed_pack_links += 1

    instance.active = False
    instance.updated_at = datetime.now()
    db.session.add(instance)
    return removed_pack_links

def get_platform_book_or_404(book_id):
    return Book.query.filter_by(id=book_id, is_platform_book=True, active=True).first()

def get_book_text_entry(book_id):
    return Book_text.query.filter_by(book_id=book_id).first()

def upsert_book_text(book_id, text):
    entry = get_book_text_entry(book_id)
    if entry:
        entry.text = text
    else:
        entry = Book_text(book_id=book_id, text=text)
        db.session.add(entry)
    return entry

def get_text_payload(data):
    text = data.get('headwords')
    if text is None:
        text = data.get('text')
    if text is None:
        return None
    return str(text).strip()

def require_school_owned_editable_book(book_id):
    school_id = get_current_school_id()
    book = get_school_book(book_id)
    if not book:
        return None, 'Book not found', 404
    if is_platform_book(book):
        return None, 'IRead platform books are read-only for school admins', 403
    if book.shcool_id != school_id:
        return None, 'This book is not editable by the current school', 403
    return book, None, None

def school_book_query():
    school_id = get_current_school_id()
    if not school_id:
        return Book.query.filter(False)
    return (
        db.session.query(Book)
        .outerjoin(Book_pack, Book.id == Book_pack.book_id)
        .outerjoin(Pack, Book_pack.pack_id == Pack.id)
        .outerjoin(
            SchoolBookInstance,
            and_(
                SchoolBookInstance.book_id == Book.id,
                SchoolBookInstance.shcool_id == school_id,
                SchoolBookInstance.active.is_(True)
            )
        )
        .filter(
            Book.active.is_(True),
            or_(
                Book.shcool_id == school_id,
                Pack.shcool_id == school_id,
                SchoolBookInstance.id.isnot(None)
            )
        )
        .distinct()
    )

def get_school_book(book_id):
    if not book_id:
        return None
    return school_book_query().filter(Book.id == book_id).first()

def serialize_admin_book(book, school_id=None):
    if school_id is None:
        school_id = get_current_school_id()
    platform_book = is_platform_book(book)
    instance = get_school_platform_instance(school_id, book.id) if school_id and platform_book else None
    pack_ids = []
    if school_id:
        pack_ids = [
            pack_id for (pack_id,) in (
                db.session.query(Pack.id)
                .join(Book_pack, Pack.id == Book_pack.pack_id)
                .filter(Book_pack.book_id == book.id, Pack.shcool_id == school_id)
                .all()
            )
        ]
    return {
        'id': book.id,
        'title': book.title,
        'author': book.author,
        'img': book.img,
        'release_date': book.release_date.strftime('%Y-%m-%d') if book.release_date else None,
        'page_number': book.page_number,
        'category': book.category,
        'neo4j_id': book.neo4j_id,
        'desc': book.desc,
        'school_id': school_id if school_id else book.shcool_id,
        'owner_school_id': book.shcool_id,
        'is_platform_book': platform_book,
        'source': 'platform' if platform_book else 'school',
        'read_only': platform_book,
        'instance_id': instance.id if instance else None,
        'active': getattr(book, 'active', True),
        'archived': getattr(book, 'archived', False),
        'pack_ids': pack_ids
    }

def get_admin_books_in_pack(pack_id):
    return (
        db.session.query(Book)
        .join(Book_pack, Book.id == Book_pack.book_id)
        .filter(Book_pack.pack_id == pack_id, Book.active.is_(True))
        .all()
    )

def serialize_admin_pack_details(pack):
    context_school_id = get_current_school_id() if current_user.is_authenticated and not is_super_admin() else pack.shcool_id
    pack_data = serialize_super_pack(pack, context_school_id)
    num_active_codes = Code.query.filter_by(pack_id=pack.id, status=StatusEnum.ACTIVE).count()
    books = [serialize_admin_book(book, context_school_id) for book in get_admin_books_in_pack(pack.id)]
    pack_data.update({
        'code': num_active_codes,
        'codes': num_active_codes,
        'books': books,
        'books_in_pack': books
    })
    return pack_data

def compute_pack_engagement_impact(pack_ids):
    pack_ids = list(pack_ids or [])
    if not pack_ids:
        return {
            'subscribed_students': 0,
            'approved_subscribed_students': 0,
            'pending_subscribed_students': 0,
            'active_students': 0,
            'active_session_students': 0,
            'active_book_students': 0
        }

    approved_user_ids = [
        user_id for (user_id,) in (
            db.session.query(Follow_pack.user_id)
            .filter(
                Follow_pack.pack_id.in_(pack_ids),
                Follow_pack.approved.is_(True)
            )
            .distinct()
            .all()
        )
    ]

    active_session_user_ids = set()
    active_book_user_ids = set()

    if approved_user_ids:
        active_session_user_ids = {
            user_id
            for (user_id,) in (
                db.session.query(Follow_session.user_id)
                .join(Session, Follow_session.session_id == Session.id)
                .filter(
                    Session.pack_id.in_(pack_ids),
                    Follow_session.approved.is_(True),
                    Follow_session.user_id.in_(approved_user_ids)
                )
                .distinct()
                .all()
            )
        }
        active_book_user_ids = {
            user_id
            for (user_id,) in (
                db.session.query(Follow_book.user_id)
                .filter(
                    Follow_book.pack_id.in_(pack_ids),
                    Follow_book.user_id.in_(approved_user_ids)
                )
                .distinct()
                .all()
            )
        }

    active_user_ids = active_session_user_ids | active_book_user_ids

    subscribed_user_ids = {
        user_id for (user_id,) in (
            db.session.query(Follow_pack.user_id)
            .filter(Follow_pack.pack_id.in_(pack_ids))
            .distinct()
            .all()
        )
    }
    pending_user_ids = {
        user_id for (user_id,) in (
            db.session.query(Follow_pack.user_id)
            .filter(Follow_pack.pack_id.in_(pack_ids), Follow_pack.approved.is_(False))
            .distinct()
            .all()
        )
    }

    return {
        'subscribed_students': len(subscribed_user_ids),
        'approved_subscribed_students': len(approved_user_ids),
        'pending_subscribed_students': len(pending_user_ids),
        'active_students': len(active_user_ids),
        'active_session_students': len(active_session_user_ids),
        'active_book_students': len(active_book_user_ids)
    }

def get_pack_delete_impact(pack):
    impact = compute_pack_engagement_impact([pack.id])
    impact.update({
        'books': Book_pack.query.filter_by(pack_id=pack.id).count(),
        'sessions': Session.query.filter_by(pack_id=pack.id).count(),
        'codes': Code.query.filter_by(pack_id=pack.id).count()
    })
    return impact

def get_book_delete_impact(book):
    school_id = get_current_school_id()
    pack_ids = [
        pack_id for (pack_id,) in (
            db.session.query(Pack.id)
            .join(Book_pack, Pack.id == Book_pack.pack_id)
            .filter(Book_pack.book_id == book.id, Pack.shcool_id == school_id)
            .distinct()
            .all()
        )
    ] if school_id else []

    impact = compute_pack_engagement_impact(pack_ids)
    impact.update({
        'packs': len(pack_ids),
        'sessions': (
            Session.query.filter(Session.book_id == book.id, Session.pack_id.in_(pack_ids)).count()
            if pack_ids else 0
        )
    })
    return impact

def get_pack_request_id():
    data = request.get_json(silent=True) or {}
    pack_id = (
        request.args.get('id')
        or request.args.get('pack_id')
        or data.get('id')
        or data.get('pack_id')
    )
    if pack_id is None:
        raise ValueError('Pack ID is required')
    return get_positive_int_value(pack_id, 'pack_id')

def get_request_school_id():
    data = request.get_json(silent=True) or {}
    school_id = (
        request.args.get('school')
        or request.args.get('school_id')
        or request.args.get('shcool_id')
        or data.get('school')
        or data.get('school_id')
        or data.get('shcool_id')
    )
    if school_id is None or school_id == '':
        return None
    return get_positive_int_value(school_id, 'school_id')

def get_admin_pack_from_request():
    pack_id = get_pack_request_id()
    if is_super_admin():
        school_id = get_request_school_id()
        query = Pack.query.filter_by(id=pack_id)
        if school_id:
            query = (
                query
                .outerjoin(
                    SchoolPackInstance,
                    and_(
                        SchoolPackInstance.pack_id == Pack.id,
                        SchoolPackInstance.shcool_id == school_id,
                        SchoolPackInstance.active.is_(True)
                    )
                )
                .filter(or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None)))
            )
        return query.first()
    return get_school_accessible_pack(pack_id)

def is_allowed_story_pdf(file_storage):
    if not file_storage or not file_storage.filename:
        return False
    filename = secure_filename(file_storage.filename)
    if not filename.lower().endswith('.pdf'):
        return False
    return file_storage.mimetype in ['application/pdf', 'application/octet-stream', 'binary/octet-stream']

def get_file_size(file_storage):
    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return file_size

def get_story_upload_dir(school_id, book_id):
    upload_root = os.path.abspath(ConfigClass.STORY_UPLOAD_DIR)
    owner_folder = str(school_id) if school_id is not None else 'platform'
    upload_dir = os.path.join(upload_root, owner_folder, str(book_id))
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

def serialize_book_story(story):
    return {
        'id': story.id,
        'book_id': story.book_id,
        'school_id': story.shcool_id,
        'source': 'platform' if story.shcool_id is None else 'school',
        'read_only': story.shcool_id is None and not is_super_admin(),
        'uploaded_by': story.uploaded_by,
        'title': story.title,
        'description': story.description,
        'original_filename': story.original_filename,
        'mime_type': story.mime_type,
        'file_size': story.file_size,
        'page_count': story.page_count,
        'active': story.active,
        'created_at': story.created_at.isoformat() if story.created_at else None,
        'updated_at': story.updated_at.isoformat() if story.updated_at else None
    }

def get_school_book_story(story_id):
    school_id = get_current_school_id()
    if not school_id or not story_id:
        return None
    return BookStory.query.filter_by(id=story_id, shcool_id=school_id).first()

def serialize_school_book_instance(instance):
    book = Book.query.get(instance.book_id)
    book_data = serialize_admin_book(book, instance.shcool_id) if book else None
    return {
        'id': instance.id,
        'school_id': instance.shcool_id,
        'book_id': instance.book_id,
        'created_by': instance.created_by,
        'active': instance.active,
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
        'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        'book': book_data
    }

def serialize_platform_book(book, school_id=None, include_details=False):
    school_id = school_id or get_current_school_id()
    data = serialize_admin_book(book, school_id)
    data['source'] = 'platform'
    data['read_only'] = not is_super_admin()
    data['school_id'] = school_id
    data['has_audio_story'] = AudioBook.query.filter_by(
        book_id=book.id,
        shcool_id=None,
        active=True
    ).first() is not None
    data['has_headwords'] = get_book_text_entry(book.id) is not None
    data['instances_count'] = SchoolBookInstance.query.filter_by(book_id=book.id, active=True).count()
    if school_id:
        data['already_added'] = get_school_platform_instance(school_id, book.id) is not None
        data['usable_in_school'] = data['already_added'] or school_has_platform_book_access(school_id, book.id)
    if include_details:
        text_entry = get_book_text_entry(book.id)
        data['headwords'] = text_entry.text if text_entry else None
        data['school_instances'] = [
            serialize_school_book_instance(instance)
            for instance in SchoolBookInstance.query.filter_by(book_id=book.id, active=True).order_by(SchoolBookInstance.id.desc()).all()
        ]
    return data

def get_book_request_data():
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        return request.form
    return request.get_json(silent=True) or {}

def apply_book_metadata(book, data, require_title_author=False):
    if require_title_author:
        for field in ['title', 'author']:
            if field not in data or not str(data.get(field) or '').strip():
                raise ValueError(f'{field.capitalize()} is required')

    if 'title' in data:
        title = str(data.get('title') or '').strip()
        if not title:
            raise ValueError('Title cannot be empty')
        book.title = title
    if 'author' in data:
        author = str(data.get('author') or '').strip()
        if not author:
            raise ValueError('Author cannot be empty')
        book.author = author
    if 'img' in data:
        book.img = data.get('img')
    if 'release_date' in data:
        book.release_date = data.get('release_date') or None
    if 'page_number' in data:
        book.page_number = data.get('page_number') or None
    if 'category' in data:
        book.category = data.get('category')
    if 'desc' in data:
        book.desc = data.get('desc')
    if 'neo4j_id' in data:
        book.neo4j_id = data.get('neo4j_id') or None
    return book

def parse_pack_age(value):
    if value is None or value == '':
        return None
    if isinstance(value, PackAgeEnum):
        return value
    value = str(value).strip().lower()
    for age in PackAgeEnum:
        if value in [age.value, age.name.lower()]:
            return age
    raise ValueError('age must be kid, teenager, or adult')

def apply_pack_metadata(pack, data, require_title=False):
    if require_title and not str(data.get('title') or '').strip():
        raise ValueError('Title is required')
    if 'title' in data:
        title = str(data.get('title') or '').strip()
        if not title:
            raise ValueError('Title cannot be empty')
        pack.title = title
    if 'level' in data:
        pack.level = data.get('level')
    if 'desc' in data:
        pack.desc = data.get('desc')
    if 'age' in data:
        pack.age = parse_pack_age(data.get('age'))
    if 'img' in data:
        pack.img = data.get('img')
    if 'price' in data:
        pack.price = data.get('price') or 0
    if 'discount' in data:
        pack.discount = data.get('discount') or 0
    if 'duration' in data:
        pack.duration = data.get('duration') or 0
    if 'faq' in data:
        pack.faq = data.get('faq')
    if 'public' in data:
        pack.public = parse_bool_value(data.get('public'), 'public')
    if 'product_id_invoicing_api' in data:
        pack.product_id_invoicing_api = data.get('product_id_invoicing_api')
    return pack

def get_global_pack_book_ids(pack_id):
    return [
        book_id for (book_id,) in
        db.session.query(Book_pack.book_id).filter(Book_pack.pack_id == pack_id).all()
    ]

def get_global_pack_book(pack_id, book_id):
    return (
        db.session.query(Book)
        .join(Book_pack, Book.id == Book_pack.book_id)
        .filter(
            Book_pack.pack_id == pack_id,
            Book.id == book_id,
            Book.is_platform_book.is_(True),
            Book.active.is_(True)
        )
        .first()
    )

def get_global_pack_unit(pack_id, unit_id):
    return Unit.query.filter_by(id=unit_id, pack_id=pack_id).first()

def parse_session_location(value):
    if value is None or value == '':
        return Location.ONLINE
    if isinstance(value, Location):
        return value
    value = str(value).strip().lower()
    for location in Location:
        if value in [location.value, location.name.lower()]:
            return location
    raise ValueError('location must be online or classroom')

def parse_datetime_value(value, name):
    if isinstance(value, datetime):
        return value
    if not value:
        raise ValueError(f'{name} is required')
    value = str(value).replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{name} must be a valid ISO datetime')

def is_active_global_teacher(teacher_id):
    return GlobalTeacher.query.filter_by(teacher_id=teacher_id, active=True).first() is not None

def serialize_global_teacher(global_teacher):
    teacher = User.query.get(global_teacher.teacher_id)
    return {
        'teacher_id': global_teacher.teacher_id,
        'id': global_teacher.teacher_id,
        'username': teacher.username if teacher else None,
        'email': teacher.email if teacher else None,
        'img': teacher.img if teacher else None,
        'active': global_teacher.active,
        'created_by': global_teacher.created_by,
        'created_at': global_teacher.created_at.isoformat() if global_teacher.created_at else None
    }

def serialize_school_pack_instance(instance):
    pack = Pack.query.get(instance.pack_id)
    return {
        'id': instance.id,
        'school_id': instance.shcool_id,
        'pack_id': instance.pack_id,
        'created_by': instance.created_by,
        'active': instance.active,
        'public': instance.public,
        'display_name': instance.display_name,
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
        'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        'pack': serialize_super_pack(pack, instance.shcool_id) if pack else None
    }

def serialize_unit(unit):
    return {
        'id': unit.id,
        'name': unit.name,
        'book_id': unit.book_id,
        'pack_id': unit.pack_id
    }

def serialize_session(session):
    teacher = User.query.get(session.teacher_id) if session.teacher_id else None
    return {
        'id': session.id,
        'name': session.name,
        'img': session.img,
        'capacity': session.capacity,
        'book_id': session.book_id,
        'unit_id': session.unit_id,
        'teacher_id': session.teacher_id,
        'teacher_name': teacher.username if teacher else None,
        'teacher_email': teacher.email if teacher else None,
        'price': session.price,
        'discount': session.discount,
        'location': session.location.value if session.location else None,
        'start_date': session.start_date.isoformat() if session.start_date else None,
        'end_date': session.end_date.isoformat() if session.end_date else None,
        'pack_id': session.pack_id,
        'description': session.description,
        'active': session.active,
        'jitsi_room': session.jitsi_room,
        'meet_link': session.meet_link,
        'video_call_available': is_online_session(session),
        'enrolled': Follow_session.query.filter_by(session_id=session.id).count()
    }

def serialize_global_pack(pack, school_id=None, include_details=False):
    data = serialize_super_pack(pack, school_id)
    data['source'] = 'global'
    data['is_global_pack'] = True
    data['read_only'] = not is_super_admin()
    data['book_number'] = Book_pack.query.filter_by(pack_id=pack.id).count()
    if school_id:
        data['already_added'] = get_school_global_pack_instance(school_id, pack.id) is not None
    data['instances_count'] = SchoolPackInstance.query.filter_by(pack_id=pack.id, active=True).count()
    if include_details:
        data['books'] = [serialize_admin_book(book, school_id) for book in get_admin_books_in_pack(pack.id)]
        data['books_in_pack'] = data['books']
        data['units'] = [
            serialize_unit(unit)
            for unit in Unit.query.filter_by(pack_id=pack.id).order_by(Unit.id.desc()).all()
        ]
        data['sessions'] = [
            serialize_session(session)
            for session in Session.query.filter_by(pack_id=pack.id).order_by(Session.id.desc()).all()
        ]
        data['school_instances'] = [
            serialize_school_pack_instance(instance)
            for instance in SchoolPackInstance.query.filter_by(pack_id=pack.id, active=True).order_by(SchoolPackInstance.id.desc()).all()
        ]
    return data

def get_user_schools_for_super(user_id):
    memberships = (
        db.session.query(User_shcool, Shcool)
        .join(Shcool, User_shcool.shcool_id == Shcool.id)
        .filter(User_shcool.user_id == user_id)
        .all()
    )
    return [{'id': school.id, 'name': school.name} for membership, school in memberships]

def serialize_super_user(user):
    suspender = User.query.get(user.suspended_by) if user.suspended_by else None
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'img': user.img,
        'role': user.type,
        'confirmed': user.confirmed,
        'approved': user.approved,
        'status': 'suspended' if not user.is_active else ('approved' if user.approved else 'pending_approval'),
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'quiz_id': getattr(user, 'quiz_id', None),
        'schools': get_user_schools_for_super(user.id),
        'is_active': user.is_active,
        'suspended_at': user.suspended_at.isoformat() if user.suspended_at else None,
        'suspended_by': user.suspended_by,
        'suspended_by_name': suspender.username if suspender else None,
        'suspended_reason': user.suspended_reason
    }

def serialize_super_user_detail(user):
    user_data = serialize_super_user(user)
    if user.type == 'teacher':
        teacher = Teacher.query.get(user.id)
        if teacher:
            user_data['description'] = teacher.description
            user_data['study_level'] = teacher.study_level
            user_data['available'] = teacher.available
    if user.type == 'reader':
        reader = Reader.query.get(user.id)
        if reader:
            user_data['level'] = reader.level
            user_data['client_id_invoicing_api'] = reader.client_id_invoicing_api
    if user.type == 'admin':
        admin_user = Admin.query.get(user.id)
        if admin_user:
            user_data['user_id_invoicing_api'] = admin_user.user_id_invoicing_api
    if user.type == 'assistant':
        assistant = Assistant.query.get(user.id)
        if assistant:
            user_data['user_id_invoicing_api'] = assistant.user_id_invoicing_api
    return user_data

def serialize_super_pack(pack, school_id=None):
    context_school_id = school_id
    if context_school_id is None and current_user.is_authenticated and not is_super_admin():
        context_school_id = get_current_school_id()
    global_pack = is_global_pack(pack)
    instance = get_school_global_pack_instance(context_school_id, pack.id) if context_school_id and global_pack else None
    school = Shcool.query.get(pack.shcool_id) if pack.shcool_id else None
    enrolled_query = Follow_pack.query.filter_by(pack_id=pack.id)
    if context_school_id and not is_super_admin():
        school_user_ids = get_school_user_ids_for_school(context_school_id)
        enrolled_count = enrolled_query.filter(Follow_pack.user_id.in_(school_user_ids)).count() if school_user_ids else 0
    else:
        enrolled_count = enrolled_query.count()
    # A global pack's `public`/`title` are shared across every school that
    # joined it (super-admin/B2C scope). When we have a school context,
    # surface that school's own publish choice + rename instead.
    effective_title = (instance.display_name or pack.title) if instance else pack.title
    effective_public = instance.public if instance else pack.public
    return {
        'id': pack.id,
        'title': effective_title,
        'default_title': pack.title,
        'display_name': instance.display_name if instance else None,
        'level': pack.level,
        'age': pack.age.value if pack.age else None,
        'price': pack.price,
        'img': pack.img,
        'book_number': pack.book_number,
        'discount': pack.discount,
        'desc': pack.desc,
        'faq': pack.faq,
        'duration': pack.duration,
        'product_id_invoicing_api': pack.product_id_invoicing_api,
        'public': effective_public,
        'school_id': context_school_id if global_pack and context_school_id else pack.shcool_id,
        'shcool_id': context_school_id if global_pack and context_school_id else pack.shcool_id,
        'owner_school_id': pack.shcool_id,
        'school': school.name if school else None,
        'is_global_pack': global_pack,
        'source': 'global' if global_pack else 'school',
        'read_only': global_pack and not is_super_admin(),
        'instance_id': instance.id if instance else None,
        'active': getattr(pack, 'active', True),
        'codes': Code.query.filter_by(pack_id=pack.id, status=StatusEnum.ACTIVE).count(),
        'enrolled': enrolled_count
    }

def serialize_super_book(book):
    book_data = serialize_admin_book(book)
    if is_super_admin():
        book_data['read_only'] = False
    direct_school = Shcool.query.get(book.shcool_id) if book.shcool_id else None
    pack_rows = (
        db.session.query(Pack, Shcool)
        .join(Book_pack, Pack.id == Book_pack.pack_id)
        .outerjoin(Shcool, Pack.shcool_id == Shcool.id)
        .filter(Book_pack.book_id == book.id)
        .all()
    )
    book_data['packs'] = [
        {
            'id': pack.id,
            'title': pack.title,
            'school_id': pack.shcool_id,
            'school': school.name if school else None
        }
        for pack, school in pack_rows
    ]
    schools = [
        {'id': pack.shcool_id, 'name': school.name if school else None}
        for pack, school in pack_rows
        if pack.shcool_id
    ]
    if direct_school and not any(school['id'] == direct_school.id for school in schools):
        schools.append({'id': direct_school.id, 'name': direct_school.name})
    instance_rows = (
        db.session.query(SchoolBookInstance, Shcool)
        .join(Shcool, SchoolBookInstance.shcool_id == Shcool.id)
        .filter(SchoolBookInstance.book_id == book.id, SchoolBookInstance.active.is_(True))
        .all()
    )
    for instance, school in instance_rows:
        if not any(school_data['id'] == school.id for school_data in schools):
            schools.append({'id': school.id, 'name': school.name})
    book_data['schools'] = schools
    book_data['school_instances'] = [
        {
            'id': instance.id,
            'school_id': school.id,
            'school': school.name,
            'active': instance.active
        }
        for instance, school in instance_rows
    ]
    book_data['has_story_pdf'] = BookStory.query.filter_by(book_id=book.id).first() is not None
    book_data['has_headwords'] = get_book_text_entry(book.id) is not None
    return book_data

## @brief Approval state of a school's own school-admin accounts.
#
# `Shcool.is_active` is only a suspension switch (it defaults to True), so a
# school that signed itself up is "not suspended" from the moment the form is
# submitted — while its school admin still sits in the super admin's approval
# queue. Approval lives on the User row, never on the school, so school status
# has to be derived from its admins: in this product "active" means approved.
#
# Returns (admin_count, approved_admin_count). `approved` is nullable on legacy
# rows, so it is read for truthiness exactly like the login check does.
def school_admin_approval_state(school_id):
    rows = (
        db.session.query(User.approved)
        .join(User_shcool, User_shcool.user_id == User.id)
        .filter(User_shcool.shcool_id == school_id, User.type == 'admin')
        .all()
    )
    approved = sum(1 for row in rows if row[0])
    return len(rows), approved


## @brief School ids that have at least one school admin and none approved yet.
# The platform-wide counterpart of school_admin_approval_state(), for analytics.
def pending_approval_school_ids():
    with_admin = set()
    with_approved_admin = set()
    rows = (
        db.session.query(User_shcool.shcool_id, User.approved)
        .join(User, User.id == User_shcool.user_id)
        .filter(User.type == 'admin')
        .all()
    )
    for school_id, approved in rows:
        with_admin.add(school_id)
        if approved:
            with_approved_admin.add(school_id)
    return with_admin - with_approved_admin


def serialize_super_school(school):
    user_count = User_shcool.query.filter_by(shcool_id=school.id).count()
    pack_count = Pack.query.filter_by(shcool_id=school.id).count()
    book_count = (
        db.session.query(Book.id)
        .outerjoin(
            SchoolBookInstance,
            and_(
                SchoolBookInstance.book_id == Book.id,
                SchoolBookInstance.shcool_id == school.id,
                SchoolBookInstance.active.is_(True)
            )
        )
        .outerjoin(Book_pack, Book.id == Book_pack.book_id)
        .outerjoin(Pack, Book_pack.pack_id == Pack.id)
        .filter(or_(Pack.shcool_id == school.id, SchoolBookInstance.id.isnot(None)))
        .distinct()
        .count()
    )
    suspender = User.query.get(school.suspended_by) if school.suspended_by else None
    admin_count, approved_admin_count = school_admin_approval_state(school.id)
    # A school with no admin at all (created by a super admin without login
    # credentials) has nothing to approve -- it is not pending, just empty.
    awaiting_admin_approval = admin_count > 0 and approved_admin_count == 0
    if not school.is_active:
        status = 'suspended'
    elif awaiting_admin_approval:
        status = 'pending_approval'
    else:
        status = 'active'
    return {
        'id': school.id,
        'name': school.name,
        'user_count': user_count,
        'pack_count': pack_count,
        'book_count': book_count,
        'seats': seat_summary(school.id),
        'is_active': school.is_active,
        'status': status,
        'admin_count': admin_count,
        'approved_admin_count': approved_admin_count,
        'pending_admin_count': admin_count - approved_admin_count,
        'awaiting_admin_approval': awaiting_admin_approval,
        'suspended_at': school.suspended_at.isoformat() if school.suspended_at else None,
        'suspended_by': school.suspended_by,
        'suspended_by_name': suspender.username if suspender else None,
        'suspended_reason': school.suspended_reason
    }

def get_school_invitation_code(invitation_code_id):
    school_id = get_current_school_id()
    if not school_id or not invitation_code_id:
        return None
    return SchoolInvitationCode.query.filter_by(id=invitation_code_id, shcool_id=school_id).first()

def serialize_school_invitation_code(invitation_code):
    school = Shcool.query.get(invitation_code.shcool_id)
    return {
        'id': invitation_code.id,
        'code': invitation_code.code,
        'shcool_id': invitation_code.shcool_id,
        'school': school.name if school else None,
        'active': invitation_code.active,
        'max_uses': invitation_code.max_uses,
        'used_count': invitation_code.used_count,
        'created_by': invitation_code.created_by,
        'created_at': invitation_code.created_at.isoformat() if invitation_code.created_at else None
    }

def user_email_exist(email):
    user=User.query.filter_by(email=email).first()
    if user :
        return True
    else:
        return False


def get_short_definition(word):
    try:
        synsets = wordnet.synsets(word)
        if synsets:
            return synsets[0].definition()  # Return the first definition
        return "Definition not found."
    except Exception as e:
        return f"Error: {str(e)}"


def translate_to_arabic(text):
    try:
        translation = translator.translate(text, src='en', dest='ar')
        return translation.text
    except Exception as e:
        return f"Translation error: {str(e)}"
## @brief Creation of the blueprint for user management by administrators.
#
# This blueprint defines routes and views for managing users by administrators.
# The blueprint is registered with the URL prefix '/admin'.
admin=Blueprint('admin',__name__,url_prefix='/admin')
bcrypt=Bcrypt()
login_manager.init_app(admin)

@admin.before_request
def require_admin_access():
    if request.method == 'OPTIONS' or request.endpoint in (
        'admin.confirm', 'admin.forget_password', 'admin.reset_password'
    ):
        return None
    if not is_admin_role():
        return abort(401)
    return None

## @brief User loader function for login manager.
#
# This function is used by the login manager to load users from the SQL database.
# It takes a unique user ID as input and returns the corresponding user object.
#
# @param user_id: The unique identifier of the user.
# @return: The user object with the specified ID.
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



## @brief Route to the admin dashboard to view their profile.
#
# This route is used by administrators to access their dashboard and view their profile details.
# The response is a JSON object containing the administrator's username and email.
#
# @return: A JSON object containing the administrator's username and email.
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    return jsonify({'email':current_user.email,'username':current_user.username}),200

@admin.route('/super/dashboard', methods=['GET'])
def super_dashboard():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        return jsonify({
            'users': User.query.count(),
            'readers': User.query.filter_by(type='reader').count(),
            'admins': User.query.filter_by(type='admin').count(),
            'pending_admins': User.query.filter(User.type == 'admin', User.approved.isnot(True)).count(),
            'super_admins': User.query.filter_by(type='super_admin').count(),
            'teachers': User.query.filter_by(type='teacher').count(),
            'assistants': User.query.filter_by(type='assistant').count(),
            'schools': Shcool.query.count(),
            'packs': Pack.query.count(),
            'books': Book.query.count(),
            'sessions': Session.query.count()
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

## @brief Strategic platform-wide analytics for the super admin: KPI pulse,
# a "needs attention" action queue, growth/engagement trends over a
# selectable range, content-health signals, and a top-schools-by-activity
# leaderboard. Reuses the same range/bucket helpers as the school-admin
# reading-analytics endpoint (resolve_dashboard_range/bucket_dates/count_in_buckets).
@admin.route('/super/analytics', methods=['GET'])
def super_analytics():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        start, now, granularity, range_key = resolve_dashboard_range(request.args.get('range'))
        buckets = bucket_dates(start, now, granularity)
        bucket_labels = [label for (_start, _end, label) in buckets]
        range_start_date = start.date()
        today = now.date()

        # --- Platform pulse ---
        schools_suspended = Shcool.query.filter_by(is_active=False).count()
        schools_total = Shcool.query.count()
        users_suspended = User.query.filter_by(is_active=False).count()
        # Self-signed-up schools are not suspended, but they are not live
        # either until their admin is approved -- keep them out of "active" so
        # this KPI agrees with the approval queue below and the schools page.
        pending_school_ids = pending_approval_school_ids()
        schools_pending_approval = (
            Shcool.query.filter(
                Shcool.is_active.is_(True),
                Shcool.id.in_(pending_school_ids)
            ).count()
            if pending_school_ids else 0
        )

        dau = db.session.query(func.count(func.distinct(UserLog.user_id))).filter(
            UserLog.created_at == today
        ).scalar() or 0
        wau = db.session.query(func.count(func.distinct(UserLog.user_id))).filter(
            UserLog.created_at >= today - timedelta(days=7)
        ).scalar() or 0
        mau = db.session.query(func.count(func.distinct(UserLog.user_id))).filter(
            UserLog.created_at >= today - timedelta(days=30)
        ).scalar() or 0

        pulse = {
            'schools_total': schools_total,
            'schools_active': schools_total - schools_suspended - schools_pending_approval,
            'schools_pending_approval': schools_pending_approval,
            'schools_suspended': schools_suspended,
            'users_total': User.query.count(),
            'users_suspended': users_suspended,
            'readers_total': User.query.filter_by(type='reader').count(),
            'admins_total': User.query.filter_by(type='admin').count(),
            'teachers_total': User.query.filter_by(type='teacher').count(),
            'assistants_total': User.query.filter_by(type='assistant').count(),
            'super_admins_total': User.query.filter_by(type='super_admin').count(),
            'dau': dau,
            'wau': wau,
            'mau': mau,
        }

        # --- Needs attention / action queue ---
        suspended_schools = (
            Shcool.query.filter_by(is_active=False)
            .order_by(Shcool.suspended_at.desc())
            .limit(10)
            .all()
        )
        pending_schools = (
            Shcool.query.filter(
                Shcool.is_active.is_(True),
                Shcool.id.in_(pending_school_ids)
            )
            .order_by(Shcool.id.desc())
            .limit(10)
            .all()
            if pending_school_ids else []
        )
        needs_attention = {
            # `approved` is nullable on legacy rows and the login check reads it
            # for truthiness, so anything that is not exactly True is pending.
            'pending_school_admins': User.query.filter(
                User.type == 'admin', User.approved.isnot(True)
            ).count(),
            'pending_teachers': User.query.filter(
                User.type == 'teacher', User.approved.isnot(True)
            ).count(),
            'pending_word_suggestions': WordSenseSuggestion.query.filter_by(status=STATUS_PENDING).count(),
            'pending_schools_count': schools_pending_approval,
            'pending_schools': [
                {'id': school.id, 'name': school.name}
                for school in pending_schools
            ],
            'suspended_schools_count': schools_suspended,
            'suspended_schools': [
                {'id': school.id, 'name': school.name, 'suspended_reason': school.suspended_reason}
                for school in suspended_schools
            ],
            'suspended_users_count': users_suspended,
        }

        # --- Growth / engagement trends over the selected range ---
        signup_rows = (
            User.query.filter(User.created_at >= range_start_date)
            .with_entities(User.created_at)
            .all()
        )
        signups_over_time = count_in_buckets(signup_rows, lambda row: row[0], buckets)

        visit_rows = (
            db.session.query(UserLog.created_at, UserLog.user_id)
            .filter(UserLog.created_at >= range_start_date, UserLog.user_id.isnot(None))
            .all()
        )
        active_readers_over_time = []
        for bucket_start, bucket_end, _label in buckets:
            distinct_ids = {
                user_id for visit_date, user_id in visit_rows
                if bucket_start.date() <= visit_date < bucket_end.date()
            }
            active_readers_over_time.append(len(distinct_ids))

        game_day_rows = (
            Game_result.query.filter(Game_result.day >= range_start_date)
            .with_entities(Game_result.day)
            .all()
        )
        games_played_over_time = count_in_buckets(game_day_rows, lambda row: row[0], buckets)

        trends = {
            'signups_over_time': signups_over_time,
            'active_readers_over_time': active_readers_over_time,
            'games_played_over_time': games_played_over_time,
        }

        # --- Content health ---
        word_sense_total = WordSense.query.count()
        word_sense_resolved = WordSense.query.filter(or_(
            WordSense.cefr_level.isnot(None),
            WordSense.cefr_override_level.isnot(None),
        )).count()
        word_sense_excluded = WordSense.query.filter(WordSense.proper_noun_excluded.is_(True)).count()
        word_sense_unresolved = word_sense_total - word_sense_resolved - word_sense_excluded

        books_total = Book.query.count()
        platform_books = Book.query.filter_by(is_platform_book=True).count()
        packs_total = Pack.query.count()
        global_packs = Pack.query.filter_by(is_global_pack=True).count()

        content_health = {
            'word_sense_total': word_sense_total,
            'word_sense_resolved': word_sense_resolved,
            'word_sense_unresolved': word_sense_unresolved,
            'word_sense_excluded': word_sense_excluded,
            'word_sense_unresolved_rate': round(word_sense_unresolved / word_sense_total, 4) if word_sense_total else 0,
            'books_total': books_total,
            'platform_books': platform_books,
            'school_books': books_total - platform_books,
            'packs_total': packs_total,
            'global_packs': global_packs,
            'school_packs': packs_total - global_packs,
        }

        # --- Engagement / achievements, and a top-schools-by-activity leaderboard ---
        mastered_this_period = WordProgress.query.filter(WordProgress.mastered_at >= start).count()
        achievements_this_period = UserAchievement.query.filter(UserAchievement.earned_at >= start).count()

        top_schools_rows = (
            db.session.query(Shcool.id, Shcool.name, func.count(Game_result.id))
            .join(User_shcool, User_shcool.shcool_id == Shcool.id)
            .join(Game_result, Game_result.user_id == User_shcool.user_id)
            .filter(Game_result.day >= range_start_date)
            .group_by(Shcool.id, Shcool.name)
            .order_by(func.count(Game_result.id).desc())
            .limit(10)
            .all()
        )

        engagement = {
            'mastered_words_this_period': mastered_this_period,
            'achievements_this_period': achievements_this_period,
            'top_schools_by_activity': [
                {'id': school_id, 'name': name, 'play_count': play_count}
                for school_id, name, play_count in top_schools_rows
            ],
        }

        return jsonify({
            'range': range_key,
            'granularity': granularity,
            'labels': bucket_labels,
            'pulse': pulse,
            'needs_attention': needs_attention,
            'trends': trends,
            'content_health': content_health,
            'engagement': engagement,
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/users', methods=['GET'])
def super_get_users():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        role = request.args.get('role')
        school_id = get_optional_school_filter_arg()
        approved = get_optional_bool_arg('approved')
        search = request.args.get('search')

        users_query = User.query
        if role:
            users_query = users_query.filter(User.type == role)
        if approved is not None:
            # NULL approved (legacy rows) blocks login just like False does, so
            # the pending filter has to catch it too -- see needs_attention.
            users_query = users_query.filter(
                User.approved.is_(True) if approved else User.approved.isnot(True)
            )
        if school_id:
            users_query = users_query.join(User_shcool, User.id == User_shcool.user_id).filter(User_shcool.shcool_id == school_id)
        if search:
            users_query = users_query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%'))
            )

        users_query = users_query.distinct().order_by(User.id.desc())
        return jsonify(paginate_super_admin_query(users_query, serialize_super_user, 'users')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/users', methods=['POST'])
def super_create_user():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = request.get_json(silent=True) or {}
        role = str(data.get('role') or data.get('type') or 'reader').strip().lower()
        allowed_roles = ['reader', 'teacher', 'assistant', 'admin', 'super_admin']
        if role not in allowed_roles:
            return jsonify({'message': 'Invalid user role'}), 400

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
        if User.query.filter_by(email=email, username=username).first():
            return jsonify({'message': 'A user with this email and username already exists'}), 409

        school_ids = None
        if role != 'super_admin':
            school_ids = normalize_school_ids(
                data.get('school_ids') or
                data.get('schools') or
                data.get('school_id') or
                data.get('shcool_id')
            )
            if not school_ids:
                return jsonify({'message': 'school_ids is required'}), 400

        user_data = {
            'username': username,
            'email': email,
            'password_hashed': bcrypt.generate_password_hash(password).decode('utf-8'),
            'created_at': datetime.now(),
            'confirmed': parse_bool_value(data.get('confirmed', True), 'confirmed'),
            'approved': parse_bool_value(data.get('approved', True), 'approved')
        }
        if data.get('img'):
            user_data['img'] = data.get('img')
        if data.get('quiz_id') is not None:
            user_data['quiz_id'] = data.get('quiz_id')

        if role == 'reader':
            new_user = Reader(**user_data)
            if data.get('level') is not None:
                new_user.level = data.get('level')
            if data.get('client_id_invoicing_api') is not None:
                new_user.client_id_invoicing_api = data.get('client_id_invoicing_api')
        elif role == 'teacher':
            description = data.get('description')
            study_level = data.get('study_level')
            if not description or not study_level:
                return jsonify({'message': 'description and study_level are required for teachers'}), 400
            new_user = Teacher(
                description=description,
                study_level=study_level,
                available=parse_bool_value(data.get('available', True), 'available'),
                **user_data
            )
        elif role == 'assistant':
            new_user = Assistant(**user_data)
            if data.get('user_id_invoicing_api') is not None:
                new_user.user_id_invoicing_api = data.get('user_id_invoicing_api')
        elif role == 'admin':
            new_user = Admin(**user_data)
            if data.get('user_id_invoicing_api') is not None:
                new_user.user_id_invoicing_api = data.get('user_id_invoicing_api')
        else:
            new_user = SuperAdmin(**user_data)

        db.session.add(new_user)
        db.session.flush()

        if school_ids:
            replace_user_school_memberships(new_user.id, school_ids)

        db.session.commit()

        log_admin_action('create', 'user', new_user.id, f'username={username}, role={role}')

        return jsonify({
            'message': 'User created successfully',
            'user': serialize_super_user_detail(new_user)
        }), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/user/<int:user_id>', methods=['GET'])
@admin.route('/super/users/<int:user_id>', methods=['GET'])
def super_get_user(user_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
        return jsonify({'user': serialize_super_user_detail(user)}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/user/<int:user_id>', methods=['PUT', 'PATCH'])
@admin.route('/super/users/<int:user_id>', methods=['PUT', 'PATCH'])
def super_update_user(user_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404

        data = request.get_json(silent=True) or {}
        was_pending_school_admin = user.type == 'admin' and not user.approved

        if 'role' in data or 'type' in data:
            return jsonify({'message': 'Changing user role is not supported by this endpoint'}), 400
        if 'username' in data:
            username = str(data.get('username')).strip()
            if not username:
                return jsonify({'message': 'username cannot be empty'}), 400
            user.username = username
        if 'email' in data:
            email = str(data.get('email')).strip().lower()
            if not email:
                return jsonify({'message': 'email cannot be empty'}), 400
            duplicate = User.query.filter(User.email == email, User.username == user.username, User.id != user.id).first()
            if duplicate:
                return jsonify({'message': 'A user with this email and username already exists'}), 409
            user.email = email
        if 'img' in data:
            user.img = data.get('img')
        if 'quiz_id' in data:
            user.quiz_id = data.get('quiz_id')
        if 'confirmed' in data:
            user.confirmed = parse_bool_value(data.get('confirmed'), 'confirmed')
        if 'approved' in data:
            user.approved = parse_bool_value(data.get('approved'), 'approved')
        if 'password' in data:
            password = data.get('password')
            if not password or not str(password).strip():
                return jsonify({'message': 'Password cannot be empty'}), 400
            user.password_hashed = bcrypt.generate_password_hash(password).decode('utf-8')

        if user.type == 'teacher':
            teacher = Teacher.query.get(user.id)
            if teacher:
                if 'description' in data:
                    teacher.description = data.get('description')
                if 'study_level' in data:
                    teacher.study_level = data.get('study_level')
                if 'available' in data:
                    teacher.available = parse_bool_value(data.get('available'), 'available')
        if user.type == 'reader':
            reader = Reader.query.get(user.id)
            if reader:
                if 'level' in data:
                    reader.level = data.get('level')
                if 'client_id_invoicing_api' in data:
                    reader.client_id_invoicing_api = data.get('client_id_invoicing_api')
        if user.type == 'admin':
            admin_user = Admin.query.get(user.id)
            if admin_user and 'user_id_invoicing_api' in data:
                admin_user.user_id_invoicing_api = data.get('user_id_invoicing_api')
        if user.type == 'assistant':
            assistant = Assistant.query.get(user.id)
            if assistant and 'user_id_invoicing_api' in data:
                assistant.user_id_invoicing_api = data.get('user_id_invoicing_api')

        school_ids = normalize_school_ids(data.get('school_ids') or data.get('schools')) if ('school_ids' in data or 'schools' in data) else None
        if school_ids is not None:
            if user.type == 'super_admin':
                return jsonify({'message': 'Super admins are not assigned to schools'}), 400
            replace_user_school_memberships(user.id, school_ids)

        db.session.commit()

        log_admin_action('update', 'user', user_id, f'fields={list(data.keys())}')

        email_sent = None
        email_error = None
        if was_pending_school_admin and user.approved:
            email_sent, email_error = send_school_admin_approved_email(user)

        response = {
            'message': 'User updated successfully',
            'user': serialize_super_user_detail(user)
        }
        if email_sent is not None:
            response['approval_email_sent'] = email_sent
            if email_error:
                response['approval_email_error'] = email_error
        return jsonify(response), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/delete_user', methods=['POST'])
def super_delete_user_from_body():
    data = request.get_json(silent=True) or {}
    user_id = data.get('id') or data.get('user_id')
    if not user_id:
        return jsonify({'message': 'user_id is required'}), 400
    try:
        user_id = get_positive_int_value(user_id, 'user_id')
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    return super_delete_user(user_id)

@admin.route('/super/user/<int:user_id>', methods=['DELETE'])
@admin.route('/super/users/<int:user_id>', methods=['DELETE'])
def super_delete_user(user_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        if user_id == current_user.id:
            return jsonify({'message': 'You cannot delete your own super admin account'}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404

        if user.type == 'super_admin' and SuperAdmin.query.count() <= 1:
            return jsonify({'message': 'Cannot delete the last super admin'}), 400

        deleted_username = user.username
        deleted_type = user.type
        delete_super_user_dependencies(user.id)
        db.session.delete(user)
        db.session.commit()

        log_admin_action(
            'delete', 'user', user_id,
            f'username={deleted_username}, type={deleted_type}'
        )

        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/approve_user', methods=['POST'])
@admin.route('/super/approve_school_admin', methods=['POST'])
@admin.route('/super/users/<int:user_id>/approve', methods=['POST'])
def super_approve_user(user_id=None):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = request.get_json(silent=True) or {}
        if user_id is None:
            user_id = data.get('id') or data.get('admin_id') or data.get('user_id')
        if not user_id:
            return jsonify({'message': 'user_id is required'}), 400

        user_id = get_positive_int_value(user_id, 'user_id')
        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404

        was_pending_school_admin = user.type == 'admin' and not user.approved
        user.confirmed = True
        user.approved = True
        db.session.commit()

        log_admin_action('approve', 'user', user_id, f'username={user.username}, type={user.type}')

        email_sent = None
        email_error = None
        if was_pending_school_admin:
            email_sent, email_error = send_school_admin_approved_email(user)

        response = {
            'message': 'User account approved successfully',
            'user': serialize_super_user_detail(user)
        }
        if user.type == 'admin':
            response['message'] = 'School admin account approved successfully'
        if email_sent is not None:
            response['approval_email_sent'] = email_sent
            if email_error:
                response['approval_email_error'] = email_error
        return jsonify(response), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/users/<int:user_id>/suspend', methods=['POST'])
def super_suspend_user(user_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        if user_id == current_user.id:
            return jsonify({'message': 'You cannot suspend your own account'}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404

        if user.type == 'super_admin' and User.query.filter_by(type='super_admin', is_active=True).count() <= 1:
            return jsonify({'message': 'Cannot suspend the last active super admin'}), 400

        data = request.get_json(silent=True) or {}
        user.is_active = False
        user.suspended_at = datetime.now()
        user.suspended_by = current_user.id
        user.suspended_reason = data.get('reason')
        db.session.commit()

        log_admin_action('suspend', 'user', user_id, f'reason={user.suspended_reason}')

        return jsonify({
            'message': 'User suspended successfully',
            'user': serialize_super_user_detail(user)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/users/<int:user_id>/activate', methods=['POST'])
def super_activate_user(user_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404

        user.is_active = True
        user.suspended_at = None
        user.suspended_by = None
        user.suspended_reason = None
        db.session.commit()

        log_admin_action('activate', 'user', user_id)

        return jsonify({
            'message': 'User reactivated successfully',
            'user': serialize_super_user_detail(user)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/books', methods=['GET'])
def super_get_books():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school_id = get_optional_school_filter_arg()
        search = request.args.get('search')

        books_query = Book.query
        if school_id:
            books_query = (
                books_query
                .outerjoin(Book_pack, Book.id == Book_pack.book_id)
                .outerjoin(Pack, Book_pack.pack_id == Pack.id)
                .outerjoin(
                    SchoolBookInstance,
                    and_(
                        SchoolBookInstance.book_id == Book.id,
                        SchoolBookInstance.shcool_id == school_id,
                        SchoolBookInstance.active.is_(True)
                    )
                )
                .filter(or_(Book.shcool_id == school_id, Pack.shcool_id == school_id, SchoolBookInstance.id.isnot(None)))
            )
        if search:
            books_query = books_query.filter(
                (Book.title.ilike(f'%{search}%')) |
                (Book.author.ilike(f'%{search}%'))
            )

        books_query = books_query.distinct().order_by(Book.id.desc())
        return jsonify(paginate_super_admin_query(books_query, serialize_super_book, 'books')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books', methods=['GET'])
def super_get_platform_books():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        search = request.args.get('search')
        books_query = Book.query.filter(Book.is_platform_book.is_(True), Book.active.is_(True))
        if search:
            books_query = books_query.filter(
                (Book.title.ilike(f'%{search}%')) |
                (Book.author.ilike(f'%{search}%')) |
                (Book.category.ilike(f'%{search}%'))
            )
        books_query = books_query.order_by(Book.id.desc())
        return jsonify(paginate_super_admin_query(books_query, serialize_platform_book, 'books')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books', methods=['POST'])
def super_create_platform_book():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = get_book_request_data()

        title = str(data.get('title') or '').strip()
        author = str(data.get('author') or '').strip()
        if not title or not author:
            return jsonify({'message': 'Title and author are required'}), 400
        if Book.query.filter_by(title=title, author=author).first():
            return jsonify({'message': 'Book with this title and author already exists'}), 409

        book = Book(
            title=title,
            author=author,
            is_platform_book=True,
            shcool_id=None,
            created_by=current_user.id,
            active=True
        )
        apply_book_metadata(book, data)
        db.session.add(book)
        db.session.flush()

        text = get_text_payload(data)
        if text:
            upsert_book_text(book.id, text)

        db.session.commit()
        return jsonify({
            'message': 'Platform book created successfully',
            'book': serialize_platform_book(book, include_details=True)
        }), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Create platform book failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books/<int:book_id>', methods=['GET'])
def super_get_platform_book(book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404
        return jsonify({'book': serialize_platform_book(book, include_details=True)}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books/<int:book_id>', methods=['PUT', 'PATCH'])
def super_update_platform_book(book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        data = request.get_json(silent=True) or {}
        new_title = str(data.get('title') or book.title or '').strip()
        new_author = str(data.get('author') or book.author or '').strip()
        if Book.query.filter(Book.title == new_title, Book.author == new_author, Book.id != book.id).first():
            return jsonify({'message': 'Book with this title and author already exists'}), 409

        apply_book_metadata(book, data)
        if 'active' in data:
            book.active = parse_bool_value(data.get('active'), 'active')
        db.session.commit()
        return jsonify({
            'message': 'Platform book updated successfully',
            'book': serialize_platform_book(book, include_details=True)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books/<int:book_id>/headwords', methods=['PUT', 'PATCH'])
def super_update_platform_book_headwords(book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404
        data = request.get_json(silent=True) or {}
        text = get_text_payload(data)
        if not text:
            return jsonify({'message': 'headwords or text is required'}), 400
        entry = upsert_book_text(book.id, text)
        db.session.commit()
        return jsonify({
            'message': 'Platform book headwords updated successfully',
            'book_id': book.id,
            'book_text': {'id': entry.id, 'book_id': entry.book_id, 'text': entry.text}
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/platform-books/<int:book_id>', methods=['DELETE'])
def super_delete_platform_book(book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        has_reader_progress = (
            db.session.query(ReaderStoryProgress)
            .join(BookStory, ReaderStoryProgress.story_id == BookStory.id)
            .filter(BookStory.book_id == book.id)
            .first()
        )
        has_school_usage = (
            SchoolBookInstance.query.filter_by(book_id=book.id, active=True).first()
            or Book_pack.query.filter_by(book_id=book.id).first()
            or has_reader_progress
        )
        if has_school_usage:
            book.active = False
            SchoolBookInstance.query.filter_by(book_id=book.id).update({'active': False}, synchronize_session=False)
            db.session.commit()
            return jsonify({'message': 'Platform book deactivated successfully'}), 200

        stories = BookStory.query.filter_by(book_id=book.id).all()
        story_paths = [story.file_path for story in stories if story.file_path]
        Book_text.query.filter_by(book_id=book.id).delete(synchronize_session=False)
        for story in stories:
            db.session.delete(story)
        db.session.delete(book)
        db.session.commit()
        for file_path in story_paths:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        return jsonify({'message': 'Platform book deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/packs', methods=['GET'])
def super_get_packs():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school_id = get_optional_school_filter_arg()
        title_search = request.args.get('title') or request.args.get('search')

        packs_query = Pack.query
        if school_id:
            packs_query = packs_query.filter(Pack.shcool_id == school_id)
        if title_search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{title_search}%'))

        packs_query = packs_query.order_by(Pack.id.desc())
        return jsonify(paginate_super_admin_query(packs_query, serialize_super_pack, 'packs')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs', methods=['GET'])
def super_get_global_packs():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        search = request.args.get('search') or request.args.get('title')
        packs_query = Pack.query.filter(Pack.is_global_pack.is_(True), Pack.active.is_(True))
        if search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{search}%'))

        packs_query = packs_query.order_by(Pack.id.desc())
        return jsonify(paginate_super_admin_query(packs_query, serialize_global_pack, 'packs')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs', methods=['POST'])
def super_create_global_pack():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = request.get_json(silent=True) or {}
        if not str(data.get('title') or '').strip():
            return jsonify({'message': 'Title is required'}), 400
        if Pack.query.filter(
            Pack.title == str(data.get('title')).strip(),
            Pack.is_global_pack.is_(True),
            Pack.active.is_(True)
        ).first():
            return jsonify({'message': 'Global pack title already exists'}), 409

        pack = Pack(
            title=str(data.get('title')).strip(),
            is_global_pack=True,
            shcool_id=None,
            created_by=current_user.id,
            active=True
        )
        apply_pack_metadata(pack, data)
        db.session.add(pack)
        db.session.commit()
        commit_notification_event(notify_global_pack_created, pack)

        return jsonify({
            'message': 'Global pack created successfully',
            'pack': serialize_global_pack(pack, include_details=True)
        }), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>', methods=['GET'])
def super_get_global_pack(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = Pack.query.filter_by(id=pack_id, is_global_pack=True).first()
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        return jsonify({'pack': serialize_global_pack(pack, include_details=True)}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>', methods=['PUT', 'PATCH'])
def super_update_global_pack(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = Pack.query.filter_by(id=pack_id, is_global_pack=True).first()
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404

        data = request.get_json(silent=True) or {}
        if 'title' in data:
            new_title = str(data.get('title') or '').strip()
            if Pack.query.filter(Pack.title == new_title, Pack.is_global_pack.is_(True), Pack.id != pack.id).first():
                return jsonify({'message': 'Global pack title already exists'}), 409
        apply_pack_metadata(pack, data)
        if 'active' in data:
            pack.active = parse_bool_value(data.get('active'), 'active')
        db.session.commit()
        return jsonify({
            'message': 'Global pack updated successfully',
            'pack': serialize_global_pack(pack, include_details=True)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>', methods=['DELETE'])
def super_delete_global_pack(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = Pack.query.filter_by(id=pack_id, is_global_pack=True).first()
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404

        pack.active = False
        SchoolPackInstance.query.filter_by(pack_id=pack.id).update({'active': False}, synchronize_session=False)
        db.session.commit()
        return jsonify({'message': 'Global pack deactivated successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/books', methods=['GET'])
def super_get_global_pack_books(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        books_query = (
            db.session.query(Book)
            .join(Book_pack, Book.id == Book_pack.book_id)
            .filter(Book_pack.pack_id == pack.id, Book.active.is_(True))
            .order_by(Book.id.desc())
        )
        return jsonify(paginate_super_admin_query(books_query, serialize_super_book, 'books')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/books/<int:book_id>', methods=['POST'])
def super_add_book_to_global_pack(pack_id, book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        book = Book.query.filter_by(id=book_id, is_platform_book=True, active=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404
        if Book_pack.query.filter_by(pack_id=pack.id, book_id=book.id).first():
            return jsonify({'message': 'Book already exists in this global pack'}), 409

        db.session.add(Book_pack(pack_id=pack.id, book_id=book.id))
        pack.book_number = (pack.book_number or 0) + 1
        db.session.add(pack)
        db.session.commit()
        commit_notification_event(notify_book_added_to_pack, pack, book)
        return jsonify({
            'message': 'Book added to global pack successfully',
            'pack': serialize_global_pack(pack, include_details=True),
            'book': serialize_super_book(book)
        }), 201
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/books/<int:book_id>', methods=['DELETE'])
def super_remove_book_from_global_pack(pack_id, book_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        link = Book_pack.query.filter_by(pack_id=pack.id, book_id=book_id).first()
        if not link:
            return jsonify({'message': 'Book is not in this global pack'}), 404
        if Session.query.filter_by(pack_id=pack.id, book_id=book_id).first():
            return jsonify({'message': 'Cannot remove book while global sessions use it'}), 400

        db.session.delete(link)
        if pack.book_number and pack.book_number > 0:
            pack.book_number -= 1
            db.session.add(pack)
        db.session.commit()
        return jsonify({'message': 'Book removed from global pack successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/units', methods=['GET'])
def super_get_global_pack_units(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        units = Unit.query.filter_by(pack_id=pack.id).order_by(Unit.id.desc()).all()
        return jsonify({'units': [serialize_unit(unit) for unit in units]}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/units', methods=['POST'])
def super_create_global_pack_unit(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        data = request.get_json(silent=True) or {}
        name = str(data.get('name') or '').strip()
        book_id = data.get('book_id')
        if not name:
            return jsonify({'message': 'Unit name is required'}), 400
        if not book_id:
            return jsonify({'message': 'book_id is required'}), 400
        book_id = get_positive_int_value(book_id, 'book_id')
        if not get_global_pack_book(pack.id, book_id):
            return jsonify({'message': 'Book not found in this global pack'}), 404
        if Unit.query.filter_by(pack_id=pack.id, book_id=book_id, name=name).first():
            return jsonify({'message': 'Unit already exists for this book in this global pack'}), 409

        unit = Unit(name=name, book_id=book_id, pack_id=pack.id)
        db.session.add(unit)
        db.session.commit()
        return jsonify({'message': 'Unit created successfully', 'unit': serialize_unit(unit)}), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/units/<int:unit_id>', methods=['PUT', 'PATCH'])
def super_update_global_pack_unit(pack_id, unit_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        if not get_global_pack_or_404(pack_id):
            return jsonify({'message': 'Global pack not found'}), 404
        unit = get_global_pack_unit(pack_id, unit_id)
        if not unit:
            return jsonify({'message': 'Unit not found'}), 404
        data = request.get_json(silent=True) or {}
        if 'name' in data:
            name = str(data.get('name') or '').strip()
            if not name:
                return jsonify({'message': 'Unit name cannot be empty'}), 400
            unit.name = name
        if 'book_id' in data:
            book_id = get_positive_int_value(data.get('book_id'), 'book_id')
            if not get_global_pack_book(pack_id, book_id):
                return jsonify({'message': 'Book not found in this global pack'}), 404
            unit.book_id = book_id
        db.session.commit()
        return jsonify({'message': 'Unit updated successfully', 'unit': serialize_unit(unit)}), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/units/<int:unit_id>', methods=['DELETE'])
def super_delete_global_pack_unit(pack_id, unit_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        if not get_global_pack_or_404(pack_id):
            return jsonify({'message': 'Global pack not found'}), 404
        unit = get_global_pack_unit(pack_id, unit_id)
        if not unit:
            return jsonify({'message': 'Unit not found'}), 404
        if Session.query.filter_by(pack_id=pack_id, unit_id=unit.id).first():
            return jsonify({'message': 'Cannot delete unit while sessions use it'}), 400
        db.session.delete(unit)
        db.session.commit()
        return jsonify({'message': 'Unit deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/sessions', methods=['GET'])
def super_get_global_pack_sessions(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        sessions_query = Session.query.filter_by(pack_id=pack.id).order_by(Session.id.desc())
        return jsonify(paginate_super_admin_query(sessions_query, serialize_session, 'sessions')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/units/<int:unit_id>/sessions', methods=['POST'])
def super_create_global_pack_session(pack_id, unit_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        unit = get_global_pack_unit(pack.id, unit_id)
        if not unit:
            return jsonify({'message': 'Unit not found'}), 404

        data = request.get_json(silent=True) or {}
        name = str(data.get('name') or '').strip()
        if not name:
            return jsonify({'message': 'Session name is required'}), 400
        book_id = get_positive_int_value(data.get('book_id') or unit.book_id, 'book_id')
        if not get_global_pack_book(pack.id, book_id):
            return jsonify({'message': 'Book not found in this global pack'}), 404
        teacher_id = get_positive_int_value(data.get('teacher_id'), 'teacher_id')
        if not is_active_global_teacher(teacher_id):
            return jsonify({'message': 'Teacher is not an active global teacher'}), 400

        session = Session(
            name=name,
            img=data.get('img'),
            capacity=data.get('capacity') or 20,
            book_id=book_id,
            unit_id=unit.id,
            teacher_id=teacher_id,
            price=data.get('price') or 0,
            discount=data.get('discount') or 0,
            location=parse_session_location(data.get('location')),
            start_date=parse_datetime_value(data.get('start_date'), 'start_date'),
            end_date=parse_datetime_value(data.get('end_date'), 'end_date'),
            pack_id=pack.id,
            description=data.get('description'),
            active=parse_bool_value(data.get('active', True), 'active'),
            meet_link=data.get('meet_link')
        )
        db.session.add(session)
        db.session.flush()
        ensure_jitsi_room(session)
        db.session.commit()
        commit_notification_event(notify_session_created, session)
        return jsonify({'message': 'Global pack session created successfully', 'session': serialize_session(session)}), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/sessions/<int:session_id>', methods=['PUT', 'PATCH'])
def super_update_global_pack_session(pack_id, session_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        session = Session.query.filter_by(id=session_id, pack_id=pack.id).first()
        if not session:
            return jsonify({'message': 'Session not found'}), 404

        was_online = is_online_session(session)
        data = request.get_json(silent=True) or {}
        if 'name' in data:
            name = str(data.get('name') or '').strip()
            if not name:
                return jsonify({'message': 'Session name cannot be empty'}), 400
            session.name = name
        if 'book_id' in data:
            book_id = get_positive_int_value(data.get('book_id'), 'book_id')
            if not get_global_pack_book(pack.id, book_id):
                return jsonify({'message': 'Book not found in this global pack'}), 404
            session.book_id = book_id
        if 'unit_id' in data:
            unit_id = get_positive_int_value(data.get('unit_id'), 'unit_id')
            if not get_global_pack_unit(pack.id, unit_id):
                return jsonify({'message': 'Unit not found'}), 404
            session.unit_id = unit_id
        if 'teacher_id' in data:
            teacher_id = get_positive_int_value(data.get('teacher_id'), 'teacher_id')
            if not is_active_global_teacher(teacher_id):
                return jsonify({'message': 'Teacher is not an active global teacher'}), 400
            session.teacher_id = teacher_id
        if 'img' in data:
            session.img = data.get('img')
        if 'capacity' in data:
            session.capacity = data.get('capacity') or 20
        if 'price' in data:
            session.price = data.get('price') or 0
        if 'discount' in data:
            session.discount = data.get('discount') or 0
        if 'location' in data:
            session.location = parse_session_location(data.get('location'))
        if 'start_date' in data:
            session.start_date = parse_datetime_value(data.get('start_date'), 'start_date')
        if 'end_date' in data:
            session.end_date = parse_datetime_value(data.get('end_date'), 'end_date')
        if 'description' in data:
            session.description = data.get('description')
        if 'active' in data:
            session.active = parse_bool_value(data.get('active'), 'active')
        if 'meet_link' in data:
            session.meet_link = data.get('meet_link')
        ensure_jitsi_room(session)
        db.session.commit()
        commit_notification_event(notify_session_updated, session, became_online=(not was_online and is_online_session(session)))
        return jsonify({'message': 'Global pack session updated successfully', 'session': serialize_session(session)}), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-packs/<int:pack_id>/sessions/<int:session_id>', methods=['DELETE'])
def super_delete_global_pack_session(pack_id, session_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        if not get_global_pack_or_404(pack_id):
            return jsonify({'message': 'Global pack not found'}), 404
        session = Session.query.filter_by(id=session_id, pack_id=pack_id).first()
        if not session:
            return jsonify({'message': 'Session not found'}), 404
        notification_user_ids = get_session_audience_ids(session)
        session_notification_data = {
            'id': session.id,
            'name': session.name,
            'pack_id': session.pack_id,
            'book_id': session.book_id,
            'school_id': None
        }
        Follow_session.query.filter_by(session_id=session.id).delete(synchronize_session=False)
        db.session.delete(session)
        db.session.commit()
        commit_notification_event(notify_session_deleted, session_notification_data, notification_user_ids)
        return jsonify({'message': 'Global pack session deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-teachers', methods=['GET'])
def super_get_global_teachers():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        search = request.args.get('search')
        teachers_query = (
            db.session.query(GlobalTeacher)
            .join(User, GlobalTeacher.teacher_id == User.id)
            .filter(GlobalTeacher.active.is_(True))
        )
        if search:
            teachers_query = teachers_query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%'))
            )
        teachers_query = teachers_query.order_by(GlobalTeacher.created_at.desc())
        return jsonify(paginate_super_admin_query(teachers_query, serialize_global_teacher, 'teachers')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-teachers', methods=['POST'])
def super_add_global_teacher():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = request.get_json(silent=True) or {}
        teacher_id = get_positive_int_value(data.get('teacher_id'), 'teacher_id')
        teacher = Teacher.query.get(teacher_id)
        if not teacher:
            return jsonify({'message': 'Teacher not found'}), 404

        global_teacher = GlobalTeacher.query.filter_by(teacher_id=teacher_id).first()
        created = False
        if global_teacher:
            global_teacher.active = True
        else:
            global_teacher = GlobalTeacher(
                teacher_id=teacher_id,
                created_by=current_user.id,
                active=True,
                created_at=datetime.now()
            )
            created = True
        db.session.add(global_teacher)
        db.session.commit()
        return jsonify({
            'message': 'Global teacher added successfully' if created else 'Global teacher reactivated successfully',
            'teacher': serialize_global_teacher(global_teacher)
        }), 201 if created else 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/global-teachers/<int:teacher_id>', methods=['DELETE'])
def super_remove_global_teacher(teacher_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        global_teacher = GlobalTeacher.query.filter_by(teacher_id=teacher_id, active=True).first()
        if not global_teacher:
            return jsonify({'message': 'Global teacher not found'}), 404
        global_teacher.active = False
        db.session.add(global_teacher)
        db.session.commit()
        return jsonify({'message': 'Global teacher removed successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

## @brief Seat usage for the calling school admin's own school.
#
# Backs the "remaining readers" meter. Deliberately scoped to the caller's
# school rather than taking a school_id, so it cannot be used to enumerate
# other tenants' seat counts -- the mistake the legacy invoicing page makes by
# calling the billing microservice straight from the browser with no school
# filter at all.
@admin.route('/school/seat-usage', methods=['GET'])
@login_required
@admin_or_assistant_required
def get_school_seat_usage():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'No school context for this admin'}), 400
        return jsonify({'school_id': school_id, 'seats': seat_summary(school_id)}), 200
    except Exception as error:
        logging.error('Failed to build seat usage: %s', error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Per-school seat usage for a super admin, for any school.
@admin.route('/super/schools/<int:school_id>/seat-usage', methods=['GET'])
def super_get_school_seat_usage(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404
        return jsonify({'school_id': school_id, 'seats': seat_summary(school_id)}), 200
    except Exception as error:
        logging.error('Failed to build seat usage for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief The contract pricing presets a super admin can pick from.
@admin.route('/super/contract-plans', methods=['GET'])
def super_get_contract_plans():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        plans = ContractPlan.query.filter_by(active=True).order_by(ContractPlan.sort_order.asc()).all()
        return jsonify({'plans': [serialize_contract_plan(plan) for plan in plans]}), 200
    except Exception as error:
        logging.error('Failed to list contract plans: %s', error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Override a school's free reader allowance (used before any contract).
#
# Chiefly for grandfathering: a school carrying a large reader base from before
# billing existed needs an allowance covering it, or its teachers hit the cap
# the day enforcement is switched on. Send null to fall back to the platform
# default.
@admin.route('/super/schools/<int:school_id>/trial-seats', methods=['PUT'])
def super_set_school_trial_seats(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        raw = data.get('trial_seats', None)

        if raw is None or raw == '':
            school.trial_seats = None
        else:
            try:
                trial_seats = int(raw)
            except (TypeError, ValueError):
                return jsonify({'message': 'trial_seats must be a number, or null to use the default'}), 400
            if trial_seats < 0:
                return jsonify({'message': 'trial_seats cannot be negative'}), 400
            school.trial_seats = trial_seats

        db.session.add(school)
        db.session.commit()

        log_admin_action('update', 'school', school_id,
                         'trial_seats=%s' % school.trial_seats)

        return jsonify({
            'message': 'Free reader allowance updated',
            'school_id': school_id,
            'trial_seats': school.trial_seats,
            'seats': seat_summary(school_id),
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to set trial seats for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Schools running on the free allowance with no contract -- the
# revenue-leak list. Ordered by how many readers they have already activated.
@admin.route('/super/billing/unlicensed', methods=['GET'])
def super_get_unlicensed_schools():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        licensed_ids = {
            school_id for (school_id,) in
            db.session.query(SchoolSubscription.shcool_id)
            .filter(SchoolSubscription.status.in_(CONSUMING_STATUSES))
            .distinct()
            .all()
        }

        rows = []
        for school in Shcool.query.all():
            if school.id in licensed_ids:
                continue
            summary = seat_summary(school.id)
            if not summary.get('seats_used'):
                continue
            rows.append({
                'school_id': school.id,
                'school_name': school.name,
                'is_active': school.is_active,
                'seats_used': summary.get('seats_used'),
                'trial_seats': summary.get('seat_limit'),
                'over_allowance': bool(
                    summary.get('seat_limit') is not None
                    and (summary.get('seats_used') or 0) > summary['seat_limit']
                ),
                'latest_status': summary.get('status'),
            })
        rows.sort(key=lambda row: row['seats_used'] or 0, reverse=True)
        return jsonify({'schools': rows, 'total': len(rows)}), 200
    except Exception as error:
        logging.error('Failed to list unlicensed schools: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Contracts for one school, newest term first.
@admin.route('/super/schools/<int:school_id>/subscriptions', methods=['GET'])
def super_get_school_subscriptions(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404
        subscriptions = (
            SchoolSubscription.query
            .filter_by(shcool_id=school_id)
            .order_by(SchoolSubscription.term_start.desc(), SchoolSubscription.id.desc())
            .all()
        )
        return jsonify({
            'school_id': school_id,
            'school_name': school.name,
            'seats': seat_summary(school_id),
            'subscriptions': [serialize_subscription(s) for s in subscriptions]
        }), 200
    except Exception as error:
        logging.error('Failed to list subscriptions for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Create a contract for a school.
#
# A plan_id prefills the seat cap and price; both stay overridable so a bespoke
# deal does not need its own plan row. The values are copied onto the contract
# rather than referenced, so editing the plan later cannot reprice a signed
# contract.
@admin.route('/super/schools/<int:school_id>/subscriptions', methods=['POST'])
def super_create_school_subscription(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        plan = None
        if data.get('plan_id'):
            plan = ContractPlan.query.get(data.get('plan_id'))
            if not plan:
                return jsonify({'message': 'Contract plan not found'}), 404

        seat_limit = data.get('seat_limit', plan.max_seats if plan else None)
        if seat_limit is None:
            return jsonify({'message': 'seat_limit is required when no plan is chosen'}), 400
        try:
            seat_limit = int(seat_limit)
        except (TypeError, ValueError):
            return jsonify({'message': 'seat_limit must be a number'}), 400
        if seat_limit < 1:
            return jsonify({'message': 'seat_limit must be at least 1'}), 400

        status = data.get('status') or STATUS_DRAFT
        if status not in ALL_SUBSCRIPTION_STATUSES:
            return jsonify({'message': 'Unknown status'}), 400

        term_start, term_end, date_error = parse_subscription_term(data, plan)
        if date_error:
            return jsonify({'message': date_error}), 400

        # Only OVERLAPPING live contracts are refused. Two live contracts with
        # sequential terms are just a renewal signed in advance, which schools
        # do routinely -- it is same-date overlap that makes "which cap applies
        # today?" ambiguous.
        if status in CONSUMING_STATUSES:
            conflict = overlapping_consuming_subscription(school_id, term_start, term_end)
            if conflict is not None:
                return jsonify({
                    'message': overlap_conflict_message(conflict),
                    'code': 'CONTRACT_TERM_OVERLAP'
                }), 409

        subscription = SchoolSubscription(
            shcool_id=school_id,
            plan_id=plan.id if plan else None,
            seat_limit=seat_limit,
            unit_price_cents=int(data.get('unit_price_cents', plan.unit_price_cents if plan else 0)),
            total_cents=int(data.get('total_cents', plan.total_cents if plan else 0)),
            currency=(data.get('currency') or (plan.currency if plan else ConfigClass.BILLING_CURRENCY)),
            term_start=term_start,
            term_end=term_end,
            grace_days=int(data.get('grace_days', 30)),
            status=status,
            auto_renew=bool(data.get('auto_renew', False)),
            notes=data.get('notes'),
            created_by=current_user.id
        )
        db.session.add(subscription)
        db.session.flush()

        attached = attach_orphan_activations(school_id, subscription)
        db.session.commit()

        log_admin_action('create', 'school_subscription', subscription.id,
                         'school=%s seats=%s status=%s' % (school_id, seat_limit, status))

        return jsonify({
            'message': 'Contract created successfully',
            'subscription': serialize_subscription(subscription),
            'seats_attached': attached,
            'seats': seat_summary(school_id)
        }), 201
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to create subscription for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Amend an existing contract.
@admin.route('/super/subscriptions/<int:subscription_id>', methods=['PUT', 'PATCH'])
def super_update_school_subscription(subscription_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        subscription = SchoolSubscription.query.get(subscription_id)
        if not subscription:
            return jsonify({'message': 'Contract not found'}), 404

        data = request.get_json(silent=True) or {}

        if 'seat_limit' in data:
            try:
                seat_limit = int(data['seat_limit'])
            except (TypeError, ValueError):
                return jsonify({'message': 'seat_limit must be a number'}), 400
            if seat_limit < 1:
                return jsonify({'message': 'seat_limit must be at least 1'}), 400
            # Warn rather than refuse: a school can legitimately be downgraded
            # while over the new cap, and blocking the edit would leave the
            # super admin with no way to record the agreed contract.
            subscription.seat_limit = seat_limit

        if 'status' in data:
            new_status = data['status']
            if new_status not in ALL_SUBSCRIPTION_STATUSES:
                return jsonify({'message': 'Unknown status'}), 400
            if new_status in CONSUMING_STATUSES and subscription.status not in CONSUMING_STATUSES:
                conflict = overlapping_consuming_subscription(
                    subscription.shcool_id, subscription.term_start,
                    subscription.term_end, exclude_id=subscription.id
                )
                if conflict is not None:
                    return jsonify({
                        'message': overlap_conflict_message(conflict),
                        'code': 'CONTRACT_TERM_OVERLAP'
                    }), 409
            subscription.status = new_status

        for money_field in ('unit_price_cents', 'total_cents'):
            if money_field in data:
                try:
                    setattr(subscription, money_field, int(data[money_field]))
                except (TypeError, ValueError):
                    return jsonify({'message': '%s must be a number' % money_field}), 400

        if 'grace_days' in data:
            try:
                subscription.grace_days = int(data['grace_days'])
            except (TypeError, ValueError):
                return jsonify({'message': 'grace_days must be a number'}), 400

        if 'term_start' in data or 'term_end' in data:
            term_start, term_end, date_error = parse_subscription_term(data, subscription.plan, subscription)
            if date_error:
                return jsonify({'message': date_error}), 400
            subscription.term_start = term_start
            subscription.term_end = term_end

        if 'auto_renew' in data:
            subscription.auto_renew = bool(data['auto_renew'])
        if 'notes' in data:
            subscription.notes = data['notes']
        if 'currency' in data and data['currency']:
            subscription.currency = data['currency']

        db.session.add(subscription)
        db.session.commit()

        log_admin_action('update', 'school_subscription', subscription.id,
                         'school=%s seats=%s status=%s' % (
                             subscription.shcool_id, subscription.seat_limit, subscription.status))

        return jsonify({
            'message': 'Contract updated successfully',
            'subscription': serialize_subscription(subscription),
            'seats': seat_summary(subscription.shcool_id)
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to update subscription %s: %s', subscription_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief End a contract early. Seats stay on the ledger -- the students are
# still activated -- but the school stops having a live cap.
@admin.route('/super/subscriptions/<int:subscription_id>/cancel', methods=['POST'])
def super_cancel_school_subscription(subscription_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        subscription = SchoolSubscription.query.get(subscription_id)
        if not subscription:
            return jsonify({'message': 'Contract not found'}), 404

        data = request.get_json(silent=True) or {}
        subscription.status = STATUS_CANCELLED
        if data.get('reason'):
            subscription.notes = ((subscription.notes or '') + '\nCancelled: %s' % data['reason']).strip()
        db.session.add(subscription)
        db.session.commit()

        log_admin_action('cancel', 'school_subscription', subscription.id,
                         'school=%s reason=%s' % (subscription.shcool_id, data.get('reason')))

        return jsonify({
            'message': 'Contract cancelled',
            'subscription': serialize_subscription(subscription)
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to cancel subscription %s: %s', subscription_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief The billing identity an invoice is made out to.
@admin.route('/super/schools/<int:school_id>/billing-profile', methods=['GET'])
def super_get_school_billing_profile(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404
        profile = SchoolBillingProfile.query.filter_by(shcool_id=school_id).first()
        return jsonify({'billing_profile': serialize_billing_profile(profile, school)}), 200
    except Exception as error:
        logging.error('Failed to read billing profile for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/super/schools/<int:school_id>/billing-profile', methods=['PUT', 'PATCH'])
def super_update_school_billing_profile(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        profile = SchoolBillingProfile.query.filter_by(shcool_id=school_id).first()
        if profile is None:
            profile = SchoolBillingProfile(shcool_id=school_id)

        for field in ('legal_name', 'billing_email', 'billing_phone', 'address_line1',
                      'address_line2', 'city', 'region', 'postal_code', 'vat_number',
                      'purchase_order_ref'):
            if field in data:
                setattr(profile, field, (data[field] or None))
        if 'country' in data:
            country = (data['country'] or '').strip().upper()
            if country and len(country) != 2:
                return jsonify({'message': 'country must be a 2-letter ISO code, e.g. IE'}), 400
            profile.country = country or None

        db.session.add(profile)
        db.session.commit()

        log_admin_action('update', 'school_billing_profile', profile.id, 'school=%s' % school_id)

        return jsonify({
            'message': 'Billing details saved',
            'billing_profile': serialize_billing_profile(profile, school)
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to save billing profile for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief A school admin's own licence: contract, seats and invoice history.
# Read-only -- schools do not edit their own commercial terms.
@admin.route('/school/licence', methods=['GET'])
@login_required
@admin_required
def get_school_licence():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'No school context for this admin'}), 400

        school = Shcool.query.get(school_id)
        subscription = get_active_subscription(school_id)
        invoices = (
            SchoolInvoice.query
            .filter_by(shcool_id=school_id)
            .order_by(SchoolInvoice.issued_at.desc(), SchoolInvoice.id.desc())
            .all()
        )
        return jsonify({
            'school_id': school_id,
            'school_name': school.name if school else None,
            'seats': seat_summary(school_id),
            'subscription': serialize_subscription(subscription) if subscription else None,
            'invoices': [serialize_school_invoice(invoice) for invoice in invoices]
        }), 200
    except Exception as error:
        logging.error('Failed to build school licence view: %s', error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief The students currently holding a seat, so an admin can see exactly
# who the licence is being spent on.
@admin.route('/school/activated-readers', methods=['GET'])
@login_required
@admin_or_assistant_required
def get_school_activated_readers():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'No school context for this admin'}), 400

        activations = (
            SchoolSeatActivation.query
            .filter(SchoolSeatActivation.shcool_id == school_id,
                    SchoolSeatActivation.released_at.is_(None))
            .order_by(SchoolSeatActivation.activated_at.desc())
            .all()
        )
        readers = []
        for activation in activations:
            user = User.query.get(activation.user_id)
            pack = Pack.query.get(activation.first_pack_id) if activation.first_pack_id else None
            readers.append({
                'user_id': activation.user_id,
                'username': user.username if user else None,
                'email': user.email if user else None,
                'activated_at': activation.activated_at.isoformat() if activation.activated_at else None,
                'first_pack_id': activation.first_pack_id,
                'first_pack_title': pack.title if pack else None,
                'source': activation.source
            })
        return jsonify({'school_id': school_id, 'readers': readers, 'total': len(readers)}), 200
    except Exception as error:
        logging.error('Failed to list activated readers: %s', error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief What the database schema is at, and what an upgrade would apply.
#
# Safe to call at any time -- it only reads. Kept separate from the upgrade
# itself so the UI can always show the state, including the "this server has
# web migrations switched off" case.
@admin.route('/super/system/migrations', methods=['GET'])
def super_get_migration_status():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        return jsonify(get_migration_status()), 200
    except Exception as error:
        logging.error('Failed to read migration status: %s', error, exc_info=True)
        return jsonify({
            'message': 'Could not read the migration status: %s' % error
        }), 500


## @brief Apply every pending migration. Upgrade only -- there is deliberately
# no downgrade endpoint, because that is the direction that destroys data.
@admin.route('/super/system/migrations/upgrade', methods=['POST'])
def super_run_migration_upgrade():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        before = get_migration_status()
        result = run_upgrade()

        log_admin_action(
            'migrate', 'database', None,
            'from=%s to=%s applied=%s' % (
                result['revision_before'], result['revision_after'],
                ','.join(r['revision'] for r in result['applied']) or 'none'
            )
        )

        return jsonify({
            'message': 'Applied %s migration(s)' % len(result['applied'])
            if result['changed'] else 'Database was already up to date',
            'result': result,
            'status': get_migration_status(),
            'previous_status': before,
        }), 200
    except MigrationsDisabled as error:
        return jsonify({'message': str(error), 'code': 'MIGRATIONS_DISABLED'}), 403
    except Exception as error:
        logging.error('Migration upgrade failed: %s', error, exc_info=True)
        # The failure text matters here -- a half-applied migration needs the
        # operator to see which revision broke, not a generic 500.
        return jsonify({
            'message': 'Migration failed: %s' % error,
            'status': get_migration_status_safe(),
        }), 500


## @brief Migration status that never raises, for use inside error handlers.
def get_migration_status_safe():
    try:
        return get_migration_status()
    except Exception:
        return None


## @brief Platform-wide licensing report: what has been sold, what is being
# used, what has been paid, and what is coming up for renewal.
#
# Returned as one payload rather than four endpoints because the page renders
# it as a single dashboard -- four round trips would only make it slower to
# paint and harder to keep internally consistent.
@admin.route('/super/billing/overview', methods=['GET'])
def super_get_billing_overview():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        months = min(max(int(request.args.get('months', 12)), 1), 36)
        renewal_days = min(max(int(request.args.get('renewal_days', 90)), 1), 365)
    except (TypeError, ValueError):
        return jsonify({'message': 'months and renewal_days must be numbers'}), 400

    try:
        live_contracts = (
            SchoolSubscription.query
            .filter(SchoolSubscription.status.in_(CONSUMING_STATUSES))
            .all()
        )

        seats_licensed = sum(c.seat_limit or 0 for c in live_contracts)
        contracted_cents = sum(c.total_cents or 0 for c in live_contracts)
        seats_in_use = (
            db.session.query(func.count(SchoolSeatActivation.id))
            .filter(SchoolSeatActivation.released_at.is_(None))
            .scalar()
        ) or 0

        # Invoiced money, split by whether it has actually arrived. Voided and
        # uncollectible invoices are excluded from both -- they are never going
        # to be paid and would overstate the pipeline.
        invoice_rows = (
            db.session.query(SchoolInvoice.status, func.sum(SchoolInvoice.total_cents))
            .group_by(SchoolInvoice.status)
            .all()
        )
        invoiced_by_status = {status: int(total or 0) for status, total in invoice_rows}
        paid_cents = invoiced_by_status.get('paid', 0)
        outstanding_cents = invoiced_by_status.get('open', 0) + invoiced_by_status.get('draft', 0)

        return jsonify({
            'totals': {
                'schools_licensed': len({c.shcool_id for c in live_contracts}),
                'contracts_live': len(live_contracts),
                'seats_licensed': seats_licensed,
                'seats_in_use': seats_in_use,
                'seats_available': max(seats_licensed - seats_in_use, 0),
                'utilisation_percent': round((seats_in_use / seats_licensed) * 100, 1)
                if seats_licensed else None,
                'contracted_cents': contracted_cents,
                'paid_cents': paid_cents,
                'outstanding_cents': outstanding_cents,
                'currency': ConfigClass.BILLING_CURRENCY,
            },
            'by_tier': build_tier_breakdown(live_contracts),
            'activations_over_time': build_activation_series(months),
            'renewals': build_renewal_pipeline(renewal_days),
        }), 200
    except Exception as error:
        logging.error('Failed to build billing overview: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Live contracts grouped by the plan they were sold on.
#
# Bespoke contracts (plan_id NULL) are reported under their own bucket rather
# than dropped -- they are real revenue, and hiding them would make the tier
# totals disagree with the headline figure.
def build_tier_breakdown(live_contracts):
    plans = ContractPlan.query.order_by(ContractPlan.sort_order.asc()).all()
    buckets = {
        plan.id: {
            'plan_id': plan.id,
            'plan_code': plan.code,
            'plan_name': plan.name,
            'contracts': 0,
            'seats_licensed': 0,
            'seats_in_use': 0,
            'total_cents': 0,
        }
        for plan in plans
    }
    bespoke = {
        'plan_id': None,
        'plan_code': 'bespoke',
        'plan_name': 'Bespoke',
        'contracts': 0,
        'seats_licensed': 0,
        'seats_in_use': 0,
        'total_cents': 0,
    }

    for contract in live_contracts:
        bucket = buckets.get(contract.plan_id, bespoke)
        bucket['contracts'] += 1
        bucket['seats_licensed'] += contract.seat_limit or 0
        bucket['seats_in_use'] += seats_used(contract.shcool_id)
        bucket['total_cents'] += contract.total_cents or 0

    ordered = [buckets[plan.id] for plan in plans]
    if bespoke['contracts']:
        ordered.append(bespoke)
    return ordered


## @brief Monthly count of seats activated, for the trend chart.
#
# Uses extract() rather than a dialect-specific date function so the same query
# runs on MySQL in production and SQLite under test. Months with no activations
# are filled with zero -- a gap in a time series reads as missing data, not as
# "nothing happened".
def build_activation_series(months):
    today = date.today()
    first_of_this_month = today.replace(day=1)
    start = add_months(first_of_this_month, -(months - 1))

    rows = (
        db.session.query(
            extract('year', SchoolSeatActivation.activated_at).label('y'),
            extract('month', SchoolSeatActivation.activated_at).label('m'),
            func.count(SchoolSeatActivation.id)
        )
        .filter(SchoolSeatActivation.activated_at >= datetime.combine(start, datetime.min.time()))
        .group_by('y', 'm')
        .all()
    )
    counts = {(int(year), int(month)): int(total) for year, month, total in rows}

    labels, data = [], []
    cursor = start
    for _ in range(months):
        labels.append(cursor.strftime('%b %Y'))
        data.append(counts.get((cursor.year, cursor.month), 0))
        cursor = add_months(cursor, 1)
    return {'labels': labels, 'data': data}


## @brief Contracts coming up for renewal, soonest first.
def build_renewal_pipeline(renewal_days):
    today = date.today()
    horizon = today + timedelta(days=renewal_days)
    upcoming = (
        SchoolSubscription.query
        .filter(SchoolSubscription.status.in_(CONSUMING_STATUSES))
        .filter(SchoolSubscription.term_end <= horizon)
        .order_by(SchoolSubscription.term_end.asc())
        .all()
    )

    pipeline = []
    for contract in upcoming:
        school = Shcool.query.get(contract.shcool_id)
        used = seats_used(contract.shcool_id)
        pipeline.append({
            'subscription_id': contract.id,
            'school_id': contract.shcool_id,
            'school_name': school.name if school else None,
            'plan_name': contract.plan.name if contract.plan else 'Bespoke',
            'seat_limit': contract.seat_limit,
            'seats_used': used,
            'term_end': contract.term_end.isoformat() if contract.term_end else None,
            'days_left': (contract.term_end - today).days if contract.term_end else None,
            'status': contract.status,
            'auto_renew': contract.auto_renew,
            'total_cents': contract.total_cents,
            'currency': contract.currency,
        })
    return pipeline


## @brief Raise and email the licence invoice for a contract, via Stripe.
@admin.route('/super/subscriptions/<int:subscription_id>/invoice', methods=['POST'])
def super_issue_subscription_invoice(subscription_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        subscription = SchoolSubscription.query.get(subscription_id)
        if not subscription:
            return jsonify({'message': 'Contract not found'}), 404
        school = Shcool.query.get(subscription.shcool_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        # Guard 1 -- never bill the same term twice. Without this, clicking
        # Invoice again raises a second Stripe invoice for the same contract
        # and the school can pay both.
        blocking_invoice = (
            SchoolInvoice.query
            .filter(SchoolInvoice.subscription_id == subscription.id)
            .filter(SchoolInvoice.status.in_((INVOICE_DRAFT, INVOICE_OPEN, INVOICE_PAID)))
            .order_by(SchoolInvoice.id.desc())
            .first()
        )
        if blocking_invoice is not None:
            already_paid = blocking_invoice.status == INVOICE_PAID
            return jsonify({
                'message': (
                    'This contract has already been paid (invoice %s). Create a new '
                    'contract for the next term rather than invoicing this one again.'
                    if already_paid else
                    'An invoice for this contract is already awaiting payment (%s). '
                    'Void it first if you need to re-issue it.'
                ) % (blocking_invoice.number or '#%s' % blocking_invoice.id),
                'code': 'INVOICE_ALREADY_EXISTS',
                'invoice': serialize_school_invoice(blocking_invoice)
            }), 409

        # Guard 2 -- invoicing moves a contract to "awaiting payment", which is
        # a seat-consuming state. Two of those for one school makes "which cap
        # applies?" ambiguous, so it is refused here exactly as it is when a
        # contract is created or activated directly.
        conflict = overlapping_consuming_subscription(
            subscription.shcool_id, subscription.term_start,
            subscription.term_end, exclude_id=subscription.id
        )
        if conflict is not None and not subscription.is_consuming():
            return jsonify({
                'message': overlap_conflict_message(conflict),
                'code': 'CONTRACT_TERM_OVERLAP'
            }), 409

        data = request.get_json(silent=True) or {}
        invoice = create_and_send_invoice(
            subscription, school,
            created_by=current_user.id,
            description=data.get('description')
        )
        db.session.commit()

        log_admin_action('invoice', 'school_subscription', subscription.id,
                         'school=%s stripe_invoice=%s' % (school.id, invoice.stripe_invoice_id))

        return jsonify({
            'message': 'Invoice raised and sent to the school',
            'invoice': serialize_school_invoice(invoice),
            'subscription': serialize_subscription(subscription)
        }), 201
    except StripeNotConfigured as error:
        db.session.rollback()
        return jsonify({'message': str(error), 'code': 'STRIPE_NOT_CONFIGURED'}), 503
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to raise invoice for contract %s: %s', subscription_id, error,
                      exc_info=True)
        return jsonify({'message': 'Stripe rejected the invoice: %s' % error}), 502


## @brief Invoices for one school.
@admin.route('/super/schools/<int:school_id>/invoices', methods=['GET'])
def super_get_school_invoices(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        invoices = (
            SchoolInvoice.query
            .filter_by(shcool_id=school_id)
            .order_by(SchoolInvoice.issued_at.desc(), SchoolInvoice.id.desc())
            .all()
        )
        return jsonify({
            'school_id': school_id,
            'invoices': [serialize_school_invoice(invoice) for invoice in invoices],
            'stripe_configured': stripe_is_configured(),
            'platform_vat_registered': bool(ConfigClass.PLATFORM_VAT_REGISTERED)
        }), 200
    except Exception as error:
        logging.error('Failed to list invoices for school %s: %s', school_id, error)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Void an invoice raised in error.
@admin.route('/super/invoices/<int:invoice_id>/void', methods=['POST'])
def super_void_invoice(invoice_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        invoice = SchoolInvoice.query.get(invoice_id)
        if not invoice:
            return jsonify({'message': 'Invoice not found'}), 404
        if invoice.status == 'paid':
            return jsonify({
                'message': 'A paid invoice cannot be voided. Refund it in Stripe instead.'
            }), 400

        voided = void_invoice(invoice)
        db.session.commit()

        log_admin_action('void', 'school_invoice', invoice_id,
                         'school=%s' % invoice.shcool_id)

        return jsonify({
            'message': 'Invoice voided',
            'invoice': serialize_school_invoice(voided or invoice)
        }), 200
    except StripeNotConfigured as error:
        db.session.rollback()
        return jsonify({'message': str(error), 'code': 'STRIPE_NOT_CONFIGURED'}), 503
    except Exception as error:
        db.session.rollback()
        logging.error('Failed to void invoice %s: %s', invoice_id, error)
        return jsonify({'message': 'Stripe rejected the request: %s' % error}), 502


## @brief Resolve and validate a contract term from request data.
# @return (term_start, term_end, error_message)
def parse_subscription_term(data, plan=None, existing=None):
    def parse_date(value, fallback):
        if not value:
            return fallback, None
        try:
            return datetime.strptime(str(value)[:10], '%Y-%m-%d').date(), None
        except (TypeError, ValueError):
            return None, 'Dates must be in YYYY-MM-DD format'

    default_start = existing.term_start if existing else date.today()
    term_start, error = parse_date(data.get('term_start'), default_start)
    if error:
        return None, None, error

    term_months = (plan.term_months if plan else 12) or 12
    if existing and not data.get('term_end'):
        default_end = existing.term_end
    else:
        default_end = add_months(term_start, term_months)
    term_end, error = parse_date(data.get('term_end'), default_end)
    if error:
        return None, None, error

    if term_end <= term_start:
        return None, None, 'The term must end after it starts'
    return term_start, term_end, None


## @brief Add whole months to a date, clamping the day to the target month's
# length so 31 Jan + 1 month lands on 28/29 Feb rather than raising.
def add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


## @brief A live contract whose term overlaps the dates given.
#
# The constraint is deliberately *overlap*, not "one live contract at a time".
# A school renewing early legitimately has two live contracts at once -- this
# year's running to August and next year's starting in September -- and it
# should be able to sign and even invoice the second one in advance.
#
# What is genuinely unsafe is two live contracts covering the *same* dates,
# because then "which seat cap applies today?" has two answers and
# get_active_subscription would silently pick one.
#
# Standard interval overlap: A starts on or before B ends, and B starts on or
# before A ends. Touching endpoints count as overlapping, so a term ending on
# the 27th and another starting on the 27th is refused -- that day would
# otherwise belong to both.
def overlapping_consuming_subscription(school_id, term_start, term_end, exclude_id=None):
    if not school_id or term_start is None or term_end is None:
        return None
    query = SchoolSubscription.query.filter(
        SchoolSubscription.shcool_id == school_id,
        SchoolSubscription.status.in_(CONSUMING_STATUSES),
        SchoolSubscription.term_start <= term_end,
        SchoolSubscription.term_end >= term_start,
    )
    if exclude_id:
        query = query.filter(SchoolSubscription.id != exclude_id)
    return query.first()


## @brief Human-readable refusal for an overlapping contract.
def overlap_conflict_message(conflict):
    return (
        'This school already has a live contract (#%s) covering %s to %s. '
        'Contract terms cannot overlap — adjust the dates so this one starts '
        'after that term ends, or cancel it first.' % (
            conflict.id,
            conflict.term_start.isoformat() if conflict.term_start else '?',
            conflict.term_end.isoformat() if conflict.term_end else '?',
        )
    )


def serialize_subscription(subscription):
    if subscription is None:
        return None
    return {
        'id': subscription.id,
        'school_id': subscription.shcool_id,
        'plan_id': subscription.plan_id,
        'plan_name': subscription.plan.name if subscription.plan else None,
        'plan_code': subscription.plan.code if subscription.plan else None,
        'seat_limit': subscription.seat_limit,
        'seats_used': seats_used(subscription.shcool_id),
        'unit_price_cents': subscription.unit_price_cents,
        'total_cents': subscription.total_cents,
        'currency': subscription.currency,
        'term_start': subscription.term_start.isoformat() if subscription.term_start else None,
        'term_end': subscription.term_end.isoformat() if subscription.term_end else None,
        'grace_days': subscription.grace_days,
        'status': subscription.status,
        'auto_renew': subscription.auto_renew,
        'notes': subscription.notes,
        'created_at': subscription.created_at.isoformat() if subscription.created_at else None,
        # Lets the UI disable the Invoice button instead of letting the super
        # admin click it and be refused -- the server still enforces it.
        **summarize_subscription_invoices(subscription)
    }


## @brief Whether a contract has already been billed, and how that went.
def summarize_subscription_invoices(subscription):
    invoices = (
        SchoolInvoice.query
        .filter(SchoolInvoice.subscription_id == subscription.id)
        .order_by(SchoolInvoice.id.desc())
        .all()
    )
    paid = next((i for i in invoices if i.status == INVOICE_PAID), None)
    awaiting = next((i for i in invoices if i.status in (INVOICE_DRAFT, INVOICE_OPEN)), None)
    latest = invoices[0] if invoices else None
    return {
        'invoice_count': len(invoices),
        'has_paid_invoice': paid is not None,
        'has_open_invoice': awaiting is not None,
        'can_invoice': paid is None and awaiting is None,
        'latest_invoice_status': latest.status if latest else None,
        'latest_invoice_number': (latest.number or ('#%s' % latest.id)) if latest else None,
    }


def serialize_billing_profile(profile, school=None):
    if profile is None:
        return {
            'school_id': school.id if school else None,
            'legal_name': school.name if school else None,
            'billing_email': None, 'billing_phone': None,
            'address_line1': None, 'address_line2': None, 'city': None, 'region': None,
            'postal_code': None, 'country': None, 'vat_number': None,
            'purchase_order_ref': None, 'stripe_customer_id': None, 'exists': False
        }
    return {
        'school_id': profile.shcool_id,
        'legal_name': profile.legal_name,
        'billing_email': profile.billing_email,
        'billing_phone': profile.billing_phone,
        'address_line1': profile.address_line1,
        'address_line2': profile.address_line2,
        'city': profile.city,
        'region': profile.region,
        'postal_code': profile.postal_code,
        'country': profile.country,
        'vat_number': profile.vat_number,
        'purchase_order_ref': profile.purchase_order_ref,
        'stripe_customer_id': profile.stripe_customer_id,
        'exists': True
    }


def serialize_school_invoice(invoice):
    return {
        'id': invoice.id,
        'number': invoice.number,
        'status': invoice.status,
        'subtotal_cents': invoice.subtotal_cents,
        'tax_cents': invoice.tax_cents,
        'total_cents': invoice.total_cents,
        'currency': invoice.currency,
        'seats': invoice.seats,
        'period_start': invoice.period_start.isoformat() if invoice.period_start else None,
        'period_end': invoice.period_end.isoformat() if invoice.period_end else None,
        'hosted_invoice_url': invoice.hosted_invoice_url,
        'invoice_pdf': invoice.invoice_pdf,
        'issued_at': invoice.issued_at.isoformat() if invoice.issued_at else None,
        'due_at': invoice.due_at.isoformat() if invoice.due_at else None,
        'paid_at': invoice.paid_at.isoformat() if invoice.paid_at else None
    }


def serialize_contract_plan(plan):
    return {
        'id': plan.id,
        'code': plan.code,
        'name': plan.name,
        'min_seats': plan.min_seats,
        'max_seats': plan.max_seats,
        'unit_price_cents': plan.unit_price_cents,
        'total_cents': plan.total_cents,
        'currency': plan.currency,
        'term_months': plan.term_months,
    }


@admin.route('/super/schools', methods=['GET'])
def super_get_schools():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        search = request.args.get('search')
        schools_query = Shcool.query
        if search:
            schools_query = schools_query.filter(Shcool.name.ilike(f'%{search}%'))

        schools_query = schools_query.order_by(Shcool.id.desc())
        return jsonify(paginate_super_admin_query(schools_query, serialize_super_school, 'schools')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

def serialize_admin_audit_log_entry(entry):
    return {
        'id': entry.id,
        'actor_id': entry.actor_id,
        'actor_username': entry.actor_username,
        'actor_role': entry.actor_role,
        'action': entry.action,
        'target_type': entry.target_type,
        'target_id': entry.target_id,
        'details': entry.details,
        'created_at': entry.created_at.isoformat() if entry.created_at else None
    }

## @brief Read-only feed of admin/assistant/super-admin actions (create, update,
# delete, approve, suspend, activate) for accountability — see log_admin_action().
@admin.route('/super/audit-log', methods=['GET'])
def super_get_audit_log():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        entries_query = AdminAuditLog.query
        action = request.args.get('action')
        if action:
            entries_query = entries_query.filter(AdminAuditLog.action == action)
        target_type = request.args.get('target_type')
        if target_type:
            entries_query = entries_query.filter(AdminAuditLog.target_type == target_type)

        entries_query = entries_query.order_by(AdminAuditLog.created_at.desc())
        return jsonify(paginate_super_admin_query(entries_query, serialize_admin_audit_log_entry, 'entries')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/schools/<int:school_id>/suspend', methods=['POST'])
def super_suspend_school(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        school.is_active = False
        school.suspended_at = datetime.now()
        school.suspended_by = current_user.id
        school.suspended_reason = data.get('reason')
        db.session.commit()

        log_admin_action('suspend', 'school', school_id, f'reason={school.suspended_reason}')

        return jsonify({
            'message': 'School suspended successfully',
            'school': serialize_super_school(school)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/super/schools/<int:school_id>/activate', methods=['POST'])
def super_activate_school(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        school.is_active = True
        school.suspended_at = None
        school.suspended_by = None
        school.suspended_reason = None
        db.session.commit()

        log_admin_action('activate', 'school', school_id)

        return jsonify({
            'message': 'School reactivated successfully',
            'school': serialize_super_school(school)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/platform-books', methods=['GET'])
def get_available_platform_books():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        search = request.args.get('search')
        books_query = Book.query.filter(Book.is_platform_book.is_(True), Book.active.is_(True))
        if search:
            books_query = books_query.filter(
                (Book.title.ilike(f'%{search}%')) |
                (Book.author.ilike(f'%{search}%')) |
                (Book.category.ilike(f'%{search}%'))
            )
        books_query = books_query.order_by(Book.id.desc())
        return jsonify(
            paginate_super_admin_query(
                books_query,
                lambda book: serialize_platform_book(book, school_id=school_id),
                'books'
            )
        ), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/platform-books/<int:book_id>/instances', methods=['POST'])
def create_platform_book_instance(book_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        book = get_platform_book_or_404(book_id)
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        instance, created = create_or_reactivate_school_book_instance(school_id, book.id)
        db.session.commit()
        return jsonify({
            'message': 'Platform book added to this school' if created else 'Platform book is already added to this school',
            'instance': serialize_school_book_instance(instance),
            'book': serialize_platform_book(book, school_id=school_id)
        }), 201 if created else 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/platform-books/<int:book_id>/instances', methods=['DELETE'])
def remove_platform_book_instance_by_book(book_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        instance = get_school_platform_instance(school_id, book.id)
        if not instance:
            return jsonify({'message': 'Platform book is not added to this school'}), 404

        removed_pack_links = remove_platform_book_from_school(instance, school_id)
        db.session.commit()
        return jsonify({
            'message': 'Platform book removed from this school',
            'book_id': book.id,
            'instance_id': instance.id,
            'removed_pack_links': removed_pack_links
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/school-platform-books', methods=['GET'])
def get_school_platform_book_instances():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        search = request.args.get('search')
        instances_query = (
            SchoolBookInstance.query
            .join(Book, SchoolBookInstance.book_id == Book.id)
            .filter(
                SchoolBookInstance.shcool_id == school_id,
                SchoolBookInstance.active.is_(True),
                Book.is_platform_book.is_(True),
                Book.active.is_(True)
            )
        )
        if search:
            instances_query = instances_query.filter(
                (Book.title.ilike(f'%{search}%')) |
                (Book.author.ilike(f'%{search}%')) |
                (Book.category.ilike(f'%{search}%'))
            )
        instances_query = instances_query.order_by(SchoolBookInstance.id.desc())
        return jsonify(paginate_super_admin_query(instances_query, serialize_school_book_instance, 'instances')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/school-platform-books/books', methods=['GET'])
def get_school_platform_books_only():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        search = request.args.get('search')
        books_query = (
            db.session.query(Book)
            .join(SchoolBookInstance, SchoolBookInstance.book_id == Book.id)
            .filter(
                SchoolBookInstance.shcool_id == school_id,
                SchoolBookInstance.active.is_(True),
                Book.is_platform_book.is_(True),
                Book.active.is_(True)
            )
        )
        if search:
            books_query = books_query.filter(
                (Book.title.ilike(f'%{search}%')) |
                (Book.author.ilike(f'%{search}%')) |
                (Book.category.ilike(f'%{search}%'))
            )
        books_query = books_query.distinct().order_by(Book.id.desc())
        return jsonify(
            paginate_super_admin_query(
                books_query,
                lambda book: serialize_platform_book(book, school_id=school_id),
                'books'
            )
        ), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/school-platform-books/<int:instance_id>', methods=['DELETE'])
def remove_school_platform_book_instance(instance_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        instance = SchoolBookInstance.query.filter_by(id=instance_id, shcool_id=school_id, active=True).first()
        if not instance:
            return jsonify({'message': 'Platform book instance not found'}), 404

        removed_pack_links = remove_platform_book_from_school(instance, school_id)
        db.session.commit()
        return jsonify({
            'message': 'Platform book removed from this school',
            'book_id': instance.book_id,
            'instance_id': instance.id,
            'removed_pack_links': removed_pack_links
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/packs/<int:pack_id>/platform-books/<int:book_id>', methods=['POST'])
def add_platform_book_to_pack(pack_id, book_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        book = get_platform_book_or_404(book_id)
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        instance, _ = create_or_reactivate_school_book_instance(school_id, book.id)
        existing_link = Book_pack.query.filter_by(book_id=book.id, pack_id=pack.id).first()
        if existing_link:
            db.session.commit()
            return jsonify({
                'message': 'Platform book already exists in this pack',
                'instance': serialize_school_book_instance(instance),
                'book': serialize_platform_book(book, school_id=school_id)
            }), 200

        db.session.add(Book_pack(book_id=book.id, pack_id=pack.id))
        pack.book_number = (pack.book_number or 0) + 1
        db.session.add(pack)
        db.session.commit()
        return jsonify({
            'message': 'Platform book added to pack successfully',
            'instance': serialize_school_book_instance(instance),
            'book': serialize_platform_book(book, school_id=school_id)
        }), 201
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/packs/<int:pack_id>/platform-books/<int:book_id>', methods=['DELETE'])
def remove_platform_book_from_pack(pack_id, book_id):
    try:
        pack = get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        book = Book.query.filter_by(id=book_id, is_platform_book=True).first()
        if not book:
            return jsonify({'message': 'Platform book not found'}), 404

        link = Book_pack.query.filter_by(book_id=book.id, pack_id=pack.id).first()
        if not link:
            return jsonify({'message': 'Platform book is not in this pack'}), 404

        Follow_book.query.filter_by(book_id=book.id, pack_id=pack.id).delete(synchronize_session=False)
        if pack.book_number and pack.book_number > 0:
            pack.book_number -= 1
            db.session.add(pack)
        db.session.delete(link)
        db.session.commit()
        return jsonify({'message': 'Platform book removed from pack successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs', methods=['GET'])
def get_available_global_packs():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        search = request.args.get('search') or request.args.get('title')
        packs_query = Pack.query.filter(Pack.is_global_pack.is_(True), Pack.active.is_(True))
        if search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{search}%'))
        packs_query = packs_query.order_by(Pack.id.desc())
        return jsonify(
            paginate_super_admin_query(
                packs_query,
                lambda pack: serialize_global_pack(pack, school_id=school_id),
                'packs'
            )
        ), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs/<int:pack_id>/instances', methods=['POST'])
def create_global_pack_instance(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404

        instance, created = create_or_reactivate_school_pack_instance(school_id, pack.id)
        db.session.commit()
        return jsonify({
            'message': 'Global pack added to this school' if created else 'Global pack is already added to this school',
            'instance': serialize_school_pack_instance(instance),
            'pack': serialize_global_pack(pack, school_id=school_id)
        }), 201 if created else 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs/<int:pack_id>/instances', methods=['DELETE'])
def remove_global_pack_instance_by_pack(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = Pack.query.filter_by(id=pack_id, is_global_pack=True).first()
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        instance = get_school_global_pack_instance(school_id, pack.id)
        if not instance:
            return jsonify({'message': 'Global pack is not added to this school'}), 404

        remove_global_pack_from_school(instance, school_id)
        db.session.commit()
        return jsonify({
            'message': 'Global pack removed from this school',
            'pack_id': pack.id,
            'instance_id': instance.id
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs/<int:pack_id>/instance', methods=['PUT', 'PATCH'])
def update_school_global_pack_instance(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        instance = get_school_global_pack_instance(school_id, pack.id)
        if not instance:
            return jsonify({'message': 'Global pack is not added to this school'}), 404

        data = request.get_json() or {}
        if 'display_name' in data:
            display_name = str(data.get('display_name') or '').strip()
            instance.display_name = display_name or None
        db.session.add(instance)
        db.session.commit()
        return jsonify({
            'message': 'Global pack updated for this school',
            'instance': serialize_school_pack_instance(instance),
            'pack': serialize_global_pack(pack, school_id=school_id)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs/<int:pack_id>/publish', methods=['POST'])
def publish_school_global_pack(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        instance = get_school_global_pack_instance(school_id, pack.id)
        if not instance:
            return jsonify({'message': 'Global pack is not added to this school'}), 404

        data = request.get_json(silent=True) or {}
        force = bool(data.get('force'))
        is_default_school = Shcool.query.filter_by(id=school_id, name='IRead').first() is not None
        if is_default_school and not force:
            has_price = (pack.price or 0) > 0
            has_active_codes = Code.query.filter_by(pack_id=pack.id, status=StatusEnum.ACTIVE).first() is not None
            if has_price or has_active_codes:
                return jsonify({
                    'message': 'This pack is priced or has active redemption codes -- publishing it to IRead makes it free and unlimited for every registered reader, bypassing per-pack code access. Pass {"force": true} to publish anyway.'
                }), 409

        if 'display_name' in data:
            display_name = str(data.get('display_name') or '').strip()
            instance.display_name = display_name or None
        instance.public = True
        db.session.add(instance)
        db.session.commit()
        return jsonify({
            'message': 'Global pack published for this school',
            'instance': serialize_school_pack_instance(instance),
            'pack': serialize_global_pack(pack, school_id=school_id)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/global-packs/<int:pack_id>/unpublish', methods=['POST'])
def unpublish_school_global_pack(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_global_pack_or_404(pack_id)
        if not pack:
            return jsonify({'message': 'Global pack not found'}), 404
        instance = get_school_global_pack_instance(school_id, pack.id)
        if not instance:
            return jsonify({'message': 'Global pack is not added to this school'}), 404

        instance.public = False
        db.session.add(instance)
        db.session.commit()
        return jsonify({
            'message': 'Global pack unpublished for this school',
            'instance': serialize_school_pack_instance(instance),
            'pack': serialize_global_pack(pack, school_id=school_id)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/school-global-packs', methods=['GET'])
def get_school_global_packs():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        search = request.args.get('search') or request.args.get('title')
        packs_query = (
            db.session.query(Pack)
            .join(SchoolPackInstance, SchoolPackInstance.pack_id == Pack.id)
            .filter(
                SchoolPackInstance.shcool_id == school_id,
                SchoolPackInstance.active.is_(True),
                Pack.is_global_pack.is_(True),
                Pack.active.is_(True)
            )
        )
        if search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{search}%'))
        packs_query = packs_query.order_by(Pack.id.desc())
        return jsonify(
            paginate_super_admin_query(
                packs_query,
                lambda pack: serialize_global_pack(pack, school_id=school_id),
                'packs'
            )
        ), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/school-global-packs/<int:pack_id>', methods=['GET'])
def get_school_global_pack_details(pack_id):
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        pack = get_global_pack_or_404(pack_id)
        if not pack or not school_has_global_pack_access(school_id, pack.id):
            return jsonify({'message': 'Global pack not found in this school'}), 404
        pack_details = serialize_global_pack(pack, school_id=school_id, include_details=True)
        return jsonify({'pack': pack_details, **pack_details}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


# ---------------------------------------------------------------------------
# School-admin codes for GLOBAL packs their school has joined (mirrors the
# classic /code_in_pack + /generate_code_in_pack pair for school-owned packs,
# see PRD ask: schools should be able to generate/share codes for packs
# instantiated from a global pack, same as classic packs). Scoped by
# school_has_global_pack_access rather than get_school_pack, since global
# packs are shared rows (SchoolPackInstance is a join table, not a per-school
# copy) — get_school_pack deliberately excludes is_global_pack packs.
# ---------------------------------------------------------------------------

@admin.route('/global-packs/<int:pack_id>/codes', methods=['GET'])
def get_school_global_pack_codes(pack_id):
    school_id = get_current_school_id()
    if not school_id:
        return jsonify({'message': 'Current admin has no school assigned'}), 403
    pack = get_global_pack_or_404(pack_id)
    if not pack or not school_has_global_pack_access(school_id, pack.id):
        return jsonify({'message': 'Global pack not found in this school'}), 404
    codes = Code.query.filter_by(pack_id=pack_id, status=StatusEnum.ACTIVE).all()
    return jsonify({
        'id': pack.id,
        'title': pack.title,
        'codes': [{'code': code.code, 'status': code.status.value, 'id': code.id, 'pack_id': code.pack_id} for code in codes]
    }), 200


@admin.route('/global-packs/<int:pack_id>/codes', methods=['POST'])
def generate_school_global_pack_codes(pack_id):
    school_id = get_current_school_id()
    if not school_id:
        return jsonify({'message': 'Current admin has no school assigned'}), 403
    pack = get_global_pack_or_404(pack_id)
    if not pack or not school_has_global_pack_access(school_id, pack.id):
        return jsonify({'message': 'Global pack not found in this school'}), 404

    data = request.get_json() or {}
    num_codes_to_generate = data.get('num_codes', 10)
    generated_codes = []
    for _ in range(num_codes_to_generate):
        code = generate_unique_code(pack_id)
        db.session.add(Code(pack_id=pack_id, code=code))
        generated_codes.append(code)
    db.session.commit()
    return jsonify({
        'message': f'{num_codes_to_generate} codes generated successfully',
        'generated_codes': generated_codes
    }), 200


## @brief Route to invite a reader to become an administrator.
#
# This route is used by administrators to invite a reader to become an administrator.
# The route accepts a POST request with JSON data containing the reader's email and username.
# The function generates a new confirmation token for the reader, sends an email invitation,
# and returns a JSON object containing a message indicating the success of the invitation.
#
# @param email: Email of the reader for sending the confirmation link.
# @param username: Username of the reader being invited.
# @return: A JSON object containing a message notifying if the invitation was successful or not.
@admin.route('/invite_admin',methods=['POST'])
@login_required
@admin_required
def invite_admin():
    try:
        email=request.json['email']
        username=request.json['username']
        confirmation_token=generate_confirmed_token(email)
        confirm_link = f"http://localhost:5000/admin/confirm/{confirmation_token}"
        #confirmation_email = render_template('invite_admin.html',username=username,confirm_link=confirm_link)
        msg = Message('Invitation to get admin\'s roles', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
        msg.body=confirm_link
        #msg.html = confirmation_email
        mail.send(msg)

        return jsonify({'message':'Admin invited sucessfully'}),200
    except Exception:
        return jsonify({'message':'Internal server error'}),500


## @brief Route for confirming administrator privileges from the received email.
#
# This route is used for confirming administrator privileges based on the confirmation token
# received in the email sent to the user. If the link is valid and not expired, the 'is_admin'
# attribute of the user is set to 1 (True) to grant administrator privileges.
#
# @param token: Token extracted from the confirmation email sent to the user.
# @return: A JSON object indicating whether the confirmation was successful or not.
@admin.route('/confirm/<token>')
def confirm(token):
    try:
        admin_confirm_token(token)
    except Exception:
        return jsonify({'message':'Invalid or exprired link'}),404

    return jsonify({'message':'Congratulation you are now admin'}),200


## @brief Route for handling forgotten passwords for school/super admins.
#
# Mirrors apps/reader/routes.py's forget_password, but links to the admin
# dashboard front-end instead of the reader-facing site.
@admin.route('/forget_password', methods=['POST'])
def forget_password():
    try:
        email = request.json['email']
        if not user_email_exist(email):
            return jsonify({'message': 'There is no account with this email'}), 404
        confirmation_token = generate_confirmed_token(email)
        confirm_link = f"{ConfigClass.ADMIN_FRONT_URL}/authentication/reset-password/{confirmation_token}"
        msg = Message('Proof your identity', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
        msg.body = confirm_link
        mail.send(msg)
        return jsonify({'message': 'You have received a confirmation email to proof your identity'}), 200
    except Exception as error:
        return jsonify({'message': 'Internal serveur error'}), 500


## @brief Route for resetting forgotten passwords for school/super admins.
@admin.route('/password_reset/<token>', methods=['POST'])
def reset_password(token):
    try:
        email = reader_confirm_token(token)
        if not email:
            return jsonify({'message': 'Invalid or expired link'}), 404
        new_password = request.json['new_password']
        password_hashed = bcrypt.generate_password_hash(new_password)
        user = User.query.filter_by(email=email).first()
        user.password_hashed = password_hashed
        db.session.commit()
        return jsonify({'message': f'{user.username}, you have successfully changed your password. You can now login'}), 200
    except Exception as error:
        return jsonify({'message': 'Internal serveur error'}), 500


## @brief Route to display information about all users.
#
# This route is used by administrators to retrieve information about all users in the system.
# The response is a JSON object containing various user details such as email, username, confirmation status, and admin status.
#
# @return: A JSON object containing information about all users.
@admin.route('/show_all_readers')
@login_required
@admin_or_assistant_required
def show_all_readers():
    try:


        # Retrieve all reader IDs associated with current user's school ID
        reader_ids = get_current_school_user_ids()
        if not reader_ids:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        # Retrieve reader data for the extracted IDs
        reader_data = []
        for reader_id in reader_ids:
            
            reader = User.query.get(reader_id)
            if reader.type=="reader":  
                reader_data.append({
                    'email': reader.email,
                    'username': reader.username,
                    'confirmed': reader.confirmed,
                    'id': reader.id,
                    'img': reader.img,
                    'approved': reader.approved,
                    'quiz_id': reader.quiz_id
                })
        return jsonify({
            'readers': reader_data
        }), 200


    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/followers/<int:pack_id>', methods=['GET'])
def get_users_following_pack(pack_id):
    """
    Get all users who follow a specific pack by pack_id.
    """
    try:
        if not get_school_pack(pack_id):
            return jsonify({'message': 'Pack not found'}), 404
        # Query to get the User details for the given pack_id
        followers = (
            db.session.query(User)
            .join(Follow_pack, Follow_pack.user_id == User.id)
            .filter(Follow_pack.pack_id == pack_id)
            .all()
        )

        # Create a response with user details
        follower_details = [
            {
                'email': follower.email,
                'username': follower.username,
                'confirmed': follower.confirmed,
                'id': follower.id,
                'img': follower.img,
                'approved': follower.approved,
                'quiz_id': follower.quiz_id
            }
            for follower in followers
        ]

        return jsonify({'readers': follower_details}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# get all teachers
@admin.route('/show_all_teachers')
@login_required
@admin_or_assistant_required
def show_all_teachers():
    try:
        # Retrieve the school associated with the current user
        user_ids = get_current_school_user_ids()
        if not user_ids:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        # Retrieve all teachers
        # Collect user data associated with each teacher's ID
        user_data = []
        for user_id in user_ids:     
            user = User.query.filter_by(id=user_id, type="teacher").first()
            if user:
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img': user.img,
                    'approved': user.approved,
                    'quiz_id': user.quiz_id
                })

        return jsonify({
            'teachers': user_data
        }), 200
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/show_all_assistants')
@login_required
@admin_required
def show_all_assistants():
    try:
        user_ids = get_current_school_user_ids()
        if not user_ids:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        user_data = []
        for user_id in user_ids: 
            user = User.query.filter_by(id=user_id,type="assistant").first()
            if user:

                    
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img':user.img,
                    'approved':user.approved,
                    'quiz_id':user.quiz_id
                    })

        return jsonify({
            'assistans': user_data
        }), 200
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error','error':e}), 500

@admin.route('/get_user/<int:user_id>', methods=['GET'])

@login_required
@admin_or_assistant_required
def get_user(user_id):
    try:
        user = get_school_user(user_id)
        if user:
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'confirmed': user.confirmed,
                'created_at': user.created_at,
                'type': user.type,
                'img':user.img
            }

            if user.type == 'teacher':
                teacher = Teacher.query.filter_by(id=user.id).first()
                if teacher:
                    user_data['description'] = teacher.description
                    user_data['study_level'] = teacher.study_level

            return jsonify(user_data), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/update_user', methods=['PUT'])
@login_required
@admin_or_assistant_required
def update_user():
    try:
        data = request.json
        user_id = data.get('id')

        user = get_school_user(user_id)
        if user:
            if 'username' in data:
                user.username = data['username']

            if 'img' in data:
                user.img = data['img']
            
            if 'email' in data:
                new_email = data['email']
                accounts= User.query.filter(User.email == new_email).all()
                
                # Check if the new email is already in use
                if len(accounts)>=3:
                    return jsonify({'message': 'You reached the limit of accounts (3)'}), 400
                user.email = new_email
            if 'quiz_id' in data :
                user.quiz_id =data['quiz_id']    
            if 'password' in data:
                if data['password'] != "":
                    user.password_hashed = bcrypt.generate_password_hash(data['password'])
                else:
                    return jsonify({'message': 'Password cannot be empty'}), 400 

            # Assuming you're using some sort of database session management, commit the changes
            db.session.commit()
            log_admin_action('update', 'user', user.id, f'fields={list(data.keys())}')
            response_data = {
                'message': 'Reader updated successfully',
                'teacher': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'img': user.img,
                    'approved': user.approved,
                }
            }
            return jsonify(response_data), 200  # OK
        else:
            return jsonify({'message': 'Invalid id'}), 404
    except Exception as e:
        return jsonify({'message': 'Internal server error'}), 500





@admin.route('/create_user',methods=['POST'])
@login_required
@admin_or_assistant_required
def create_user():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        img =data['img']


        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict

        # Resolve the current admin's school before creating anything, so a missing
        # school assignment never leaves behind a reader with no school link.
        shcool = User_shcool.query.filter_by(user_id=current_user.id).first()
        if not shcool:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        # Hash the password
        password_hash = bcrypt.generate_password_hash(password)
         #Create a new user in quiz api
        quiz_user ={
            'app':f'{ConfigClass.QUIZ_API_KEY}'
        }
        invoicing_client ={
            'appId':f'{ConfigClass.INVOICING_API_KEY}'
        }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/client/create', json=invoicing_client)
        response = requests.post(f'{ConfigClass.QUIZ_API}user', json=quiz_user)

        if response.status_code != 201 or invoicing_response.status_code != 201:
            return jsonify({'message': 'Error creation Quiz account'}), 400

        quiz_id = response.json()['_id']
        client_id = invoicing_response.json()['_id']

        # Create a new user
        new_user = Reader(
            img=img,
            username=username,
            email=email,
            password_hashed=password_hash,
            created_at=datetime.now(),
            confirmed=True,
            quiz_id=quiz_id,
            client_id_invoicing_api=client_id
            )
        db.session.add(new_user)
        db.session.flush()

        # Same transaction as the reader itself, so the two can never diverge.
        db.session.add(User_shcool(user_id=new_user.id, shcool_id=shcool.shcool_id))
        db.session.commit()

        log_admin_action('create', 'user', new_user.id, f'username={username}, role=reader')

        # Return a success response
        response_data = {
            'message': 'Your account has been successfully created.',
            'user': {
                'username': username,
                'email': email,
                'confirmed': new_user.confirmed,
                'id': new_user.id,
                'img':new_user.img,
                'quiz_id':new_user.quiz_id

            }
        }
        return jsonify(response_data), 201
    except Exception as e:
        db.session.rollback()
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/create_assistant', methods=['POST'])
@login_required
@admin_required
def create_assistant():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        img = data['img']

       
        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:

            invoicing_user = {'appId': f'{ConfigClass.INVOICING_API_KEY}'}
            invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/user/create', json=invoicing_user)  
            if invoicing_response.status_code == 201:
                
                user_id = invoicing_response.json()['_id']
                # Hash the password
                password_hash = bcrypt.generate_password_hash(password)

                # Create a new user
                new_user = Assistant(
                    img=img,
                    username=username,
                    email=email,
                    password_hashed=password_hash,
                    created_at=datetime.now(),
                    confirmed=True,
                    approved=True,
                    user_id_invoicing_api=user_id
                )
                # Add the user to the database
                db.session.add(new_user)
                db.session.commit()
                shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
                if not shcool:
                    return jsonify({'message': 'Current admin has no school assigned'}), 403
                new_user_shcool = User_shcool(
                    user_id = new_user.id,
                    shcool_id = shcool.shcool_id
                    )
                db.session.add(new_user_shcool)
                db.session.commit()

                log_admin_action('create', 'user', new_user.id, f'username={username}, role=assistant')

                # Return a success response
                response_data = {
                    'message': 'Your account has been successfully created.',
                    'user': {
                        'username': username,
                        'email': email,
                        'confirmed': new_user.confirmed,
                        'id': new_user.id,
                        'img': new_user.img
                    }
                }
                return jsonify(response_data), 201
            else:
                password_hash = bcrypt.generate_password_hash(password)

                # Create a new user
                new_user = Assistant(
                    img=img,
                    username=username,
                    email=email,
                    password_hashed=password_hash,
                    created_at=datetime.now(),
                    confirmed=True,
                    approved=True
                    
                )
                # Add the user to the database
                db.session.add(new_user)
                db.session.commit()
                shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
                if not shcool:
                    return jsonify({'message': 'Current admin has no school assigned'}), 403
                new_user_shcool = User_shcool(
                    user_id = new_user.id,
                    shcool_id = shcool.shcool_id
                    )
                db.session.add(new_user_shcool)
                db.session.commit()

                log_admin_action('create', 'user', new_user.id, f'username={username}, role=assistant')

                # Return a success response
                response_data = {
                    'message': 'Your account has been successfully created.',
                    'user': {
                        'username': username,
                        'email': email,
                        'confirmed': new_user.confirmed,
                        'id': new_user.id,
                        'img': new_user.img
                    }
                }
                return jsonify(response_data), 201
                 
                 
    except Exception as e:
        
        # Handle exceptions and return an error response
        return jsonify({'message': e}), 500





@admin.route('/create_teacher',methods=['POST'])
@login_required
@admin_or_assistant_required
def create_teacher():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        description = data['description']
        study_level = data['study_level']
        img =data['img']

        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Hash the password
            password_hash = bcrypt.generate_password_hash(password)

            # Create a new user
            new_user = Teacher(
                img=img,
                username=username,
                email=email,
                password_hashed=password_hash,
                created_at=datetime.now(),
                description =description,
                study_level= study_level,
                confirmed=True,
               
            )

            # Add the user to the database
            db.session.add(new_user)
            db.session.commit()
            shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
            if not shcool:
                return jsonify({'message': 'Current admin has no school assigned'}), 403
            new_user_shcool = User_shcool(
                user_id = new_user.id,
                shcool_id = shcool.shcool_id
                )
            db.session.add(new_user_shcool)
            db.session.commit()
            log_admin_action('create', 'user', new_user.id, f'username={username}, role=teacher')
            # Return a success response
            response_data = {
                'message': 'Your account has been successfully created.',
                'user': {
                    'username': username,
                    'email': email,
                    'confirmed': new_user.confirmed,
                    'id': new_user.id,
                    'img':new_user.img,
                    'description' :new_user.description,
                    'study_level' : new_user.study_level

                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        # Handle exceptions and return an error response
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/update_teacher', methods=['PUT'])
@login_required
@admin_or_assistant_required

def update_teacher():
    data = request.json
    teacher_id = data.get('id')
    try:
        # Get the teacher by their ID
        if not user_belongs_to_current_school(teacher_id):
            return jsonify({'message': 'Teacher not found'}), 404
        teacher = Teacher.query.get(teacher_id)

        if not teacher:
            return jsonify({'message': 'Teacher not found'}), 404  # Not Found

        # Get data from the request

        # You can update any fields you want here
        if 'username' in data:
            teacher.username = data['username']
        if 'email' in data:
            new_email = data['email']
            # Check if the new email is already in use
            if Teacher.query.filter(Teacher.email == new_email, Teacher.id != teacher_id).first():
                return jsonify({'message': 'Email is already in use'}), 400
            teacher.email = new_email
        if 'password' in data:
            # Hash the new password
            teacher.password_hashed = bcrypt.generate_password_hash(data['password'])
        if 'description' in data:
            teacher.description = data['description']
        if 'study_level' in data:
            teacher.study_level = data['study_level']
        if 'img' in data:
            teacher.img = data['img']    

        # Commit the changes to the database
        db.session.commit()

        log_admin_action('update', 'user', teacher.id, f'fields={list(data.keys())}')

        # Return a success response
        response_data = {
            'message': 'Teacher updated successfully',
            'teacher': {
                'id': teacher.id,
                'username': teacher.username,
                'email': teacher.email,
                'img': teacher.img,
                'description': teacher.description,
                'study_level': teacher.study_level,
                'approved': teacher.approved
            }
        }
        return jsonify(response_data), 200  # OK

    except Exception as e:
        # Handle exceptions and return an error response
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/approved_user',methods=['POST'])
@login_required
@admin_or_assistant_required
def approved_user():
    try:
        id=request.json['id']
        user=get_school_user(id)
        if user:

            user.approved=True
            user.confirmed =True
            db.session.commit()
            log_admin_action('approve', 'user', user.id, f'username={user.username}, type={user.type}')
            return jsonify({'message':'Account approved sucessfully'}),200

        else :
            return jsonify({'message':'Invalid id'}),404
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

## @brief Route to delete a user's account.
#
# This route is used by administrators to delete a user's account based on the email provided.
# The function accepts a POST request with JSON data containing the user's email to be deleted.
# If the user with the specified email exists, their account will be deleted from the database.
#
# @param email: The email of the user whose account needs to be deleted.
# @return: A JSON object indicating whether the account deletion was successful or not.
@admin.route('/delete_user',methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_user():
    try:
        id = request.json['id']
        user = get_school_user(id)
        
        if user:
            deleted_username = user.username
            deleted_type = user.type
            db.session.delete(user)
            db.session.commit()
            log_admin_action(
                'delete', 'user', id,
                f'username={deleted_username}, type={deleted_type}'
            )
            return jsonify({'message': 'Account deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid ID'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/readers/<int:user_id>/remove_from_school', methods=['POST'])
@login_required
@admin_required
def remove_reader_from_school(user_id):
    """PRD §6 — offboard a student from a school WITHOUT touching their Global
    Reading Passport. Removes only the User_shcool membership for the given
    school; the reader's account, reading history, word progress, streaks,
    achievements, and certificates all remain. Deliberately distinct from
    /delete_user, which destroys the whole account."""
    try:
        data = request.get_json(silent=True) or {}
        requested_school_id = data.get('school_id') or data.get('shcool_id')

        if requested_school_id is not None:
            school_id = int(requested_school_id)
            if not is_super_admin():
                allowed = get_scoped_school_ids()
                if not allowed or school_id not in allowed:
                    return jsonify({'message': 'You do not manage this school'}), 403
        elif is_super_admin():
            return jsonify({'message': 'school_id is required'}), 400
        else:
            school_id = get_current_school_id()
            if not school_id:
                return jsonify({'message': 'No school context for this admin'}), 400

        reader = Reader.query.get(user_id)
        if reader is None:
            return jsonify({'message': 'Reader not found'}), 404

        membership = User_shcool.query.filter_by(user_id=user_id, shcool_id=school_id).first()
        if membership is None:
            return jsonify({'message': 'This student is not enrolled in that school'}), 404

        # Resolved before the membership goes away so the notification/email can
        # still name the school and reach the managing parent.
        school = Shcool.query.get(school_id)
        parent = get_parent_for_reader(reader)

        was_default = membership.is_default
        db.session.delete(membership)
        # Offboarding returns the seat: the student is no longer one of this
        # school's activated readers, whatever they keep in their passport.
        release_seat(user_id, school_id, reason='removed_from_school')
        db.session.flush()

        # Keep a sensible default among any remaining memberships so the
        # reader still resolves a school context next time they sign in.
        remaining = User_shcool.query.filter_by(user_id=user_id).all()
        if was_default and remaining and not any(m.is_default for m in remaining):
            remaining[0].is_default = True

        db.session.commit()

        # Told after the removal is durable, and never allowed to undo it: a
        # failed bell or a dead mail server must not leave the student enrolled,
        # nor turn a completed removal into an error the admin will retry.
        try:
            commit_notification_event(
                notify_reader_removed_from_school, reader, school, parent=parent
            )
            send_removed_from_school_emails(reader, school, parent=parent)
        except Exception as error:
            logging.error(
                'remove_reader_from_school: could not notify reader %s: %s',
                user_id, error, exc_info=True
            )

        return jsonify({
            'message': 'Student removed from this school. Their Reading Passport is preserved.',
            'user_id': user_id,
            'school_id': school_id,
            'remaining_schools': len(remaining),
        }), 200
    except (TypeError, ValueError):
        db.session.rollback()
        return jsonify({'message': 'school_id must be a number'}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('remove_reader_from_school failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error'}), 500


## @brief Route to revoke administrator roles from another administrator.
#
# This route is used by administrators to revoke administrator roles from another administrator based on the email provided.
# The function accepts a POST request with JSON data containing the email of the other administrator whose roles need to be revoked.
# If the user with the specified email exists and is an administrator, their 'is_admin' attribute will be set to False,
# removing their administrator rights.
#
# @param email: The email of the other administrator whose roles need to be revoked.
# @return: A JSON object indicating whether the operation was successful or not.
@admin.route('/revoke_admin_roles',methods=['POST'])
@login_required
@admin_required
def revoke_admin_roles():
    try:
        email=request.json['email']
        admin=Admin.query.filter_by(email=email).first()
        if admin:

            follow_session=Follow_session.query.filter_by(user_id=admin.id).first()
            follow_pack=Follow_pack.query.filter_by(user_id=admin.id).first()
            #a revoir
            db.session.delete(follow_session) if follow_session else None
            db.session.delete(follow_pack) if follow_pack else None
            db.session.commit()

            reader=Reader(id=admin.id,username=admin.username,email=email,password_hashed=admin.password_hashed)
            db.session.delete(admin)
            db.session.commit()
            db.session.add(reader)
            db.session.commit()
            return jsonify({'message':'Admin\'s roles revoked succesfully'}),200
        else:
            return jsonify({'message':'Invalid email'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500
        

## @brief Route for administrator logout.
#
# This route is used by administrators to log out from the system.
# After successful logout, the function returns a JSON object indicating that the logout was successful.
#
# @return: A JSON object notifying if the logout was successful.
@admin.route('/logout')
@login_required
@admin_required
def logout():
    logout_user()
    return jsonify({'message':'You are logged out sucessufully'}),200


## @brief Route for creating a new formation.
#
# This route is used by administrators to create a new formation based on the data provided in the request.
# The function accepts a POST request with JSON data containing the title, author, place, and date of the formation.
# The formation is then added to the database.
#
# @param title: Title of the book associated with the formation.
# @param author: Author of the book associated with the formation.
# @param place: Location of the formation, which can be 'online' or 'classroom'.
# @param date_str: Date of the formation in the format 'YYYY-MM-DD'.
#
# @return: A JSON object indicating whether the formation creation was successful or not.


# Get all sessions


def generate_random_color():
    # Generate a random RGB color code
    rgb_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    # Convert the RGB color to a hex color code
    hex_color = webcolors.rgb_to_hex(rgb_color)

    return hex_color

@admin.route('/sessions', methods=['GET'])
def get_sessions():
    sessions = school_accessible_session_query().all()
    session_list = []
    
    teacher_color_mapping = {}  # Dictionary to store teacher colors

    for session in sessions:
        teacher_id = session.teacher_id
        teacher = Teacher.query.get(teacher_id)
        pack = Pack.query.get(session.pack_id)

        # Handle the case where teacher is None
        if not teacher:
            teacher_name = "Unknown Teacher"
            teacher_color = "#000000"  # Default color for unknown teacher
        else:
            # Check if the teacher already has a color assigned
            if teacher_id not in teacher_color_mapping:
                # Generate a random color for the current teacher
                teacher_color_mapping[teacher_id] = generate_random_color()

            # Use the color associated with the current teacher
            teacher_color = teacher_color_mapping[teacher_id]
            teacher_name = teacher.username

        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': teacher_id,
            'teacher_name': teacher_name,
            'teacher_color': teacher_color,
            'location': session.location.value if session.location else None,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active,
            'unit_id': session.unit_id,
            'jitsi_room': session.jitsi_room,
            'meet_link': session.meet_link,
            'video_call_available': is_online_session(session),
            'source': 'global' if pack and is_global_pack(pack) else 'school',
            'read_only': bool(pack and is_global_pack(pack))
        })

    return jsonify({'sessions': session_list}), 200


# get session by teacher
@admin.route('/sessions_by_teacher/<int:teacher_id>', methods=['GET'])
def get_sessions_by_teacher(teacher_id):
    if not user_belongs_to_current_school(teacher_id):
        return jsonify({'message': 'Teacher not found'}), 404
    sessions = school_session_query().filter(Session.teacher_id == teacher_id).all()
    session_list = []

    for session in sessions:
        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': session.teacher_id,
            'location': session.location.value if session.location else None,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active,
            'jitsi_room': session.jitsi_room,
            'meet_link': session.meet_link,
            'video_call_available': is_online_session(session)
        })

    return jsonify({'sessions': session_list}), 200

# get  reader in session 
@admin.route('/reader_in_session/<int:session_id>', methods=['GET'])
def reader_in_session(session_id):
    try:
        if not get_school_session(session_id):
            return jsonify({'message': 'Session not found'}), 404
        session_follow_requests = Follow_session.query.filter_by(session_id=session_id, approved=True).all()
        
        all_session = []
        for follow_request in session_follow_requests:
            user_info = User.query.get(follow_request.user_id)
            all_session.append({

                'user_id': user_info.id,
                'username': user_info.username,
                'email': user_info.email,
                'img' : user_info.img,
                'quiz_id':user_info.quiz_id,
                'presence':follow_request.presence
            })

        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/user_session/<string:code>', methods=['GET'])
def user_session(code):
    try:
        print(code)
        user_code = get_school_code_by_value(code)
        if not user_code:
            return jsonify({'message': 'Code not found'}), 404
        user = User.query.filter_by(id=user_code.user_id).first()
        if not user or not user_belongs_to_current_school(user.id):
            return jsonify({'message': 'User not found'}), 404
        print(user.id)
        session_follow_requests = Follow_session.query.filter_by(user_id=user.id).all()
       
        all_session = []
        
        for follow_request in session_follow_requests:
            session = get_school_session(follow_request.session_id)
            if not session:
                continue
            # print(session)
            all_session.append({
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'img' : user.img,
                'quiz_id':user.quiz_id,
                'start_date':session.start_date,
                'end_date':session.end_date,
                'name':session.name,
                'presence':follow_request.presence
            })
        print(all_session )
        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error','error':e}), 500



@admin.route('/reader_in_pack/<int:pack_id>', methods=['GET'])
def reader_in_pack(pack_id):
    try:
        if not get_school_accessible_pack(pack_id):
            return jsonify({'message': 'Pack not found'}), 404
        school_user_ids = get_current_school_user_ids()
        pack_follow_requests = (
            Follow_pack.query
            .filter(Follow_pack.pack_id == pack_id)
            .filter(Follow_pack.user_id.in_(school_user_ids) if school_user_ids else False)
            .all()
        )
        
        user_in_pack = []
        for follow_request in pack_follow_requests:
            user_info = User.query.get(follow_request.user_id)
            user_in_pack.append({

                'user_id': user_info.id,
                'username': user_info.username,
                'email': user_info.email,
                'img' : user_info.img,
                'quiz_id':user_info.quiz_id,
                'presence':follow_request.presence
            })

        return jsonify({'user_in_pack': user_in_pack}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



#update presence 
@admin.route('/update_presence/<int:session_id>/<int:user_id>', methods=['PUT'])
def update_presence(session_id, user_id):
    try:
        if not get_school_accessible_session(session_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Session or user not found'}), 404
        # Get the request data
        data = request.get_json()

        # Check if the 'presence' field is provided in the request data
        if 'presence' in data:
            presence = data['presence']

            # Find the Follow_session record for the specified session and user
            follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

            if follow_request:
                # Update the 'presence' field
                follow_request.presence = presence
                db.session.commit()

                return jsonify({'message': 'Presence updated successfully'}), 200
            else:
                return jsonify({'message': 'Follow_session record not found for the specified session and user'}), 404
        else:
            return jsonify({'message': 'Please provide the "presence" field in the request data'}), 400

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


# Define the route to get sessions by book_id from request body
@admin.route('/sessions_in_book', methods=['POST'])
def get_sessions_by_book_id_from_body():
    data = request.get_json(silent=True) or {}
    
    # Check if the 'book_id' key exists in the JSON request body
    if 'book_id' not in data:
        return jsonify({'message': 'The request must contain a "book_id" field in the JSON body'}), 400

    book_id = data['book_id']

    # Query sessions with the specified book_id
    sessions = school_session_query().filter(Session.book_id == book_id).all()
    
    # Check if sessions were found
    if not sessions:
        return jsonify({'message': 'No sessions found for book_id {}'.format(book_id)}), 404
    
    # Create a list to store session information
    session_list = []

    for session in sessions:
        teacher = Teacher.query.filter_by(id=session.teacher_id).first()
        book = Book.query.filter_by(id=session.book_id).first()

        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': session.teacher_id,
            'location': session.location.value if session.location else None,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active,
            'book_name' : book.title if book else None,
            'teacher_name' : teacher.username if teacher else None,
            'jitsi_room': session.jitsi_room,
            'meet_link': session.meet_link,
            'video_call_available': is_online_session(session)

        })

    return jsonify({'sessions': session_list}), 200

# Create a new session
@admin.route('/create_session', methods=['POST'])
def create_session():
    try:

        data = request.get_json()
        unit_id = None

        # Validate required fields
        required_fields = ['name', 'start_date','end_date','unit']
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400   
        pack = get_school_pack(data['pack_id'])
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        if not user_belongs_to_current_school(data['teacher_id']):
            return jsonify({'message': 'Teacher not found'}), 404
        exist_session=school_session_query().filter(Session.name == data['name']).first()
        teacher = Teacher.query.filter_by(id=data['teacher_id']).first()
        book = Book.query.filter_by(id=data['book_id']).first()
        if not teacher:
            return jsonify({'message': 'Teacher not found'}), 404
        if not book:
            return jsonify({'message': 'Book not found'}), 404
        exist_unit=Unit.query.filter_by(name=data['unit'],book_id=data['book_id']).first()
        if exist_unit:
            unit_id =exist_unit.id
        else:
            new_unit=Unit(name=data['unit'],book_id=data['book_id'])
            db.session.add(new_unit)
            db.session.commit()
            unit_id= new_unit.id
        if exist_session :
            return jsonify({'message':'Session name already exist'}),404
        else:
             new_session = Session(
             name=data['name'],
             capacity=data['capacity'],
             book_id=data['book_id'],
             teacher_id=data['teacher_id'],
             location=parse_session_location(data.get('location')),
             start_date=data['start_date'],
             end_date=data['end_date'],
             pack_id=data['pack_id'],
             description=data['description'],
             active=data['active'],
             unit_id=unit_id
            )
    
        db.session.add(new_session)
        db.session.flush()
        ensure_jitsi_room(new_session)
        db.session.commit()
        commit_notification_event(notify_session_created, new_session)
        session_info = {

             'id': new_session.id,
             'name': new_session.name,
             'capacity': new_session.capacity,
             'book_id': new_session.book_id,
             'teacher_id': new_session.teacher_id,
             'location': new_session.location.value,
             'start_date': new_session.start_date,
             'end_date': new_session.end_date,
             'pack_id': new_session.pack_id,
             'description': new_session.description,
             'active': new_session.active,
             'jitsi_room': new_session.jitsi_room,
             'meet_link': new_session.meet_link,
             'video_call_available': is_online_session(new_session),
             'book_name' : book.title if book else None,
             'teacher_name' : teacher.username if teacher else None
             }

        return jsonify({'message': 'Session created successfully','session':session_info}), 201
    
    except Exception as e:
        print(e)
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

#get session numbers 
@admin.route('/session_count', methods=['POST'])
def count_sessions():
    try:
        book_id = request.json['book_id']
        pack_id = request.json['pack_id']
        if not get_school_accessible_pack(pack_id):
            return jsonify({'message': 'Pack not found'}), 404
        # Get the session related with pack bok 
        sessions = school_accessible_session_query().filter(Session.book_id == book_id, Session.pack_id == pack_id).count()
        return jsonify({'session_number':sessions})


    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500    



GAME_TYPE_LABELS = {
    'bee-genius': 'Bee Genius',
    'word-explorer': 'Word Explorer',
    'think-word': 'Think Word',
    'intellect-link': 'Intellect Link'
}

@admin.route('/packs/<int:pack_id>/publish-readiness', methods=['GET'])
def get_pack_publish_readiness(pack_id):
    try:
        pack = get_school_accessible_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        school_id = get_current_school_id()

        books = (
            db.session.query(Book.id, Book.title)
            .join(Book_pack, Book_pack.book_id == Book.id)
            .filter(Book_pack.pack_id == pack.id)
            .all()
        )
        book_ids = [book.id for book in books]

        scheduled_by_book = {}
        if book_ids:
            game_rows = (
                db.session.query(GameCalendarEntry.book_id, GameCalendarEntry.game_type)
                .filter(
                    GameCalendarEntry.shcool_id == school_id,
                    GameCalendarEntry.book_id.in_(book_ids)
                )
                .distinct()
                .all()
            )
            for book_id, game_type in game_rows:
                scheduled_by_book.setdefault(book_id, set()).add(game_type)

        session_count_by_book = {}
        if book_ids:
            session_rows = (
                db.session.query(Session.book_id, func.count(Session.id))
                .filter(Session.pack_id == pack.id, Session.book_id.in_(book_ids))
                .group_by(Session.book_id)
                .all()
            )
            session_count_by_book = dict(session_rows)

        books_payload = []
        books_ready = 0
        for book in books:
            scheduled = scheduled_by_book.get(book.id, set())
            missing = [g for g in SUPPORTED_GAME_TYPES if g not in scheduled]
            all_scheduled = not missing
            session_count = session_count_by_book.get(book.id, 0)
            has_sessions = session_count > 0
            ready = all_scheduled and has_sessions
            if ready:
                books_ready += 1

            books_payload.append({
                'id': book.id,
                'title': book.title,
                'games': {
                    'scheduled': [GAME_TYPE_LABELS.get(g, g) for g in SUPPORTED_GAME_TYPES if g in scheduled],
                    'missing': [GAME_TYPE_LABELS.get(g, g) for g in missing],
                    'all_scheduled': all_scheduled
                },
                'sessions': {
                    'count': session_count,
                    'has_sessions': has_sessions
                },
                'ready': ready
            })

        return jsonify({
            'pack': {'id': pack.id, 'title': pack.title, 'public': pack.public},
            'summary': {'books_total': len(books), 'books_ready': books_ready},
            'books': books_payload
        }), 200
    except Exception as error:
        logging.error('Unable to compute pack publish readiness: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/packs/<int:pack_id>/publish', methods=['POST'])
def publish_pack(pack_id):
    try:
        pack = get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        pack.public = True
        db.session.add(pack)
        db.session.commit()
        return jsonify({
            'message': 'Pack published successfully',
            'pack': {'id': pack.id, 'public': pack.public}
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to publish pack: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/packs/<int:pack_id>/unpublish', methods=['POST'])
def unpublish_pack(pack_id):
    try:
        pack = get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        pack.public = False
        db.session.add(pack)
        db.session.commit()
        return jsonify({
            'message': 'Pack unpublished successfully',
            'pack': {'id': pack.id, 'public': pack.public}
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to unpublish pack: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/delete_session', methods=['POST'])
def delete_session():
    try:
        token = request.json['id']
        # Get the session to be deleted
        session = get_school_session(token)
        if session:
            pack = Pack.query.get(session.pack_id) if session.pack_id else None
            notification_user_ids = get_session_audience_ids(session)
            session_notification_data = {
                'id': session.id,
                'name': session.name,
                'pack_id': session.pack_id,
                'book_id': session.book_id,
                'school_id': pack.shcool_id if pack else None
            }
            # Delete all associated records in Follow_session table
            follow_sessions = Follow_session.query.filter_by(session_id=session.id).all()
            for follow in follow_sessions:
                db.session.delete(follow)
            # Delete all associated records in Session_quiz table
            session_quizzes = Session_quiz.query.filter_by(session_id=session.id).all()
            for session_quiz in session_quizzes:
                db.session.delete(session_quiz)
            # Commit the changes
            db.session.commit()
            # Delete the session
            db.session.delete(session)
            db.session.commit()
            commit_notification_event(notify_session_deleted, session_notification_data, notification_user_ids)

            return jsonify({'message': 'Session and associated records successfully deleted'})
        else:
            return jsonify({'message': 'No matching session found'})
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500


# Get a specific session by ID
@admin.route('/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id):
    session = get_school_accessible_session(session_id)

    if session is None:
        return jsonify({'message': 'Session not found'}), 404
    teacher = Teacher.query.filter_by(id=session.teacher_id).first()
    book = Book.query.filter_by(id=session.book_id).first()
    pack = Pack.query.get(session.pack_id)
    session_info = {
        'id': session.id,
        'name': session.name,
        'img': session.img,
        'capacity': session.capacity,
        'book_id': session.book_id,
        'teacher_id': session.teacher_id,
        'location': session.location.value if session.location else None,
        'start_date': str(session.start_date),
        'end_date': str(session.end_date),
        'pack_id': session.pack_id,
        'description': session.description,
        'active': session.active,
        'book_name' : book.title if book else None,
        'teacher_name' : teacher.username if teacher else None,
        'jitsi_room': session.jitsi_room,
        'meet_link':session.meet_link,
        'video_call_available': is_online_session(session),
        'source': 'global' if pack and is_global_pack(pack) else 'school',
        'read_only': bool(pack and is_global_pack(pack))
    }

    return jsonify({'session': session_info}), 200

@admin.route('/sessions/<int:session_id>/video-call', methods=['GET'])
@login_required
def get_admin_session_video_call(session_id):
    try:
        if not is_admin_role():
            return jsonify({'message': 'Admin access is required'}), 401

        if is_super_admin():
            session = Session.query.get(session_id)
        else:
            session = get_school_accessible_session(session_id)

        if not session:
            return jsonify({'message': 'Session not found'}), 404
        if not is_online_session(session):
            return jsonify({'message': 'Video call is available only for online sessions'}), 400

        call_data = serialize_jitsi_call(session, current_user, is_moderator=True)
        db.session.commit()
        return jsonify(call_data), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to generate admin session video call: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/update_session', methods=['POST'])
@login_required
@admin_or_assistant_required
def update_session():
    try:
        data = request.json
        
        token = data['id']
        
        session_to_update = get_school_session(token)
        
        if not session_to_update:
            return jsonify({'message': 'Session not found'}), 404
        
        was_online = is_online_session(session_to_update)
        teacher = Teacher.query.filter_by(id=session_to_update.teacher_id).first()
        book = Book.query.filter_by(id=session_to_update.book_id).first()
        
        if 'name' in data:
            new_name = data['name']
            # Check if the new name is an empty string or if it's already in use by another session
            if not new_name.strip():
                return jsonify({'message': 'Name cannot be empty'}), 400
            elif Session.query.filter(Session.name == new_name, Session.id != token).first():
                return jsonify({'message': 'Name is already in use by another session'}), 400
            session_to_update.name = new_name
        
        if 'pack_id' in data and not get_school_pack(data['pack_id']):
            return jsonify({'message': 'Pack not found'}), 404
        if 'teacher_id' in data and not user_belongs_to_current_school(data['teacher_id']):
            return jsonify({'message': 'Teacher not found'}), 404

        session_to_update.book_id = data['book_id'] if 'book_id' in data else session_to_update.book_id
        session_to_update.teacher_id = data['teacher_id'] if 'teacher_id' in data else session_to_update.teacher_id
        session_to_update.location = parse_session_location(data['location']) if 'location' in data else session_to_update.location
        session_to_update.start_date = data['start_date'] if 'start_date' in data else session_to_update.start_date
        session_to_update.end_date = data['end_date'] if 'end_date' in data else session_to_update.end_date
        session_to_update.description = data['description'] if 'description' in data else session_to_update.description
        session_to_update.active = data['active'] if 'active' in data else session_to_update.active
        session_to_update.capacity = data['capacity'] if 'capacity' in data else session_to_update.capacity
        session_to_update.pack_id = data['pack_id'] if 'pack_id' in data else session_to_update.pack_id
        session_to_update.meet_link = data['meet_link'] if 'meet_link' in data else session_to_update.meet_link
        ensure_jitsi_room(session_to_update)
  
        db.session.commit()
        commit_notification_event(notify_session_updated, session_to_update, became_online=(not was_online and is_online_session(session_to_update)))
        teacher = Teacher.query.filter_by(id=session_to_update.teacher_id).first()
        book = Book.query.filter_by(id=session_to_update.book_id).first()

        session_info = {
            'id': session_to_update.id,
            'name': session_to_update.name,
            'capacity': session_to_update.capacity,
            'book_id': session_to_update.book_id,
            'teacher_id': session_to_update.teacher_id,
            'location': session_to_update.location.value if session_to_update.location else None,
            'start_date': str(session_to_update.start_date),
            'end_date': str(session_to_update.end_date),
            'pack_id': session_to_update.pack_id,
            'description': session_to_update.description,
            'active': session_to_update.active,
            'book_name': book.title if book else None,
            'teacher_name': teacher.username if teacher else None,
            'jitsi_room': session_to_update.jitsi_room,
            'meet_link':session_to_update.meet_link,
            'video_call_available': is_online_session(session_to_update)
        }
        
        return jsonify({'message': 'Session details updated successfully', 'session': session_info}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    

## @brief Route for suggesting books for a user based on their preferences.
#
# This route is used by administrators to suggest books to a user based on their preferences and previous follows.
# The function accepts a POST request with JSON data containing the user's email.
# The function calculates the user's most followed book category and suggests books from that category.
# If there are suggestions available, a JSON object containing the book details is returned as a response.
# If no suggestions are found, a JSON object with a message indicating so is returned.
#
# @param email: Email of the user for whom the book suggestions are to be made.
#
# @return: A JSON object containing book suggestions or a message if no suggestions are found.
@admin.route('/suggest_book_for_user', methods=['POST'])
@login_required
@admin_required
def suggest_book_for_user():
    try:
        email = request.json['email']

        most_category = db.session.query(Book.category, func.count().label('count')).filter(User.email == email).join(Follow_session, Follow_session.user_id == User.id).join(Session, Session.id == Follow_session.session_id).join(Book,Book.id==Session.book_id).group_by(Book.category).order_by(func.count().desc()).first()

        if most_category:
            category, _ = most_category  # Extract the category from the tuple
            
            books = Book.query.filter(Book.category == category).all()
            suggestions = []
            for book in books:
                suggestions.append({
                    'title': book.title,
                    'author': book.author,
                    'page_number': book.page_number,
                    'release_date': book.release_date,
                    'category': book.category
                })

            return jsonify({'suggestions': suggestions}), 200
        else:
            return jsonify({'message': 'No suggestion found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/show_all_books', methods=['GET'])
def get_all_books():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        books_query = school_book_query()
        search = str(request.args.get('search') or '').strip()
        if search:
            books_query = books_query.filter(
                or_(
                    Book.title.ilike(f'%{search}%'),
                    Book.author.ilike(f'%{search}%'),
                    Book.category.ilike(f'%{search}%')
                )
            )

        books_query = books_query.order_by(Book.title.asc())
        per_page = request.args.get('per_page') or request.args.get('limit')
        if per_page:
            per_page = min(get_positive_int_value(per_page, 'per_page'), 100)
            books_query = books_query.limit(per_page)

        books = books_query.all()
   
        # Create a list to store the book data
        book_list = []

        # Loop through the books and create a dictionary for each book
        for book in books:
            book_data = serialize_admin_book(book)
            pack_ids = (
                db.session.query(Pack.id)
                .join(Book_pack, Pack.id == Book_pack.pack_id)
                .filter(Book_pack.book_id == book.id, Pack.shcool_id == school_id)
                .all()
            )
            book_data['school_id'] = school_id
            book_data['pack_ids'] = [pack_id for (pack_id,) in pack_ids]
            book_list.append(book_data)

        return jsonify(book_list), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


#get all units 
@admin.route('/show_all_units/<int:id>', methods=['GET'])
def get_all_units(id):
    try:
        # Query all books from the database
        units = Unit.query.filter_by(book_id=id).all() 
        # Create a list to store the book data
        unit_list = []
        # Loop through the books and create a dictionary for each book
        for unit in units:
            unit_data = {
                'id': unit.id,
                'name': unit.name,
                'book_id': unit.book_id  
            }
            unit_list.append(unit_data)
        return jsonify(unit_list), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
#delete unit 
@admin.route('/delete_unit', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_unit():
    try:
        token = request.json['id']
        unit = Unit.query.filter_by(id=token).first()
        if not unit:
            return jsonify({'message': 'Unit not found'}), 404
        else:
            db.session.delete(unit)  # Corrected from 'unit' to 'unit'
            db.session.commit()
            return jsonify({'message': 'Unit is successfully deleted'}), 200
    except Exception as e:
        return jsonify({'message': f'Internal server error: {str(e)}'}), 500

#create unit 
@admin.route('/create_unit',methods=['POST'])
@login_required
@admin_or_assistant_required
def create_unit():
    try:
        data = request.get_json()
        name=data['name']
        book_id=data['book_id']
        exist_unit=Unit.query.filter_by(name=name,book_id=book_id).first()
 
        if exist_unit :
            return jsonify({'message':'Name already exist'}),404
        else:

           unit=Unit(name=name,book_id=book_id)  
           if unit:
            db.session.add(unit)
            db.session.commit()
            unit_data = {
            'id': unit.id,
            'name': unit.name,
            'book_id': unit.book_id,

        }
            return jsonify({'message':'Unit is sucessfully created','unit':unit_data}),201
           else:
            return jsonify({'message':'Somthing wrong please try later'}),404
    except Exception as e:
        logging.error(f" {str(e)} is required")
        return jsonify({'message':f" {str(e)} is required"}),500
    
#update unit 
@admin.route('/update_unit', methods=['PUT'])
def update_unit():
    try:
        data = request.get_json()

        if 'id' not in data:
            return jsonify({'message': 'Unit ID is missing in the request body'}), 400

        unit_id = data['id']
        unit = Unit.query.get(unit_id)

        if unit is None:
            return jsonify({'message': 'Unit not found'}), 404

        if 'name' in data:
            new_name = data['name']

            # Check if the new name is an empty string or if it's already in use by another unit
            if not new_name.strip():
                return jsonify({'message': 'Name cannot be empty'}), 400
            elif Unit.query.filter(Unit.name == new_name, Unit.id != unit_id).first():
                return jsonify({'message': 'Name is already in use by another unit'}), 400

            unit.name = new_name

        db.session.commit()

        unit_data = {
            'id': unit.id,
            'name': unit.name,
            'book_id': unit.book_id,
        }

        return jsonify({'message': 'Unit updated successfully', 'unit': unit_data}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



# @admin.route('/get_book/<int:id>', methods=['GET'])
# def get_book(id):
#     try:
#         book = Book.query.get(id)

#         if book is None:
#             return jsonify({'message': 'Book not found'}), 404

#         book_data = {
#             'id': book.id,
#             'title': book.title,
#             'author': book.author,
#             'img': book.img,
#             'release_date': book.release_date.strftime('%Y-%m-%d'),  # Format the date as a string
#             'page_number': book.page_number,
#             'category': book.category,
#             'neo4j_id': book.neo4j_id,
#             'desc': book.desc,
           
#         }

#         return jsonify(book_data), 200

#     except Exception as e:
#         logging.error(f"An error occurred: {str(e)}")
#         return jsonify({'message': 'Internal server error'}), 500

## @brief Route for deleting a book from the database.
#
# This route is used by administrators to delete a book from the database based on the title and author provided.
# The function accepts a POST request with JSON data containing the title and author of the book to be deleted.
# The function retrieves the book's instance from the database and deletes it.
# If the book with the specified title and author is found and successfully deleted, a JSON object with a success message is returned.
# If no book with the specified title and author is found, a JSON object with a message indicating so is returned.
#
# @param title: Title of the book to be deleted.
# @param author: Author of the book to be deleted.
#
# @return: A JSON object indicating whether the book deletion was successful or not.

@admin.route('/delete_book', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_book():
    try:
        token = request.json['id']
        book = get_school_book(token)
        if not book:
            return jsonify({'message': 'Book not found'}), 404
        if is_platform_book(book):
            school_id = get_current_school_id()
            instance = get_school_platform_instance(school_id, book.id)
            if not instance:
                return jsonify({'message': 'Platform book instance not found'}), 404
            school_pack_ids = [
                pack_id for (pack_id,) in db.session.query(Pack.id).filter(Pack.shcool_id == school_id).all()
            ]
            if school_pack_ids:
                links = Book_pack.query.filter(
                    Book_pack.book_id == book.id,
                    Book_pack.pack_id.in_(school_pack_ids)
                ).all()
                for link in links:
                    Follow_book.query.filter_by(book_id=book.id, pack_id=link.pack_id).delete(synchronize_session=False)
                    pack = Pack.query.get(link.pack_id)
                    if pack and pack.book_number and pack.book_number > 0:
                        pack.book_number -= 1
                        db.session.add(pack)
                    db.session.delete(link)
            instance.active = False
            instance.updated_at = datetime.now()
            db.session.add(instance)
            db.session.commit()
            return jsonify({'message': 'Platform book removed from this school'}), 200
        else:
            school_id = get_current_school_id()
            school_pack_ids = [
                pack_id for (pack_id,) in db.session.query(Pack.id).filter(Pack.shcool_id == school_id).all()
            ]
            sessions = (
                Session.query.filter(Session.book_id == book.id, Session.pack_id.in_(school_pack_ids)).all()
                if school_pack_ids else []
            )
            book_packs = (
                Book_pack.query.filter(Book_pack.book_id == book.id, Book_pack.pack_id.in_(school_pack_ids)).all()
                if school_pack_ids else []
            )

            for session in sessions:
                Follow_session.query.filter_by(session_id=session.id).delete()
                Session_quiz.query.filter_by(session_id=session.id).delete()
                db.session.delete(session)
            for book_pack in book_packs:
                Follow_book.query.filter_by(book_id=book.id, pack_id=book_pack.pack_id).delete()
                pack = Pack.query.get(book_pack.pack_id)
                if pack and pack.book_number > 0:
                    pack.book_number -= 1
                    db.session.add(pack)
                db.session.delete(book_pack)
            if book.shcool_id == school_id:
                book.shcool_id = None
                db.session.add(book)
            db.session.commit()

            remaining_links = Book_pack.query.filter_by(book_id=book.id).first()
            if not remaining_links and book.shcool_id is None:
                db.session.delete(book)
                db.session.commit()
                return jsonify({'message': 'Book is successfully deleted'}), 200

            return jsonify({'message': 'Book has been removed from this school'}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/books/<int:book_id>/delete-impact', methods=['GET'])
def get_book_delete_impact_preview(book_id):
    try:
        book, error_message, error_status = require_school_owned_editable_book(book_id)
        if not book:
            return jsonify({'message': error_message}), error_status
        return jsonify({
            'book': {
                'id': book.id,
                'title': book.title,
                'author': book.author
            },
            'impact': get_book_delete_impact(book)
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/books/<int:book_id>/archive', methods=['POST'])
def archive_book(book_id):
    try:
        book, error_message, error_status = require_school_owned_editable_book(book_id)
        if not book:
            return jsonify({'message': error_message}), error_status
        book.archived = True
        db.session.commit()
        return jsonify({
            'message': 'Book archived successfully',
            'book': serialize_admin_book(book)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/books/<int:book_id>/unarchive', methods=['POST'])
def unarchive_book(book_id):
    try:
        book, error_message, error_status = require_school_owned_editable_book(book_id)
        if not book:
            return jsonify({'message': error_message}), error_status
        book.archived = False
        db.session.commit()
        return jsonify({
            'message': 'Book unarchived successfully',
            'book': serialize_admin_book(book)
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


## @brief Route for creating a new book in the database.
#
# This route is used by administrators to create a new book in the database with the provided information.
# The function accepts a POST request with JSON data containing the book's title, author, release date, page number, and category.
# A new instance of the Book model is created with the provided data and added to the database.
# If the book creation is successful, a JSON object with a success message is returned.
#
# @param title: Title of the new book.
# @param author: Author of the new book.
# @param release_date: Release date of the new book in the format 'YYYY-MM-DD'.
# @param page_number: Number of pages in the new book.
# @param category: Category of the new book.
#
# @return: A JSON object indicating whether the book creation was successful or not.
@admin.route('/create_book',methods=['POST'])
@login_required
@admin_or_assistant_required
def create_book():   
    try:
        data = request.get_json(silent=True) or {}
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        # Validate required fields
        required_fields = ['title', 'author']
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400

        title = data['title'].strip()
        author = data['author'].strip()
        img = data.get('img')
        release_date = data.get('release_date') or None
        page_number = data.get('page_number')
        category = data.get('category')
        neo4j_id = data.get('neo4j_id')
        desc = data.get('desc')
        pack_ids = normalize_pack_ids(data.get('pack_ids') if 'pack_ids' in data else data.get('pack_id'))

        selected_packs = []
        for pack_id in pack_ids:
            pack = get_school_pack(pack_id)
            if not pack:
                return jsonify({'message': f'Pack {pack_id} not found in current school'}), 404
            selected_packs.append(pack)

        existing_school_book = (
            school_book_query()
            .filter(Book.title == title, Book.author == author)
            .first()
        )
        if existing_school_book:
            return jsonify({'message': 'Book already exists in this school'}), 409

        existing_global_book = Book.query.filter_by(title=title, author=author).first()
        if existing_global_book and is_platform_book(existing_global_book):
            return jsonify({
                'message': 'This is an IRead platform book. Add it with /admin/platform-books/<book_id>/instances or /admin/packs/<pack_id>/platform-books/<book_id>.',
                'book': serialize_platform_book(existing_global_book, school_id=school_id)
            }), 409
        if existing_global_book and not selected_packs:
            return jsonify({
                'message': 'Book already exists globally. Send pack_id or pack_ids to link it to this school.'
            }), 409

        if existing_global_book:
            book = existing_global_book
            if book.shcool_id is None:
                book.shcool_id = school_id
        else:
            book = Book(
                title=title,
                author=author,
                img=img,
                release_date=release_date,
                page_number=page_number,
                category=category,
                neo4j_id=neo4j_id,
                desc=desc,
                shcool_id=school_id,
                is_platform_book=False,
                created_by=current_user.id,
                active=True
            )
            db.session.add(book)
            db.session.flush()

        linked_pack_ids = []
        for pack in selected_packs:
            existing_link = Book_pack.query.filter_by(book_id=book.id, pack_id=pack.id).first()
            if not existing_link:
                db.session.add(Book_pack(book_id=book.id, pack_id=pack.id))
                pack.book_number = (pack.book_number or 0) + 1
                db.session.add(pack)
            linked_pack_ids.append(pack.id)

        db.session.commit()

        book_data = serialize_admin_book(book)
        book_data['school_id'] = school_id
        book_data['pack_ids'] = linked_pack_ids

        status_code = 200 if existing_global_book else 201
        message = 'Book is successfully linked to this school' if existing_global_book else 'Book is successfully created'
        return jsonify({'message': message, 'book': book_data}), status_code
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Create book failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500
    

@admin.route('/update_book', methods=['PUT'])
def update_book():
    try:
        data = request.get_json()

        if 'id' not in data:
            return jsonify({'message': 'Book ID is missing in the request body'}), 400

        book_id = data['id']
        book = get_school_book(book_id)

        if book is None:
            return jsonify({'message': 'Book not found'}), 404
        if is_platform_book(book):
            return jsonify({'message': 'IRead platform books are read-only for school admins'}), 403
        if book.shcool_id != get_current_school_id():
            return jsonify({'message': 'This book is not editable by the current school'}), 403

        if 'title' in data:
            new_title = data['title']

            # Check if the new title is an empty string or if it's already in use by another book
            if not new_title.strip():
                return jsonify({'message': 'Title cannot be empty'}), 400
            elif Book.query.filter(Book.title == new_title, Book.id != book_id).first():
                return jsonify({'message': 'Title is already in use by another book'}), 400

            book.title = new_title

        if 'author' in data:
            book.author = data['author']
        if 'img' in data:
            book.img = data['img']
        if 'release_date' in data:
            book.release_date = data['release_date']
        if 'page_number' in data:
            book.page_number = data['page_number']
        if 'category' in data:
            book.category = data['category']
        if 'desc' in data:
            book.desc = data['desc']
        if 'neo4j_id' in data:
            book.neo4j_id = data['neo4j_id']

        db.session.commit()

        book_data = {
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'img': book.img,
            'release_date': book.release_date.strftime('%Y-%m-%d') if book.release_date else None,
            'page_number': book.page_number,
            'category': book.category,
            'neo4j_id': book.neo4j_id,
            'desc': book.desc,
            'school_id': get_current_school_id()
        }

        return jsonify({'message': 'Book updated successfully', 'book': book_data}), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_book/<int:id>', methods=['GET'])
def get_book(id):
    try:
      
        book = get_school_book(id)
        if book is None:
            return jsonify({'message': 'Book not found'}), 404
        book_data = serialize_admin_book(book)
        book_data['school_id'] = get_current_school_id()

        return jsonify(book_data), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

def get_school_game_context(book_id=None):
    if not is_game_manager_role():
        return None, None, jsonify({'message': 'Admin or teacher access required', 'code': 'GAME_MANAGER_ACCESS_REQUIRED'}), 403

    school_id = get_current_school_id()
    if not school_id:
        return None, None, jsonify({
            'message': 'Current admin has no school assigned',
            'code': 'SCHOOL_REQUIRED'
        }), 403

    if book_id is None:
        return school_id, None, None, None

    book = get_school_book(book_id)
    if not book:
        return school_id, None, jsonify({'message': 'Book not found', 'code': 'BOOK_NOT_FOUND'}), 404
    return school_id, book, None, None


@admin.route('/game-settings', methods=['GET'])
@login_required
def get_admin_game_settings():
    try:
        school_id, _, error_response, error_status = get_school_game_context()
        if error_response:
            return error_response, error_status

        settings = get_school_game_settings(school_id)
        return jsonify({
            'school_id': school_id,
            'shcool_id': school_id,
            'settings': [
                serialize_game_setting(settings.get(game_type), game_type=game_type, school_id=school_id)
                for game_type in SUPPORTED_GAME_TYPES
            ]
        }), 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Get game settings failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/game-settings/<game_type>', methods=['PUT'])
@login_required
def upsert_admin_game_setting(game_type):
    try:
        school_id, _, error_response, error_status = get_school_game_context()
        if error_response:
            return error_response, error_status

        data = request.get_json(silent=True) or {}
        setting, created = get_or_create_game_setting(
            school_id,
            game_type,
            data.get('timer_seconds'),
            data.get('max_hints'),
            data.get('timer_enabled')
        )
        db.session.commit()
        return jsonify({
            'message': 'Game setting created' if created else 'Game setting updated',
            'setting': serialize_game_setting(setting)
        }), 201 if created else 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Upsert game setting failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar', methods=['GET'])
@login_required
def get_admin_book_game_calendar(book_id, game_type):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        game_type = normalize_game_type(game_type)
        start_date = parse_optional_play_date(request.args.get('start_date'), 'start_date')
        end_date = parse_optional_play_date(request.args.get('end_date'), 'end_date')
        if start_date and end_date and end_date < start_date:
            raise GameCalendarError('end_date must be after or equal to start_date', 'INVALID_DATE_RANGE', 400)

        query = get_calendar_entries_query(school_id, book.id, game_type, start_date, end_date)
        page, per_page = get_super_admin_pagination_params()
        total = query.order_by(None).count()
        entries = query.offset((page - 1) * per_page).limit(per_page).all()
        total_pages = (total + per_page - 1) // per_page if total else 0

        return jsonify({
            'school_id': school_id,
            'shcool_id': school_id,
            'book_id': book.id,
            'game_type': game_type,
            'entries': [serialize_calendar_entry(entry) for entry in entries],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
                'max_per_page': MAX_SUPER_ADMIN_PER_PAGE
            }
        }), 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error), 'code': 'INVALID_PAGINATION'}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Get game calendar failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/<play_date>', methods=['PUT'])
@login_required
def upsert_admin_book_game_calendar_day(book_id, game_type, play_date):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        data = request.get_json(silent=True) or {}
        normalized_game_type = normalize_game_type(game_type)
        entry, created = upsert_calendar_entry(
            school_id,
            book.id,
            normalized_game_type,
            play_date,
            data.get('words')
        )
        db.session.commit()
        commit_notification_event(notify_daily_game_created, school_id, book, normalized_game_type, entry.play_date)
        return jsonify({
            'message': 'Calendar entry created' if created else 'Calendar entry updated',
            'entry': serialize_calendar_entry(entry)
        }), 201 if created else 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Upsert calendar entry failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/<play_date>', methods=['DELETE'])
@login_required
def delete_admin_book_game_calendar_day(book_id, game_type, play_date):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        deleted = delete_calendar_entry(school_id, book.id, game_type, play_date)
        if not deleted:
            return jsonify({
                'message': 'Calendar entry not found',
                'code': 'GAME_CALENDAR_ENTRY_NOT_FOUND'
            }), 404
        db.session.commit()
        return jsonify({'message': 'Calendar entry deleted'}), 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Delete calendar entry failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/generate', methods=['POST'])
@login_required
def generate_admin_book_game_calendar(book_id, game_type):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        data = request.get_json(silent=True) or {}
        start_date = data.get('start_date') or request.args.get('start_date')
        if start_date is None:
            raise GameCalendarError('start_date is required', 'START_DATE_REQUIRED', 400)

        raw_overwrite = data.get('overwrite', request.args.get('overwrite', False))
        if isinstance(raw_overwrite, bool):
            overwrite = raw_overwrite
        else:
            raw_overwrite = str(raw_overwrite).strip().lower()
            if raw_overwrite in ['true', '1', 'yes']:
                overwrite = True
            elif raw_overwrite in ['false', '0', 'no', '']:
                overwrite = False
            else:
                raise GameCalendarError('overwrite must be true or false', 'INVALID_OVERWRITE', 400)
        normalized_game_type = normalize_game_type(game_type)
        result = generate_calendar_entries(school_id, book.id, normalized_game_type, start_date, overwrite=overwrite)
        db.session.commit()
        if result.get('created') or result.get('updated'):
            commit_notification_event(
                notify_daily_game_created,
                school_id,
                book,
                normalized_game_type,
                parse_play_date(result['start_date'], 'start_date')
            )
        return jsonify({
            'message': 'Game calendar generated',
            'result': result
        }), 201 if result['created'] else 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Generate game calendar failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


def json_download_response(payload, filename):
    response = Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype='application/json'
    )
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def get_game_calendar_import_json():
    uploaded_file = request.files.get('file') or request.files.get('json_file')
    if uploaded_file:
        try:
            return json.loads(uploaded_file.read().decode('utf-8-sig'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GameCalendarError('Uploaded file must be valid JSON', 'INVALID_IMPORT_JSON', 400)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise GameCalendarError('Request body must be valid JSON', 'INVALID_IMPORT_JSON', 400)
    return data.get('payload') if isinstance(data.get('payload'), dict) else data


def get_import_request_bool(name, default=False):
    if request.form and name in request.form:
        return parse_bool_value(request.form.get(name), name, default=default)

    data = request.get_json(silent=True)
    if isinstance(data, dict) and name in data:
        return parse_bool_value(data.get(name), name, default=default)

    return parse_bool_value(request.args.get(name), name, default=default)


def public_game_calendar_import_result(result):
    public_result = dict(result)
    public_result.pop('valid_entries', None)
    return public_result


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/template', methods=['GET'])
@login_required
def download_admin_book_game_calendar_template(book_id, game_type):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        game_type = normalize_game_type(game_type)
        settings = get_school_game_settings(school_id)
        payload = build_calendar_template_payload(
            school_id,
            book.id,
            game_type,
            setting=settings.get(game_type),
            start_date=request.args.get('start_date')
        )
        return json_download_response(payload, f'{game_type}-calendar-template-book-{book.id}.json')
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Download game calendar template failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/export', methods=['GET'])
@login_required
def export_admin_book_game_calendar_json(book_id, game_type):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        game_type = normalize_game_type(game_type)
        start_date = parse_optional_play_date(request.args.get('start_date'), 'start_date')
        end_date = parse_optional_play_date(request.args.get('end_date'), 'end_date')
        if start_date and end_date and end_date < start_date:
            raise GameCalendarError('end_date must be after or equal to start_date', 'INVALID_DATE_RANGE', 400)

        entries = get_calendar_entries_query(school_id, book.id, game_type, start_date, end_date).all()
        settings = get_school_game_settings(school_id)
        payload = build_calendar_export_payload(
            school_id,
            book.id,
            game_type,
            entries,
            setting=settings.get(game_type)
        )
        return json_download_response(payload, f'{game_type}-calendar-book-{book.id}.json')
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Export game calendar failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500


@admin.route('/books/<int:book_id>/games/<game_type>/calendar/import', methods=['POST'])
@login_required
def import_admin_book_game_calendar_json(book_id, game_type):
    try:
        school_id, book, error_response, error_status = get_school_game_context(book_id)
        if error_response:
            return error_response, error_status

        game_type = normalize_game_type(game_type)
        payload = get_game_calendar_import_json()
        overwrite = get_import_request_bool('overwrite', default=False)
        dry_run = get_import_request_bool('dry_run', default=True)
        apply_settings = get_import_request_bool('apply_settings', default=False)

        if dry_run:
            preview = preview_calendar_import_payload(
                school_id,
                book.id,
                game_type,
                payload,
                overwrite=overwrite,
                validate_settings=apply_settings
            )
            return jsonify({
                'message': 'Game calendar import preview generated',
                'preview': public_game_calendar_import_result(preview)
            }), 200

        result = import_calendar_payload(
            school_id,
            book.id,
            game_type,
            payload,
            overwrite=overwrite,
            validate_settings=apply_settings
        )
        setting_payload = None
        if apply_settings:
            setting_values = get_import_setting_values(game_type, payload)
            if setting_values:
                setting, _ = get_or_create_game_setting(
                    school_id,
                    game_type,
                    setting_values.get('timer_seconds'),
                    setting_values.get('max_hints'),
                    setting_values.get('timer_enabled')
                )
                setting_payload = serialize_game_setting(setting)

        db.session.commit()
        if result.get('created') or result.get('updated'):
            imported_dates = [
                entry.get('date')
                for entry in result.get('valid_entries', [])
                if entry.get('date')
            ]
            if imported_dates:
                commit_notification_event(
                    notify_daily_game_created,
                    school_id,
                    book,
                    game_type,
                    min(imported_dates)
                )
        response_payload = {
            'message': 'Game calendar imported',
            'result': public_game_calendar_import_result(result)
        }
        if setting_payload:
            response_payload['setting'] = setting_payload
        return jsonify(response_payload), 201 if result.get('created') else 200
    except GameCalendarError as error:
        db.session.rollback()
        payload, status = game_error_response(error)
        return jsonify(payload), status
    except Exception as error:
        db.session.rollback()
        logging.error('Import game calendar failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'code': 'INTERNAL_SERVER_ERROR'}), 500

@admin.route('/books/<int:book_id>/stories', methods=['GET'])
def get_admin_book_stories(book_id):
    try:
        book = get_school_book(book_id)
        if not book:
            return jsonify({'message': 'Book not found'}), 404

        if is_platform_book(book):
            stories_query = BookStory.query.filter(
                BookStory.book_id == book.id,
                BookStory.shcool_id.is_(None)
            ).order_by(BookStory.id.desc())
        else:
            stories_query = BookStory.query.filter_by(
                book_id=book.id,
                shcool_id=get_current_school_id()
            ).order_by(BookStory.id.desc())
        return jsonify(paginate_super_admin_query(stories_query, serialize_book_story, 'stories')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/books/<int:book_id>/stories', methods=['POST'])
def upload_admin_book_story(book_id):
    saved_file_path = None
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        book = get_school_book(book_id)
        if not book:
            return jsonify({'message': 'Book not found'}), 404
        if is_platform_book(book):
            return jsonify({'message': 'IRead platform story PDFs are read-only for school admins'}), 403

        if 'file' not in request.files:
            return jsonify({'message': 'PDF file is required'}), 400

        pdf_file = request.files['file']
        if not is_allowed_story_pdf(pdf_file):
            return jsonify({'message': 'Only PDF files are allowed'}), 400

        file_size = get_file_size(pdf_file)
        max_file_size = ConfigClass.MAX_STORY_UPLOAD_MB * 1024 * 1024
        if file_size > max_file_size:
            return jsonify({'message': f'PDF file is too large. Max size is {ConfigClass.MAX_STORY_UPLOAD_MB} MB'}), 413

        title = (request.form.get('title') or '').strip()
        if not title:
            title = os.path.splitext(secure_filename(pdf_file.filename))[0] or 'Story'
        description = request.form.get('description')
        original_filename = secure_filename(pdf_file.filename)
        stored_filename = f'{uuid4().hex}.pdf'
        upload_dir = get_story_upload_dir(school_id, book.id)
        saved_file_path = os.path.join(upload_dir, stored_filename)
        pdf_file.save(saved_file_path)

        story = BookStory(
            book_id=book.id,
            shcool_id=school_id,
            uploaded_by=current_user.id,
            title=title,
            description=description,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=saved_file_path,
            file_url=f'/reader/stories/{{story_id}}/pdf',
            mime_type=pdf_file.mimetype or 'application/pdf',
            file_size=file_size,
            page_count=None,
            active=True
        )
        db.session.add(story)
        db.session.flush()
        story.file_url = f'/reader/stories/{story.id}/pdf'
        db.session.commit()

        return jsonify({
            'message': 'Story uploaded successfully',
            'story': serialize_book_story(story)
        }), 201
    except Exception as error:
        db.session.rollback()
        if saved_file_path and os.path.exists(saved_file_path):
            os.remove(saved_file_path)
        logging.error('Story upload failed: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/stories/<int:story_id>', methods=['PUT'])
def update_admin_book_story(story_id):
    try:
        story = get_school_book_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404

        data = request.get_json(silent=True) or {}
        if 'title' in data:
            title = str(data.get('title') or '').strip()
            if not title:
                return jsonify({'message': 'Title cannot be empty'}), 400
            story.title = title
        if 'description' in data:
            story.description = data.get('description')
        if 'active' in data:
            story.active = parse_bool_value(data.get('active'), 'active')

        db.session.commit()
        return jsonify({
            'message': 'Story updated successfully',
            'story': serialize_book_story(story)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/stories/<int:story_id>', methods=['DELETE'])
def delete_admin_book_story(story_id):
    try:
        story = get_school_book_story(story_id)
        if not story:
            return jsonify({'message': 'Story not found'}), 404

        file_path = story.file_path
        db.session.delete(story)
        db.session.commit()
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({'message': 'Story deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/packs', methods=['GET'])
@admin.route('/show_all_packs', methods=['GET'])
def get_school_packs():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        search = request.args.get('search') or request.args.get('title')
        level = str(request.args.get('level') or '').strip()
        age = parse_pack_age(request.args.get('age'))
        sort_order = str(request.args.get('sort_order') or 'desc').strip().lower()
        packs_query = school_accessible_pack_query()

        if search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{search}%'))
        if level:
            packs_query = packs_query.filter(func.lower(Pack.level) == level.lower())
        if age:
            packs_query = packs_query.filter(Pack.age == age)

        if sort_order not in ['asc', 'desc']:
            raise ValueError('sort_order must be asc or desc')

        packs_query = packs_query.order_by(Pack.id.asc() if sort_order == 'asc' else Pack.id.desc())
        response = paginate_super_admin_query(
            packs_query,
            lambda pack: serialize_super_pack(pack, school_id),
            'packs'
        )
        school = Shcool.query.get(school_id)
        response['school_id'] = school_id
        response['school'] = school.name if school else None

        return jsonify(response), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/get_pack_details', methods=['GET', 'POST'])
def get_admin_pack_details():
    try:
        pack = get_admin_pack_from_request()
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        pack_details = serialize_admin_pack_details(pack)
        return jsonify({'pack': pack_details, **pack_details}), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/packs/<int:pack_id>/delete-impact', methods=['GET'])
def get_pack_delete_impact_preview(pack_id):
    try:
        pack = get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        return jsonify({
            'pack': {
                'id': pack.id,
                'title': pack.title,
                'level': pack.level,
                'age': pack.age.value if pack.age else None
            },
            'impact': get_pack_delete_impact(pack)
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/get_books_from_pack', methods=['GET', 'POST'])
def get_admin_books_from_pack():
    try:
        pack = get_admin_pack_from_request()
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        context_school_id = get_current_school_id() if current_user.is_authenticated and not is_super_admin() else pack.shcool_id
        books = [serialize_admin_book(book, context_school_id) for book in get_admin_books_in_pack(pack.id)]
        return jsonify({
            'school_id': context_school_id if is_global_pack(pack) else pack.shcool_id,
            'shcool_id': context_school_id if is_global_pack(pack) else pack.shcool_id,
            'pack_id': pack.id,
            'books_in_pack': books,
            'books': books
        }), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@admin.route('/create_pack', methods=['POST'])
def create_pack():
    try:
        data = request.get_json()
        # Validate required fields
        required_fields = ['title', 'level',]
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400
        duration= data['duration']
        title = data['title']
        level = data['level']
        img = data['img']
        age = data.get('age')
        price = data['price']
        discount = data['discount']
        desc = data['desc']
        faq = data['faq']
        shcool_id = get_current_school_id()
        if not shcool_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        public=data['public']
        # Check if the title is already used
        if Pack.query.filter_by(title=title, shcool_id=shcool_id).first():
            return jsonify({'message': 'Title is already used'}), 409
            
        invoicing_product ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}',
                'title': title,
                'price': price,
                'vat':0,
                'quantity': 999,
                }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/product/create', json=invoicing_product)  
        if invoicing_response.status_code==201:
            invoicing_data = invoicing_response.json()
            
            prodcut_id = invoicing_data['_id']
            # Create a new pack
            pack = Pack(
                title=title,
                level=level,
                img=img,
                age=age,
                price=price,
                discount=discount,
                desc=desc,
                faq=faq,
                duration=duration,
                product_id_invoicing_api=prodcut_id,
                shcool_id=shcool_id,
                is_global_pack=False,
                created_by=current_user.id,
                active=True
            )
            db.session.add(pack)
            db.session.commit()
            commit_notification_event(notify_school_pack_created, pack)
            pack_data = {
               'id': pack.id,
               'title': pack.title,
               'level': pack.level,
               'img': pack.img,
               'age': pack.age.value,
               'price': pack.price,
               'discount': pack.discount,
               'desc': pack.desc,
               'book_number': pack.book_number,
               'faq' : pack.faq,
               'duration':pack.duration,
               'product_id_invoicing_api':prodcut_id,
               'shcool_id' :pack.shcool_id,
               'public':pack.public
                }
            return jsonify({'message': 'Pack is successfully created', 'pack': pack_data}), 201
    except Exception as e:
        print(e)  # Log the error for debugging
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/add_book_to_pack',methods=['POST'])
@login_required
@admin_or_assistant_required
def add_book_to_pack():
    try:
        pack_token=request.json['pack_id']
        book_token=request.json['book_id']
        
        book=get_school_book(book_token)
        pack=get_school_pack(pack_token)
        
        if book and pack:
            existing_book=Book_pack.query.filter_by(book_id=book.id,pack_id=pack.id).first()
            if not existing_book:
                    book_pack=Book_pack(pack_id=pack.id,book_id=book.id)
                    pack.book_number+=1
                    db.session.add(book_pack)
                    db.session.add(pack)
                    db.session.commit()
                    commit_notification_event(notify_book_added_to_pack, pack, book)
                    book_data = {
                        'id': book.id,
                        'title': book.title,
                        'author': book.author,
                        'img': book.img,
                        'release_date': book.release_date.strftime('%Y-%m-%d'),  # Format the date as a string
                        'page_number': book.page_number,
                        'category': book.category,
                        'neo4j_id': book.neo4j_id
        }



                    return jsonify({'message':'Book is sucessfully added','book':book_data}), 200
            else:
                return jsonify({'message':'Book already exist in this pack'}),400
        else:
            return jsonify({'message':'Book not found or pack not found'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500


@admin.route('/delete_book_from_pack', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_book_from_pack():
    try:
        book_token = request.json['book_id']
        pack_token=request.json['pack_id']
        
        pack=get_school_pack(pack_token)
        
        book = get_school_book(book_token)
        
        if book:
            if not pack:
                return jsonify({'message': 'Pack not found'}), 404
            else:
                record = Book_pack.query.filter_by(book_id=book.id,pack_id=pack.id).first()
                if record:
                    pack.book_number-=1
                    db.session.delete(record)
                    db.session.commit()
                    
                    return jsonify({'message': 'Book removed from pack successfully'}), 200
                else:
                    return jsonify({'message': 'Book is not in this pack'}), 404
        else:
            return jsonify({'message': 'Book not found'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500


@admin.route('/delete_pack', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_pack():
    try:
        token = (request.get_json(silent=True) or {}).get('id')
        pack = get_school_pack(token)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        impact = get_pack_delete_impact(pack)
        session_ids = [
            session_id for (session_id,) in (
                db.session.query(Session.id)
                .filter(Session.pack_id == pack.id)
                .all()
            )
        ]

        notification_filter = ReaderNotification.pack_id == pack.id
        if session_ids:
            notification_filter = or_(
                ReaderNotification.pack_id == pack.id,
                ReaderNotification.session_id.in_(session_ids)
            )
            Chat.query.filter(Chat.session_id.in_(session_ids)).delete(synchronize_session=False)
            Session_quiz.query.filter(Session_quiz.session_id.in_(session_ids)).delete(synchronize_session=False)
            Follow_session.query.filter(Follow_session.session_id.in_(session_ids)).delete(synchronize_session=False)

        ReaderNotification.query.filter(notification_filter).delete(synchronize_session=False)
        Follow_book.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        Follow_pack.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        Book_pack.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        Code.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        SchoolPackInstance.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        Session.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        Unit.query.filter_by(pack_id=pack.id).delete(synchronize_session=False)
        db.session.delete(pack)
        db.session.commit()

        return jsonify({
            'message': 'Pack is successfully deleted',
            'impact': impact
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to delete pack: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500
        


@admin.route('/update_pack_details', methods=['POST'])
@login_required
@admin_or_assistant_required
def update_pack_details():
    try:
        data = request.json
        
        pack_token = data['id']
    
        pack_to_update = get_school_pack(pack_token)
        
        if not pack_to_update:
            return jsonify({'message': 'Pack not found'}), 404
        
        if 'title' in data:
            new_title = data['title']
            # Check if the new title is an empty string or if it's already in use by another pack
            if not new_title.strip():
                return jsonify({'message': 'Title cannot be empty'}), 400
            elif Pack.query.filter(Pack.title == new_title, Pack.shcool_id == pack_to_update.shcool_id, Pack.id != pack_token).first():
                return jsonify({'message': 'Title is already in use by another pack'}), 400
            pack_to_update.title = new_title
        
        if 'level' in data:
            new_level = data['level']
            if not new_level.strip():
                return jsonify({'message': 'Level cannot be empty'}), 400
            pack_to_update.level = new_level
            
        pack_to_update.duration= data['duration'] if 'duration' in data else pack_to_update.duration
        pack_to_update.img = data['img'] if 'img' in data else pack_to_update.img
        pack_to_update.price = data['price'] if 'price' in data else pack_to_update.price
        pack_to_update.discount = data['discount'] if 'discount' in data else pack_to_update.discount
        pack_to_update.faq= data['faq'] if 'faq' in data else pack_to_update.faq
        pack_to_update.age = data['age'] if 'age' in data else pack_to_update.age.value
        pack_to_update.desc = data['desc'] if 'desc' in data else pack_to_update.desc
        pack_to_update.duration = data['duration'] if 'duration' in data else pack_to_update.duration 
        pack_to_update.public = data['public'] if 'public' in data else pack_to_update.public 

        
        db.session.commit()
        
        pack_data = {
            'id': pack_to_update.id,
            'title': pack_to_update.title,
            'level': pack_to_update.level,
            'img': pack_to_update.img,
            'age': pack_to_update.age.value,
            'price': pack_to_update.price,
            'discount': pack_to_update.discount,
            'desc': pack_to_update.desc,
            'book_number': pack_to_update.book_number,
            'faq' : pack_to_update.faq,
            'duration':pack_to_update.duration,
            'public':pack_to_update.public 
        }

        return jsonify({'message': 'Pack details updated successfully', 'pack': pack_data}), 200
    except Exception as e:
        return jsonify({'message': 'An error occurred', 'error': str(e)}), 500

    
    
@admin.route('/show_all_teacher_postulate')
@login_required
@admin_required
def show_all_teacher_postulate():
    try:
        teacher_postulates=Teacher_postulate.query.all()
        teacher_submits=[]

        for teacher_submit in teacher_postulates:
            teacher_submits.append({
            'username': User.query.filter_by(id=teacher_submit.id).first().username or None,
            'email': User.query.filter_by(id=teacher_submit.id).first().email or None,
            'description' :teacher_submit.description,
            'study_level': teacher_submit.study_level,
            'selected' : teacher_submit.selected
        })

        return jsonify({'teacher_submits':teacher_submits}),200
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/accept_teacher_job',methods=['POST'])
@login_required
@admin_required
def accept_teacher_job():
    try:
        email=request.json['email']
        reader =Reader.query.filter_by(email=email).first()
        if reader:
            teacher_postulate=Teacher_postulate.query.filter_by(id=reader.id).first()
            if teacher_postulate:
                db.session.delete(teacher_postulate)
                db.session.commit()
                db.session.delete(reader)
                db.session.commit()
                new_teacher=Teacher(id=reader.id,username=reader.username,email=reader.email,password_hashed=reader.password_hashed,created_at=reader.created_at,confirmed=True,description=teacher_postulate.description,study_level=teacher_postulate.study_level)
                db.session.add(new_teacher)
                db.session.commit()

                return jsonify({'message':'Switched to teacher successfully'}),200
            else:
                return jsonify({'message':'The user hadn\'t postulate to teacher job'}),404
        else:
            return jsonify({'message':'Invalid email or already switched to teacher'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/reject_teacher_job',methods=['POST'])
@login_required
@admin_required
def reject_teacher_role():
    try:
        email=request.json['email']
        reader=Reader.query.filter_by(email=email).first()
        if reader:
            teacher_postulate=Teacher_postulate.query.filter_by(id=reader.id).first()
            if teacher_postulate:
                db.session.delete(teacher_postulate)
                db.session.commit()
                return jsonify({'message':'Teacher job rejected successfully'}),200
            else:
                return jsonify({'message':'The user hadn\'t postulate to teacher job'}),404
        else:
            return jsonify({'message':'Invalid email ,any reader matched'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500
        

@admin.route('/revoke_teacher_role',methods=['POST'])
@login_required
@admin_required
def revoke_teacher_role():
    try:
        email=request.json['email']
        teacher=Teacher.query.filter_by(email=email).first()

        if teacher:
            reader=Reader(id=teacher.id,username=teacher.username,email=teacher.email,password_hashed=teacher.password_hashed,confirmed=True,created_at=teacher.created_at)
            db.session.delete(teacher)
            db.session.commit()
            db.session.add(reader)
            db.session.commit()
            return jsonify({'message':'Teacher role\'s revoked successfully'}),200
        else:
            return jsonify({'message':'Invalid email'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/show_pack_follow_requests')
@login_required
@admin_or_assistant_required
def show_pack_follow_requests():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        school_user_ids = get_school_user_ids_for_school(school_id)
        pack_follow_requests = (
            db.session.query(Follow_pack)
            .join(Pack, Follow_pack.pack_id == Pack.id)
            .outerjoin(
                SchoolPackInstance,
                and_(
                    SchoolPackInstance.pack_id == Pack.id,
                    SchoolPackInstance.shcool_id == school_id,
                    SchoolPackInstance.active.is_(True)
                )
            )
            .filter(
                Follow_pack.user_id.in_(school_user_ids) if school_user_ids else False,
                Pack.active.is_(True),
                or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None))
            )
            .all()
        )
        
        all_packs = []
        for follow_request in pack_follow_requests:
            pack = get_school_accessible_pack(follow_request.pack_id)
            user_info = User.query.filter_by(id=follow_request.user_id).first()
            if pack :
                all_packs.append({
                    'pack_id': pack.id,
                    'pack_title': pack.title,
                    'source': 'global' if is_global_pack(pack) else 'school',
                    'read_only': is_global_pack(pack),
                    'user_id': user_info.id,
                    'username': user_info.username,
                    'email': user_info.email,
                    'approved':follow_request.approved
                     })

        return jsonify({'pack_follow_requests': all_packs}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
# Define a new route to approve follow requests.
@admin.route('/approve_pack_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def approve_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400
        if not get_school_accessible_pack(pack_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Pack or user not found'}), 404

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = True
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        pack = Pack.query.get(pack_id)
        if pack:
            commit_notification_event(notify_pack_follow_approved, pack, user_id)

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

 # Define a new route to approve follow requests.
@admin.route('/reject_pack_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def reject_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400
        if not get_school_accessible_pack(pack_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Pack or user not found'}), 404

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = False
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500       

# Define a route to delete a follow request.
@admin.route('/delete_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400
        if not get_school_accessible_pack(pack_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Pack or user not found'}), 404

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Delete the follow request.
        db.session.delete(follow_request)
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request deleted'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

#create follow pack 
@admin.route('/create_follow_pack', methods=['POST'])
@login_required
@admin_or_assistant_required
def create_follow_pack():
    try:
        pack_id = request.json.get('pack_id')
        user_id = request.json.get('user_id')

        if not pack_id or not user_id:
            return jsonify({'message': 'Pack ID and User ID are required'}), 400

        # Find the pack
        pack = get_school_accessible_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        if not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'User not found'}), 404

        # Check if the user already follows the pack
        existing_pack = Follow_pack.query.filter_by(user_id=user_id, pack_id=pack_id).first()
        if existing_pack:
            return jsonify({'message': 'You already follow this pack'}), 400

        # Refuse once the school is at its licensed reader limit. Inert until
        # SEAT_ENFORCEMENT_ENABLED is turned on.
        allowed, refusal = check_capacity(resolve_billing_school(pack, user_id), audience='admin')
        if not allowed:
            return jsonify({'message': refusal, 'code': 'SEAT_LIMIT_REACHED'}), 403

        # Add a new follow_pack record
        follow_pack_entry = Follow_pack(user_id=user_id, pack_id=pack_id, approved=True)
        db.session.add(follow_pack_entry)
        activate_seat(user_id, pack, source=SOURCE_ADMIN_ASSIGN)
        db.session.commit()

        followed_pack = {
            'approved': follow_pack_entry.approved,
            'id': pack.id,
            'level': pack.level,
            'book_number': pack.book_number,
            'price': pack.price,
            'title': pack.title,
            'source': 'global' if is_global_pack(pack) else 'school',
            'read_only': is_global_pack(pack)
        }

        return jsonify({'message': 'Pack successfully added to your pack list', 'followed_pack': followed_pack}), 200

    except Exception as e:
        print(f"Error: {e}")  # Log the error for debugging
        return jsonify({'message': 'Internal server error'}), 500




# Define a route to get follow requests by user and pack ID.
@admin.route('/get_one_pack_follow_requests', methods=['POST'])
@login_required
@admin_or_assistant_required
def get_one_pack_follow_requests():
    try:


        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400
        if not get_school_accessible_pack(pack_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Pack or user not found'}), 404

        # Find follow requests by pack_id and user_id.
        follow_requests = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).all()
        
        # Check if any follow requests exist.
        if not follow_requests:
            return jsonify({'message': 'No follow requests found for the specified user and pack'}), 404

        # Serialize the follow requests.
        all_requests = []
        for pack_request in follow_requests:

            pack = Pack.query.filter_by(id=pack_request.pack_id).first()
            user_info = User.query.filter_by(id=pack_request.user_id).first()
            all_requests.append({
                'pack_title': pack.title,
                'username': user_info.username,
                'email': user_info.email,
                'pack_id': pack_request.pack_id,
                'user_id': pack_request.user_id,
                'approved': pack_request.approved
            })

        return jsonify({'follow_requests': all_requests}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


#create follow session 
@admin.route('/create_follow_session', methods=['POST'])
@login_required
@admin_or_assistant_required
def create_follow_session():
    try:
        session_id = request.json.get('session_id')
        user_id = request.json.get('user_id')

        if not session_id or not user_id:
            return jsonify({'message': 'Session ID and User ID are required'}), 400

        session = get_school_accessible_session(session_id)
        if not session:
            return jsonify({'message': 'Session not found'}), 404
        user = get_school_user(user_id)
        if not user :
            return jsonify({'message': 'User not found'}), 404
            
        follow_pack = Follow_pack.query.filter_by(pack_id=session.pack_id, user_id=user_id).first()
        if not follow_pack or not follow_pack.approved:
            return jsonify({'message': 'No matching or approved Follow_pack found'}), 404

        follows_count = Follow_session.query.filter_by(session_id=session.id).count()
        if session.capacity <= follows_count:
            return jsonify({'message': 'Session is full'}), 404

        # Follow book if not already followed
        follow_book_exists = Follow_book.query.filter_by(
            user_id=user_id, book_id=session.book_id, pack_id=session.pack_id
        ).first()
        if not follow_book_exists:
            follow_book = Follow_book(user_id=user_id, book_id=session.book_id, pack_id=session.pack_id)
            db.session.add(follow_book)

        # Follow session
        follow = Follow_session(user_id=user_id, session_id=session_id, approved=True)
        db.session.add(follow)
        db.session.commit()
        

        followed_session= {
                    'session_id': session.id,
                    'session_name': session.name,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'approved':follow.approved
                     }
        return jsonify({'message': 'session has been created ','follow_session':followed_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500





@admin.route('/show_session_follow_requests')
@login_required
@admin_or_assistant_required
def show_session_follow_requests():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403
        school_user_ids = get_school_user_ids_for_school(school_id)
        session_follow_requests = (
            db.session.query(Follow_session)
            .join(Session, Follow_session.session_id == Session.id)
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
                Follow_session.user_id.in_(school_user_ids) if school_user_ids else False,
                Pack.active.is_(True),
                or_(Pack.shcool_id == school_id, SchoolPackInstance.id.isnot(None))
            )
            .all()
        )
        
        all_session = []
        for follow_request in session_follow_requests:
            session = get_school_accessible_session(follow_request.session_id)
            if not session:
                continue
            pack = get_school_accessible_pack(session.pack_id)
            user_info = User.query.filter_by(id=follow_request.user_id).first()
            if pack :
                
                all_session.append({
                    'session_id': session.id,
                    'session_name': session.name,
                    'pack_id': pack.id,
                    'pack_title': pack.title,
                    'source': 'global' if is_global_pack(pack) else 'school',
                    'user_id': user_info.id,
                    'username': user_info.username,
                    'email': user_info.email,
                    'approved':follow_request.approved
                     })
        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/approve_session_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def approve_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400
        if not get_school_accessible_session(session_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Session or user not found'}), 404

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = True
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        session_instance = Session.query.get(session_id)
        if session_instance:
            commit_notification_event(notify_session_follow_approved, session_instance, user_id)

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/reject_session_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def reject_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400
        if not get_school_accessible_session(session_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Session or user not found'}), 404

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = False
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
        
# Define a route to delete a follow request.
@admin.route('/delete_session_follow_request', methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400
        session = get_school_accessible_session(session_id)
        if not session or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Session or user not found'}), 404

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()
        book_follow = Follow_book.query.filter_by(book_id=session.book_id, user_id=user_id).first()
        
        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Delete the follow request.
        if book_follow :
            db.session.delete(book_follow)
        db.session.delete(follow_request)
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request deleted'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


# Define a route to get follow requests by user and session ID.
@admin.route('/get_one_session_follow_requests', methods=['POST'])
@login_required
@admin_or_assistant_required
def get_one_session_follow_requests():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400
        if not get_school_session(session_id) or not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'Session or user not found'}), 404

        # Find follow requests by session_id and user_id.
        follow_requests = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).all()

        # Check if any follow requests exist.
        if not follow_requests:
            return jsonify({'message': 'No follow requests found for the specified user and session'}), 404

        # Serialize the follow requests.
        all_requests = []
        for session_request in follow_requests:
            session = get_school_accessible_session(session_request.session_id)
            if not session:
                continue
            user_info = User.query.filter_by(id=session_request.user_id).first()
            all_requests.append({
                'username': user_info.username,
                'email': user_info.email,
                'session_name': session.name,
                'session_id': session_request.session_id,
                'user_id': session_request.user_id,
                'approved': session_request.approved
            })

        return jsonify({'follow_requests': all_requests}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/add_quiz_to_session', methods=['POST'])
@login_required
@admin_or_assistant_required
def add_quiz_to_session():
    try:
        # Get data from the request
        data = request.get_json()
        session_id = data['session_id']
        quiz_token = data['quiz_token']
        if not get_school_session(session_id):
            return jsonify({'message': 'Session not found'}), 404

        # Check if  the quiz already exists in the session
        if Session_quiz.query.filter_by(session_id=session_id, quiz_token=quiz_token).first():
            return jsonify({'message': 'This quiz is already exists in the session.'}), 409  # Conflict
        else:
            # Create a new session_quiz
            new_session_quiz = Session_quiz(
                session_id=session_id,
                quiz_token=quiz_token,
            )

            # Add the user to the database
            db.session.add(new_session_quiz)
            db.session.commit()

            # Return a success response
            response_data = {
                'message': 'Your Quiz has been successfully added.',
                'quiz_session': {
                    'session_id': session_id,
                    'quiz_token': quiz_token,
                    'id': new_session_quiz.id,
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/delete_quiz_from_session',methods=['POST'])
@login_required
@admin_or_assistant_required
def delete_quiz_from_session():
    try:
        session_id = request.json['session_id']
        quiz_token = request.json['quiz_token']
        if not get_school_session(session_id):
            return jsonify({'message': 'Session not found'}), 404

        quiz = Session_quiz.query.filter_by(session_id=session_id,quiz_token=quiz_token).first()
        
        if quiz:
            db.session.delete(quiz)
            db.session.commit()
            return jsonify({'message': 'Quiz deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid Quiz'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_quiz_in_session',methods=['POST'])
@login_required
@admin_or_assistant_required
def get_quiz_in_session():
    try:
        session_id = request.json['session_id']
        if not get_school_session(session_id):
            return jsonify({'message': 'Session not found'}), 404
        

        quizs = Session_quiz.query.filter_by(session_id=session_id).all()
        quiz_data=[]
        for quiz in quizs :
            quiz_data.append({
                'session_id': quiz.session_id,
                'quiz_token': quiz.quiz_token,
                'id': quiz.id,
            })
        return jsonify({
            'quizes': quiz_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500




# Get route to retrieve pack and its associated codes
@admin.route('/code_in_pack/<int:pack_id>', methods=['GET'])
def get_pack(pack_id):
    pack = get_school_pack(pack_id)
    if pack is not None:
        # Retrieve associated codes for the pack
        codes = Code.query.filter_by(pack_id=pack_id,status=StatusEnum.ACTIVE).all()
        pack_data = {
            "id": pack.id,
            "title": pack.title,
            "codes": [{"code": code.code, "status": code.status.value,'id':code.id,'pack_id':code.pack_id} for code in codes]
        }
        return jsonify(pack_data)
    else:
        return jsonify({"error": "Pack not found"}), 404
@admin.route('/delete_code/<int:code_id>', methods=['DELETE'])
def delete_code(code_id):
    code = get_school_code(code_id)

    if code is not None:
        db.session.delete(code)
        db.session.commit()
        return jsonify({"message": "Code deleted successfully"})
    else:
        return jsonify({"error": "Code not found"}), 404

def generate_unique_code(pack_id):
   
    characters = string.ascii_letters + string.digits  

  
    code_length = 8
    generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

  
    while Code.query.filter_by(pack_id=pack_id, code=generated_code).first() is not None:
    
        generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

    return generated_code

def generate_unique_school_invitation_code():
    characters = string.ascii_uppercase + string.digits
    code_length = 10
    generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

    while SchoolInvitationCode.query.filter_by(code=generated_code).first() is not None:
        generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

    return generated_code





@admin.route('/generate_code_in_pack/<int:pack_id>', methods=['POST'])
def generate_codes(pack_id):
    pack = get_school_pack(pack_id)
    if pack is not None:
        data = request.get_json()
        num_codes_to_generate = data.get('num_codes', 10) 
        generated_codes = []

        for _ in range(num_codes_to_generate):
       
            code = generate_unique_code(pack_id)
            
            new_code = Code(pack_id=pack_id, code=code)
            db.session.add(new_code)
            generated_codes.append(code)

        db.session.commit()
        return jsonify({"message": f"{num_codes_to_generate} codes generated successfully", "generated_codes": generated_codes})
    else:
        return jsonify({"error": "Pack not found"}), 404


# ---------------------------------------------------------------------------
# iRead-issued codes for GLOBAL packs (PRD §4). The school code endpoints above
# are scoped to school-owned packs (get_school_pack excludes is_global_pack), so
# global packs need their own super-admin code generation — the codes a B2C /
# school-less reader redeems to follow (and then read) an official iRead pack,
# exactly the way a student redeems a school code for a school pack.
# ---------------------------------------------------------------------------

def get_global_pack_for_codes(pack_id):
    return Pack.query.filter_by(id=pack_id, is_global_pack=True).first()


@admin.route('/super/global-packs/<int:pack_id>/codes', methods=['GET'])
def super_get_global_pack_codes(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    pack = get_global_pack_for_codes(pack_id)
    if pack is None:
        return jsonify({'message': 'Global pack not found'}), 404
    codes = Code.query.filter_by(pack_id=pack_id, status=StatusEnum.ACTIVE).all()
    return jsonify({
        'id': pack.id,
        'title': pack.title,
        'codes': [
            {'id': code.id, 'code': code.code, 'status': code.status.value, 'pack_id': code.pack_id}
            for code in codes
        ],
    }), 200


@admin.route('/super/global-packs/<int:pack_id>/codes', methods=['POST'])
def super_generate_global_pack_codes(pack_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    pack = get_global_pack_for_codes(pack_id)
    if pack is None:
        return jsonify({'message': 'Global pack not found'}), 404

    data = request.get_json() or {}
    try:
        num_codes = int(data.get('num_codes', 10))
    except (TypeError, ValueError):
        return jsonify({'message': 'num_codes must be a number'}), 400
    if num_codes < 1 or num_codes > 500:
        return jsonify({'message': 'num_codes must be between 1 and 500'}), 400

    generated_codes = []
    for _ in range(num_codes):
        code = generate_unique_code(pack_id)
        db.session.add(Code(pack_id=pack_id, code=code))
        generated_codes.append(code)
    db.session.commit()
    return jsonify({
        'message': f'{num_codes} codes generated successfully',
        'generated_codes': generated_codes,
    }), 200


@admin.route('/super/global-packs/codes/<int:code_id>', methods=['DELETE'])
def super_delete_global_pack_code(code_id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    code = Code.query.get(code_id)
    if code is None or get_global_pack_for_codes(code.pack_id) is None:
        return jsonify({'message': 'Code not found'}), 404
    db.session.delete(code)
    db.session.commit()
    return jsonify({'message': 'Code deleted successfully'}), 200

@admin.route('/update_code/<int:code_id>', methods=['PUT'])
def update_code_status(code_id):
    code = get_school_code(code_id)
    if code is not None:
        data = request.get_json()
        new_status = data.get('status')
        
        # Check if the provided status is valid
        if new_status in [status.value for status in StatusEnum]:
            code.status = StatusEnum(new_status)
            db.session.commit()
            return jsonify({"message": f"Code status updated to {new_status}"})
        else:
            return jsonify({"error": "Invalid status provided"}), 400
    else:
        return jsonify({"error": "Code not found"}), 404

@admin.route('/get_code/<string:code_client>', methods=['GET'])
def get_code(code_client):
    try:
        print(code_client)
        code = get_school_code_by_value(code_client)

        if code:  
            code_data = {
                "id": code.id,
                "code": code.code,
                "user_id": code.user_id,
                "pack_id": code.pack_id,
                "status":code.status.value
            }
            return jsonify({"code": code_data})
        else:
            return jsonify({"error": "Code not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin.route('/generate_school_invitation_code', methods=['POST'])
def generate_school_invitation_code():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        data = request.get_json(silent=True) or {}
        requested_code = data.get('code')
        max_uses = data.get('max_uses')

        if max_uses in ('', None):
            max_uses = None
        else:
            try:
                max_uses = int(max_uses)
            except (TypeError, ValueError):
                return jsonify({'message': 'max_uses must be a number'}), 400
            if max_uses < 1:
                return jsonify({'message': 'max_uses must be greater than 0'}), 400

        if requested_code:
            code = str(requested_code).strip().upper()
            if not code:
                return jsonify({'message': 'Invitation code is required'}), 400
            if len(code) > 64:
                return jsonify({'message': 'Invitation code is too long'}), 400
            if SchoolInvitationCode.query.filter_by(code=code).first():
                return jsonify({'message': 'Invitation code already exists'}), 409
        else:
            code = generate_unique_school_invitation_code()

        invitation_code = SchoolInvitationCode(
            shcool_id=school_id,
            code=code,
            max_uses=max_uses,
            created_by=current_user.id
        )
        db.session.add(invitation_code)
        db.session.commit()

        return jsonify({
            'message': 'School invitation code generated successfully',
            'invitation_code': serialize_school_invitation_code(invitation_code)
        }), 201
    except Exception as e:
        return jsonify({'message': 'Internal server error', 'error': str(e)}), 500

@admin.route('/school_invitation_codes', methods=['GET'])
def get_school_invitation_codes():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        invitation_codes = SchoolInvitationCode.query.filter_by(shcool_id=school_id).order_by(SchoolInvitationCode.id.desc()).all()
        return jsonify({
            'invitation_codes': [serialize_school_invitation_code(invitation_code) for invitation_code in invitation_codes]
        }), 200
    except Exception as e:
        return jsonify({'message': 'Internal server error', 'error': str(e)}), 500

@admin.route('/school_invitation_code/<int:invitation_code_id>', methods=['PUT'])
def update_school_invitation_code(invitation_code_id):
    try:
        invitation_code = get_school_invitation_code(invitation_code_id)
        if not invitation_code:
            return jsonify({'message': 'Invitation code not found'}), 404

        data = request.get_json(silent=True) or {}

        if 'active' in data:
            active = data.get('active')
            if isinstance(active, bool):
                invitation_code.active = active
            elif str(active).lower() in ['true', '1', 'yes']:
                invitation_code.active = True
            elif str(active).lower() in ['false', '0', 'no']:
                invitation_code.active = False
            else:
                return jsonify({'message': 'active must be true or false'}), 400

        if 'max_uses' in data:
            max_uses = data.get('max_uses')
            if max_uses in ('', None):
                invitation_code.max_uses = None
            else:
                try:
                    max_uses = int(max_uses)
                except (TypeError, ValueError):
                    return jsonify({'message': 'max_uses must be a number'}), 400
                if max_uses < 1:
                    return jsonify({'message': 'max_uses must be greater than 0'}), 400
                if max_uses < invitation_code.used_count:
                    return jsonify({'message': 'max_uses cannot be lower than used_count'}), 400
                invitation_code.max_uses = max_uses

        db.session.commit()

        return jsonify({
            'message': 'School invitation code updated successfully',
            'invitation_code': serialize_school_invitation_code(invitation_code)
        }), 200
    except Exception as e:
        return jsonify({'message': 'Internal server error', 'error': str(e)}), 500

@admin.route('/school_invitation_code/<int:invitation_code_id>', methods=['DELETE'])
def delete_school_invitation_code(invitation_code_id):
    try:
        invitation_code = get_school_invitation_code(invitation_code_id)
        if not invitation_code:
            return jsonify({'message': 'Invitation code not found'}), 404

        db.session.delete(invitation_code)
        db.session.commit()

        return jsonify({'message': 'School invitation code deleted successfully'}), 200
    except Exception as e:
        return jsonify({'message': 'Internal server error', 'error': str(e)}), 500

@admin.route('/get_all_logs', methods=['GET'])
def get_all_logs():
   
    try:
        # Query the UserLog table to get all logs
        school_user_ids = get_current_school_user_ids()
        user_logs = UserLog.query.filter(UserLog.user_id.in_(school_user_ids)).all() if school_user_ids else []

        # Create a list to store log data
        logs = []

        # Iterate through user logs
        for log in user_logs:
            log_data = {
                'id': log.id,
                'user_agent': log.user_agent,
                'user_ip': log.user_ip,
                'referer': log.referer,
                'user_country': log.user_country,
                'user_city': log.user_city,
                'user_id':log.user_id,
                'visit_duration':log.visit_duration,
                'browser':log.browser,
                'system':log.system
            }

            # Check if user_id is not None in the UserLog
            if log.user_id:
                user = User.query.get(log.user_id)
                if user:
                    log_data['user_email'] = user.email

            logs.append(log_data)

        return jsonify({'logs': logs}), 200
    except Exception as error:
        return jsonify({'message': 'Error retrieving logs', 'error': str(error)}), 500

@admin.route('/get_dashboard_analytics', methods=['GET'])
def get_dashboard_admin():
    try:
        school_user_ids = get_current_school_user_ids()
        user_logs = UserLog.query.filter(UserLog.user_id.in_(school_user_ids)).all() if school_user_ids else []
        users = User.query.filter(User.id.in_(school_user_ids)).all() if school_user_ids else []
        user_counts = [0] * 12
        log_counts = [0] * 12
        visit_duration_count = [0] * 12
        total_visit_duration = 0
        browser_counts = {}
        country_counts ={}
        system_counts ={}

        for user in users:
            month = user.created_at.month
            user_counts[month - 1] += 1
        for log in user_logs:
            month = log.created_at.month
            log_counts[month - 1] += 1
            total_visit_duration += log.visit_duration
            visit_duration_count[month - 1] += round(log.visit_duration / 60)

            # Update browser counts
            if log.browser in browser_counts:
                browser_counts[log.browser] += 1
            else:
                browser_counts[log.browser] = 1
            if log.user_country in country_counts :
                country_counts[log.user_country]+=1  
            else :
                  country_counts[log.user_country]=1 
            if log.system in system_counts :
                system_counts[log.system]+=1  
            else :
                  system_counts[log.system]=1



        total_users = sum(user_counts)
        total_logs = sum(log_counts)
        total_duration = sum(visit_duration_count) *60
        average_visit_duration =( total_visit_duration / total_logs ) if total_logs > 0 else 0

        # Calculate browser percentages
        total_browser_logs = sum(browser_counts.values())
        browser_percentages = [{'browser': browser, 'percent': round(count / total_browser_logs * 100),'users':count} for browser, count in
                               browser_counts.items()]
        

        # Calculate country percentages
        total_country_logs = sum(country_counts.values())
        country_percentages = [{'country': country, 'percent': round(count / total_country_logs * 100),'users':count} for country, count in
                               country_counts.items()]   

        # Calculate system percentages
        total_system_logs = sum(system_counts.values())
        system_percentages = [{'system': system, 'percent': round(count / total_system_logs * 100),'users':count} for system, count in
                               system_counts.items()]   
        


       
        result = {
            'users': user_counts,
            'vistors': log_counts,
            "userCount": total_users,
            "vistorCount": total_logs,
            'averageVisitDuration': average_visit_duration ,
            "totalVisitDuration": total_duration,
            "duration": visit_duration_count,
            "browsers": browser_percentages,
            "users_by_country":country_percentages,
            "operating_system" :system_percentages

        }

        return jsonify(result)

    except Exception as error:
        return jsonify({'message': 'Error retrieving logs', 'error': str(error)}), 500


## @brief Reading-domain dashboard helpers (school-admin Overview/Analytics pages).
#
# Resolves a `range` query param into a (period_start, period_end, bucket_granularity, range_key) tuple.
def resolve_dashboard_range(range_param):
    now = datetime.now()
    range_key = (range_param or '30d').strip().lower()
    if range_key == '3m':
        start = now - timedelta(days=90)
        granularity = 'week'
    elif range_key == '12m':
        start = now - timedelta(days=365)
        granularity = 'month'
    else:
        range_key = '30d'
        start = now - timedelta(days=30)
        granularity = 'day'
    return start, now, granularity, range_key


## @brief Builds an ordered list of (bucket_start, bucket_end, label) tuples covering [start, end].
def bucket_dates(start, end, granularity):
    buckets = []
    if granularity == 'day':
        cursor = datetime(start.year, start.month, start.day)
        end_day = datetime(end.year, end.month, end.day)
        while cursor <= end_day:
            bucket_end = cursor + timedelta(days=1)
            buckets.append((cursor, bucket_end, cursor.strftime('%b %d')))
            cursor = bucket_end
    elif granularity == 'week':
        cursor = datetime(start.year, start.month, start.day)
        end_boundary = datetime(end.year, end.month, end.day) + timedelta(days=1)
        while cursor < end_boundary:
            bucket_end = cursor + timedelta(days=7)
            buckets.append((cursor, bucket_end, cursor.strftime('%b %d')))
            cursor = bucket_end
    else:
        cursor_year, cursor_month = start.year, start.month
        end_year, end_month = end.year, end.month
        while (cursor_year, cursor_month) <= (end_year, end_month):
            bucket_start = datetime(cursor_year, cursor_month, 1)
            if cursor_month == 12:
                next_year, next_month = cursor_year + 1, 1
            else:
                next_year, next_month = cursor_year, cursor_month + 1
            bucket_end = datetime(next_year, next_month, 1)
            buckets.append((bucket_start, bucket_end, bucket_start.strftime('%b %Y')))
            cursor_year, cursor_month = next_year, next_month
    return buckets


## @brief Counts rows into buckets produced by bucket_dates(), using date_getter(row) to locate each row.
def count_in_buckets(rows, date_getter, buckets):
    counts = [0] * len(buckets)
    for row in rows:
        value = date_getter(row)
        if value is None:
            continue
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime(value.year, value.month, value.day)
        for index, (bucket_start, bucket_end, _label) in enumerate(buckets):
            if bucket_start <= value < bucket_end:
                counts[index] += 1
                break
    return counts


GAME_DISPLAY_LABELS = {
    'BEE': 'Bee Genius',
    'WORDEXPLORER': 'Word Explorer',
    'THINKWORD': 'Think Word',
    'INTELLECTLNK': 'Intellect Link'
}
GAME_DISPLAY_ORDER = ['BEE', 'WORDEXPLORER', 'THINKWORD', 'INTELLECTLNK']


## @brief School-admin Overview page: KPI snapshot, 6-month trend, top packs, recent activity feed.
@admin.route('/dashboard/overview-summary', methods=['GET'])
def get_dashboard_overview_summary():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school_user_ids = get_current_school_user_ids()
        now = datetime.now()

        readers_query = User.query.filter(User.id.in_(school_user_ids), User.type == 'reader')
        readers_total = readers_query.count()
        readers_approved = readers_query.filter(User.approved.is_(True)).count()
        readers_pending = readers_total - readers_approved

        teachers_query = Teacher.query.filter(Teacher.id.in_(school_user_ids))
        teachers_total = teachers_query.count()
        teachers_approved = teachers_query.filter(Teacher.approved.is_(True)).count()
        teachers_available = teachers_query.filter(Teacher.available.is_(True)).count()

        pending_packs = Follow_pack.query.filter(
            Follow_pack.user_id.in_(school_user_ids),
            Follow_pack.approved.is_(False)
        ).count()
        pending_teachers = User.query.filter(
            User.id.in_(school_user_ids), User.type == 'teacher', User.approved.is_(False)
        ).count()

        books_own = Book.query.filter_by(shcool_id=school_id, active=True).count()
        books_adopted = SchoolBookInstance.query.filter_by(shcool_id=school_id, active=True).count()
        packs_own = Pack.query.filter_by(shcool_id=school_id, active=True).count()
        packs_adopted = SchoolPackInstance.query.filter_by(shcool_id=school_id, active=True).count()

        # Trailing 6 calendar months, independent of any period selector.
        trend_year, trend_month = now.year, now.month
        for _ in range(5):
            if trend_month == 1:
                trend_year -= 1
                trend_month = 12
            else:
                trend_month -= 1
        trend_start = datetime(trend_year, trend_month, 1)
        month_buckets = bucket_dates(trend_start, now, 'month')

        new_reader_rows = User.query.filter(
            User.id.in_(school_user_ids), User.type == 'reader', User.created_at >= trend_start.date()
        ).with_entities(User.created_at).all()
        new_readers_trend = count_in_buckets(new_reader_rows, lambda r: r.created_at, month_buckets)

        session_rows = school_accessible_session_query().filter(
            Session.start_date >= trend_start, Session.start_date <= now
        ).with_entities(Session.start_date).all()
        sessions_held_trend = count_in_buckets(session_rows, lambda r: r.start_date, month_buckets)

        completed_story_rows = ReaderStoryProgress.query.filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.completed.is_(True),
            ReaderStoryProgress.completed_at >= trend_start
        ).with_entities(ReaderStoryProgress.completed_at).all()
        stories_completed_trend = count_in_buckets(completed_story_rows, lambda r: r.completed_at, month_buckets)

        accessible_pack_ids_subquery = school_accessible_pack_query().with_entities(Pack.id).subquery()
        top_pack_rows = (
            db.session.query(
                Pack.id,
                Pack.title,
                Pack.is_global_pack,
                func.count(Follow_pack.user_id).label('followers'),
                func.sum(case((Follow_pack.approved.is_(True), 1), else_=0)).label('approved_count')
            )
            .select_from(Pack)
            .outerjoin(Follow_pack, and_(
                Follow_pack.pack_id == Pack.id,
                Follow_pack.user_id.in_(school_user_ids)
            ))
            .filter(Pack.id.in_(accessible_pack_ids_subquery))
            .group_by(Pack.id)
            .order_by(func.count(Follow_pack.user_id).desc())
            .limit(5)
            .all()
        )
        top_packs = []
        for row in top_pack_rows:
            followers = row.followers or 0
            approved_count = int(row.approved_count or 0)
            top_packs.append({
                'id': row.id,
                'title': row.title,
                'source': 'global' if row.is_global_pack else 'school',
                'followers': followers,
                'approved': approved_count,
                'pending': followers - approved_count
            })

        recent_readers = User.query.filter(
            User.id.in_(school_user_ids), User.type == 'reader'
        ).order_by(User.created_at.desc()).limit(8).all()
        recent_reader_events = [{
            'type': 'new_reader',
            'label': f'{user.username} joined as a reader',
            'timestamp': user.created_at.isoformat(),
            'ref_id': user.id
        } for user in recent_readers if user.created_at]

        recent_completion_rows = (
            db.session.query(ReaderStoryProgress, User, BookStory)
            .join(User, User.id == ReaderStoryProgress.user_id)
            .join(BookStory, BookStory.id == ReaderStoryProgress.story_id)
            .filter(
                ReaderStoryProgress.user_id.in_(school_user_ids),
                ReaderStoryProgress.completed.is_(True),
                ReaderStoryProgress.completed_at.isnot(None)
            )
            .order_by(ReaderStoryProgress.completed_at.desc())
            .limit(8)
            .all()
        )
        recent_completion_events = [{
            'type': 'story_completed',
            'label': f'{user.username} finished "{story.title}"',
            'timestamp': progress.completed_at.isoformat(),
            'ref_id': story.id
        } for progress, user, story in recent_completion_rows]

        recent_session_rows = (
            school_accessible_session_query()
            .filter(Session.start_date <= now)
            .order_by(Session.start_date.desc())
            .limit(8)
            .all()
        )
        recent_session_events = [{
            'type': 'session_held',
            'label': f'Session "{session.name}" took place',
            'timestamp': session.start_date.isoformat(),
            'ref_id': session.id
        } for session in recent_session_rows]

        recent_activity = sorted(
            recent_reader_events + recent_completion_events + recent_session_events,
            key=lambda event: event['timestamp'],
            reverse=True
        )[:8]

        result = {
            'readers': {'total': readers_total, 'approved': readers_approved, 'pending': readers_pending},
            'teachers': {'total': teachers_total, 'approved': teachers_approved, 'available': teachers_available},
            'pending_approvals': {
                'packs': pending_packs,
                'teachers': pending_teachers,
                'total': pending_packs + pending_teachers
            },
            'catalog': {
                'books_total': books_own + books_adopted,
                'books_own': books_own,
                'books_adopted': books_adopted,
                'packs_total': packs_own + packs_adopted,
                'packs_own': packs_own,
                'packs_adopted': packs_adopted
            },
            'trend': {
                'months': [label for (_s, _e, label) in month_buckets],
                'new_readers': new_readers_trend,
                'sessions_held': sessions_held_trend,
                'stories_completed': stories_completed_trend
            },
            'top_packs': top_packs,
            'recent_activity': recent_activity
        }
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'message': 'Error retrieving dashboard overview', 'error': str(error)}), 500


## @brief School-admin Analytics page: reader growth, reading activity, sessions, packs, games — time-bound by `range`.
@admin.route('/dashboard/reading-analytics', methods=['GET'])
def get_dashboard_reading_analytics():
    try:
        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school_user_ids = get_current_school_user_ids()
        period_start, period_end, granularity, range_key = resolve_dashboard_range(request.args.get('range'))
        buckets = bucket_dates(period_start, period_end, granularity)
        bucket_labels = [label for (_s, _e, label) in buckets]

        accessible_session_ids_subquery = school_accessible_session_query().with_entities(Session.id).subquery()
        reader_ids = [r.id for r in User.query.filter(
            User.id.in_(school_user_ids), User.type == 'reader'
        ).with_entities(User.id).all()]

        # ---- Section A: reader growth & engagement ----
        new_readers = User.query.filter(
            User.id.in_(school_user_ids), User.type == 'reader',
            User.created_at >= period_start.date(), User.created_at <= period_end.date()
        ).count()

        active_via_sessions = set(r[0] for r in db.session.query(Follow_session.user_id)
            .join(Session, Session.id == Follow_session.session_id)
            .filter(
                Follow_session.user_id.in_(reader_ids),
                Follow_session.presence.is_(True),
                Session.start_date >= period_start, Session.start_date <= period_end
            ).distinct().all()) if reader_ids else set()

        active_via_stories = set(r[0] for r in db.session.query(ReaderStoryProgress.user_id)
            .filter(
                ReaderStoryProgress.user_id.in_(reader_ids),
                ReaderStoryProgress.last_read_at >= period_start,
                ReaderStoryProgress.last_read_at <= period_end
            ).distinct().all()) if reader_ids else set()

        active_via_games = set(r[0] for r in db.session.query(Game_result.user_id)
            .filter(
                Game_result.user_id.in_(reader_ids),
                Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
            ).distinct().all()) if reader_ids else set()

        active_reader_ids = active_via_sessions | active_via_stories | active_via_games
        active_readers_rate = (len(active_reader_ids) / len(reader_ids) * 100) if reader_ids else 0.0

        total_follow_session_rows = (
            Follow_session.query
            .join(Session, Session.id == Follow_session.session_id)
            .filter(
                Follow_session.user_id.in_(reader_ids),
                Session.start_date >= period_start, Session.start_date <= period_end
            ).count()
        ) if reader_ids else 0
        avg_sessions_per_reader = (total_follow_session_rows / len(reader_ids)) if reader_ids else 0.0

        signup_rows = User.query.filter(
            User.id.in_(school_user_ids), User.type == 'reader',
            User.created_at >= period_start.date(), User.created_at <= period_end.date()
        ).with_entities(User.created_at).all()
        signups_over_time = count_in_buckets(signup_rows, lambda r: r.created_at, buckets)

        # ---- Section B: reading activity ----
        stories_completed = ReaderStoryProgress.query.filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.completed.is_(True),
            ReaderStoryProgress.completed_at >= period_start, ReaderStoryProgress.completed_at <= period_end
        ).count()

        stories_started = ReaderStoryProgress.query.filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.last_read_at >= period_start, ReaderStoryProgress.last_read_at <= period_end
        ).count()
        completion_rate = (stories_completed / stories_started * 100) if stories_started else 0.0

        books_actively_read = db.session.query(func.count(func.distinct(BookStory.book_id))).select_from(BookStory).join(
            ReaderStoryProgress, ReaderStoryProgress.story_id == BookStory.id
        ).filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.last_read_at >= period_start, ReaderStoryProgress.last_read_at <= period_end
        ).scalar() or 0

        stories_month_buckets = bucket_dates(period_start, period_end, 'month')
        started_rows = ReaderStoryProgress.query.filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.last_read_at >= period_start, ReaderStoryProgress.last_read_at <= period_end
        ).with_entities(ReaderStoryProgress.last_read_at).all()
        completed_rows = ReaderStoryProgress.query.filter(
            ReaderStoryProgress.user_id.in_(school_user_ids),
            ReaderStoryProgress.completed.is_(True),
            ReaderStoryProgress.completed_at >= period_start, ReaderStoryProgress.completed_at <= period_end
        ).with_entities(ReaderStoryProgress.completed_at).all()
        stories_started_series = count_in_buckets(started_rows, lambda r: r.last_read_at, stories_month_buckets)
        stories_completed_series = count_in_buckets(completed_rows, lambda r: r.completed_at, stories_month_buckets)

        top_book_rows = (
            db.session.query(
                Book.id,
                Book.title,
                func.count(func.distinct(ReaderStoryProgress.user_id)).label('readers'),
                func.sum(case((ReaderStoryProgress.completed.is_(True), 1), else_=0)).label('completed_count'),
                func.count(ReaderStoryProgress.story_id).label('progress_rows')
            )
            .join(BookStory, BookStory.book_id == Book.id)
            .join(ReaderStoryProgress, ReaderStoryProgress.story_id == BookStory.id)
            .filter(ReaderStoryProgress.user_id.in_(school_user_ids))
            .group_by(Book.id)
            .order_by(func.count(func.distinct(ReaderStoryProgress.user_id)).desc())
            .limit(10)
            .all()
        )
        top_books = []
        for row in top_book_rows:
            progress_rows = row.progress_rows or 0
            completed_count = int(row.completed_count or 0)
            top_books.append({
                'id': row.id,
                'title': row.title,
                'readers': row.readers or 0,
                'completion_rate': round(completed_count / progress_rows * 100, 1) if progress_rows else 0.0
            })

        quizzes_scheduled = Session_quiz.query.filter(
            Session_quiz.session_id.in_(accessible_session_ids_subquery),
            Session_quiz.release_date >= period_start.date(), Session_quiz.release_date <= period_end.date()
        ).count()

        # ---- Section C: sessions & attendance ----
        sessions_held = school_accessible_session_query().filter(
            Session.start_date >= period_start, Session.start_date <= period_end
        ).count()

        def attendance_ratios(extra_filter=None):
            query = (
                db.session.query(
                    Session.id,
                    func.sum(case((Follow_session.approved.is_(True), 1), else_=0)).label('approved_count'),
                    func.sum(case((and_(
                        Follow_session.approved.is_(True), Follow_session.presence.is_(True)
                    ), 1), else_=0)).label('present_count')
                )
                .select_from(Session)
                .outerjoin(Follow_session, Follow_session.session_id == Session.id)
                .filter(
                    Session.id.in_(accessible_session_ids_subquery),
                    Session.start_date >= period_start, Session.start_date <= period_end
                )
            )
            if extra_filter is not None:
                query = query.filter(extra_filter)
            rows = query.group_by(Session.id).all()
            return [row.present_count / row.approved_count for row in rows if row.approved_count]

        session_ratios = attendance_ratios()
        avg_attendance_rate = (sum(session_ratios) / len(session_ratios) * 100) if session_ratios else 0.0

        upcoming_sessions = school_accessible_session_query().filter(Session.start_date > period_end).count()

        sessions_per_month_buckets = bucket_dates(period_start, period_end, 'month')
        online_rows = school_accessible_session_query().filter(
            Session.location == Location.ONLINE,
            Session.start_date >= period_start, Session.start_date <= period_end
        ).with_entities(Session.start_date).all()
        classroom_rows = school_accessible_session_query().filter(
            Session.location == Location.CLASSROOM,
            Session.start_date >= period_start, Session.start_date <= period_end
        ).with_entities(Session.start_date).all()
        sessions_online_series = count_in_buckets(online_rows, lambda r: r.start_date, sessions_per_month_buckets)
        sessions_classroom_series = count_in_buckets(classroom_rows, lambda r: r.start_date, sessions_per_month_buckets)

        teacher_rows = (
            db.session.query(
                Teacher.id,
                Teacher.username.label('teacher_name'),
                func.count(func.distinct(Session.id)).label('sessions_count')
            )
            .select_from(Teacher)
            .join(Session, Session.teacher_id == Teacher.id)
            .filter(
                Session.id.in_(accessible_session_ids_subquery),
                Session.start_date >= period_start, Session.start_date <= period_end
            )
            .group_by(Teacher.id, Teacher.username)
            .order_by(func.count(func.distinct(Session.id)).desc())
            .all()
        )
        teacher_activity = []
        for row in teacher_rows:
            ratios = attendance_ratios(Session.teacher_id == row.id)
            avg_rate = (sum(ratios) / len(ratios) * 100) if ratios else 0.0
            teacher_activity.append({
                'id': row.id,
                'name': row.teacher_name,
                'sessions': row.sessions_count,
                'avg_attendance_rate': round(avg_rate, 1)
            })

        # ---- Section D: pack adoption & approvals ----
        accessible_pack_ids_subquery = school_accessible_pack_query().with_entities(Pack.id).subquery()
        pack_rows = (
            db.session.query(
                Pack.id,
                Pack.title,
                func.count(Follow_pack.user_id).label('followers'),
                func.sum(case((Follow_pack.approved.is_(True), 1), else_=0)).label('approved_count')
            )
            .select_from(Pack)
            .outerjoin(Follow_pack, and_(
                Follow_pack.pack_id == Pack.id,
                Follow_pack.user_id.in_(school_user_ids)
            ))
            .filter(Pack.id.in_(accessible_pack_ids_subquery))
            .group_by(Pack.id)
            .order_by(func.count(Follow_pack.user_id).desc())
            .limit(10)
            .all()
        )
        section_d_top_packs = []
        for row in pack_rows:
            followers = row.followers or 0
            approved_count = int(row.approved_count or 0)
            section_d_top_packs.append({
                'id': row.id,
                'title': row.title,
                'followers': followers,
                'approved': approved_count,
                'pending': followers - approved_count,
                'approval_rate': round(approved_count / followers * 100, 1) if followers else 0.0
            })

        invitation_codes = SchoolInvitationCode.query.filter_by(shcool_id=school_id).order_by(
            SchoolInvitationCode.id.desc()
        ).all()
        invitation_codes_payload = [serialize_school_invitation_code(code) for code in invitation_codes]

        # ---- Section E: games engagement ----
        total_plays = Game_result.query.filter(
            Game_result.user_id.in_(school_user_ids),
            Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
        ).count()

        try:
            total_words_learned = db.session.query(
                func.coalesce(func.sum(func.json_length(Game_result.words_learned)), 0)
            ).filter(
                Game_result.user_id.in_(school_user_ids),
                Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
            ).scalar()
        except Exception:
            db.session.rollback()
            word_rows = Game_result.query.filter(
                Game_result.user_id.in_(school_user_ids),
                Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
            ).with_entities(Game_result.words_learned).all()
            total_words_learned = sum(len(row.words_learned or []) for row in word_rows)

        avg_time_spent_seconds = db.session.query(func.avg(Game_result.time_spent_seconds)).filter(
            Game_result.user_id.in_(school_user_ids),
            Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
        ).scalar() or 0.0

        plays_by_type_rows = db.session.query(Game_result.game, func.count(Game_result.id)).filter(
            Game_result.user_id.in_(school_user_ids),
            Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
        ).group_by(Game_result.game).all()
        plays_by_type_counts = {game_enum.name: count for game_enum, count in plays_by_type_rows}
        plays_by_type = {
            'labels': [GAME_DISPLAY_LABELS[name] for name in GAME_DISPLAY_ORDER],
            'data': [plays_by_type_counts.get(name, 0) for name in GAME_DISPLAY_ORDER]
        }

        game_day_rows = Game_result.query.filter(
            Game_result.user_id.in_(school_user_ids),
            Game_result.day >= period_start.date(), Game_result.day <= period_end.date()
        ).with_entities(Game_result.day).all()
        plays_over_time_series = count_in_buckets(game_day_rows, lambda r: r.day, buckets)

        result = {
            'range': range_key,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'section_a_growth': {
                'new_readers': new_readers,
                'active_readers_rate': round(active_readers_rate, 1),
                'avg_sessions_per_reader': round(avg_sessions_per_reader, 2),
                'signups_over_time': {'labels': bucket_labels, 'data': signups_over_time}
            },
            'section_b_reading': {
                'stories_completed': stories_completed,
                'completion_rate': round(completion_rate, 1),
                'books_actively_read': books_actively_read,
                'stories_started_vs_completed': {
                    'labels': [label for (_s, _e, label) in stories_month_buckets],
                    'started': stories_started_series,
                    'completed': stories_completed_series
                },
                'top_books': top_books,
                'quizzes_scheduled': quizzes_scheduled
            },
            'section_c_sessions': {
                'sessions_held': sessions_held,
                'avg_attendance_rate': round(avg_attendance_rate, 1),
                'upcoming_sessions': upcoming_sessions,
                'sessions_per_month': {
                    'labels': [label for (_s, _e, label) in sessions_per_month_buckets],
                    'online': sessions_online_series,
                    'classroom': sessions_classroom_series
                },
                'teacher_activity': teacher_activity
            },
            'section_d_packs': {
                'top_packs': section_d_top_packs,
                'invitation_codes': invitation_codes_payload
            },
            'section_e_games': {
                'total_plays': total_plays,
                'total_words_learned': int(total_words_learned or 0),
                'avg_time_spent_seconds': round(float(avg_time_spent_seconds or 0), 1),
                'plays_by_type': plays_by_type,
                'plays_over_time': {'labels': bucket_labels, 'data': plays_over_time_series}
            }
        }
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'message': 'Error retrieving reading analytics', 'error': str(error)}), 500


@admin.route('/create_about_book/<int:book_id>', methods=['POST'])
def create_about_book_from_json_file(book_id):
    # Check if a record with the same book_id already exists
    existing_book = Book.query.filter_by(id=book_id).first()

    if not existing_book:
        return jsonify({'message': "Book doesn't exists"}), 400


    existing_about_book = About_Book.query.filter_by(book_id=book_id).first()
    
    if existing_about_book:
        return jsonify({'message': 'About_Book for this book already exists'}), 400
    
    if 'jsonFile' in request.files:
        json_file = request.files['jsonFile']
        try:
            # Parse the JSON data from the file
            data = json_file.read()
            about_data = json.loads(data)

            # Create a new About_Book instance
            about_book = About_Book(book_id=book_id, about=about_data)

            # Add it to the database
            db.session.add(about_book)
            db.session.commit()

            return jsonify({'message': 'About_Book created successfully','about':about_data}), 201
        except json.JSONDecodeError as e:
            return jsonify({'message': 'Invalid JSON data in the file', 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'message': 'Error creating About_Book', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'No JSON file uploaded'}), 400


@admin.route('/update_about_book/<int:book_id>', methods=['PUT', 'PATCH'])
def update_about_book_from_json(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        # Ensure the uploaded file is a JSON file
        if 'jsonFile' in request.files:
            json_file = request.files['jsonFile']
            try:
                # Parse the JSON data from the file
                data = json_file.read()
                about_data = json.loads(data)

                # Update the "about" field of the About_Book instance
                about_book.about = about_data
                
                # Commit the changes to the database
                db.session.commit()
                
                return jsonify({'message': 'About_Book updated successfully','about':about_data}), 200
            except json.JSONDecodeError as e:
                return jsonify({'message': 'Invalid JSON data in the file', 'error': str(e)}), 400
            except Exception as e:
                return jsonify({'message': 'Error updating About_Book', 'error': str(e)}), 500
        else:
            return jsonify({'message': 'No JSON file uploaded'}), 400
    else:
        return jsonify({'message': 'About_Book not found'}), 404
@admin.route('/delete_about_book/<int:book_id>', methods=['DELETE'])
def delete_about_book(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        try:
            # Delete the About_Book instance
            db.session.delete(about_book)
            db.session.commit()

            return jsonify({'message': 'About_Book deleted successfully'}), 200
        except Exception as e:
            return jsonify({'message': 'Error deleting About_Book', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'About_Book not found'}), 404

@admin.route('/get_about_book/<int:book_id>')
def get_about_book_by_book_id(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        # Serialize the About_Book object to a JSON response
        about_book_data = {
            'id': about_book.id,
            'book_id': about_book.book_id,
            'about': about_book.about
        }
        return jsonify(about_book_data), 200
    else:
        return jsonify({'message': 'About_Book not found for the specified book_id'}), 404 



@admin.route('/create_notification', methods=['POST'])
@login_required
@admin_required
def create_notification():
    try:
        # Get data from the request
        data = request.get_json()
        user_id = data['user_id']
        notification_id = data['notification_id']
        if not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'User not found'}), 404
     
        if Notification_user.query.filter_by(user_id=user_id, notification_id=notification_id).first():
            return jsonify({'message': 'This notification is already send it to user'}), 409  # Conflict
        else:
            new_notification = Notification_user(
                user_id=user_id,
                notification_id=notification_id,
            )

            db.session.add(new_notification)
            db.session.commit()

            # Return a success response
            response_data = {
                'message': 'Your notification has been successfully added.',
                'notification': {
                    'user_id': user_id,
                    'notification_id': notification_id,
                    'id': new_notification.id,
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/delete_notification',methods=['POST'])
@login_required
@admin_required
def delete_notification():
    try:
        id = request.json['id']
        notification = Notification_user.query.filter_by(notification_id=id).first()
        if notification and not user_belongs_to_current_school(notification.user_id):
            return jsonify({'message': 'Invalid Notification'}), 404
        if notification:
            db.session.delete(notification)
            db.session.commit()
            return jsonify({'message': 'Notification deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid Notification'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_notification',methods=['POST'])
@login_required
@admin_required
def get_notification():
    try:
        user_id = request.json['user_id']
        if not user_belongs_to_current_school(user_id):
            return jsonify({'message': 'User not found'}), 404
        

        notifications = Notification_user.query.filter_by(user_id=user_id).all()
        notification_data=[]
        for notification in notifications :
            notification_data.append({
                'user_id': notification.user_id,
                'notification_id': notification.notification_id,
                'id': notification.id,
            })
        return jsonify({
            'notifications': notification_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/get_users_in_pack',methods=['POST'])
@login_required
@admin_or_assistant_required
def get_users_in_pack():
    try:
        pack_id = request.json['pack_id']
        if not get_school_accessible_pack(pack_id):
            return jsonify({'message': 'Pack not found'}), 404
        
        school_user_ids = get_current_school_user_ids()
        users = (
            Follow_pack.query
            .filter(Follow_pack.pack_id == pack_id)
            .filter(Follow_pack.user_id.in_(school_user_ids) if school_user_ids else False)
            .all()
        )
        user_data=[]
        for user in users :
            reader= User.query.filter_by(id=user.user_id).first()
            user_data.append({
                'id': user.user_id,
                'username':reader.username,
                'email':reader.email
            })
        return jsonify({
            'users': user_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   

@admin.route('/paser_story',methods=['POST'])
@login_required
@admin_or_assistant_required
def paser_story():
    try:
        text = request.json['text']

        print(text)
        words= get_tenses_words(text)
        
        return jsonify({
            "words":words
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   

            
@admin.route('/get_word',methods=['POST'])
@login_required
@admin_or_assistant_required
def get_word():
    try:
        word = request.json['word']
        driver =Neo4jDriver().get_driver()
        result = DataSetDB.get_word_from_db(driver,word)

        if result.get('code') is not None and  result['code']  == 400:
            return jsonify({'message': result['message']}), 404  
     
        return jsonify({
            "res":result
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error','e':{str(e)}}), 500  

#link pack to invoice 

@admin.route('/link_pack_to_invoicing')
def link_pack_to_invoicing():
    try:
        pack_id = request.json['pack_id']
        pack=get_school_pack(pack_id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        invoicing_product ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}',
                'title': pack.title,
                'price': pack.price,
                'vat':0,
                'quantity': 999,
                }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/product/create', json=invoicing_product)  
        if invoicing_response.status_code==201:
            invoicing_data = invoicing_response.json()
            prodcut_id = invoicing_data['_id']
            pack.product_id_invoicing_api =prodcut_id
            db.session.commit()

            return jsonify({'message':'pack has been linked to invoicing_api'})


    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/school_public_page', methods=['GET'])
@login_required
def get_current_school_public_page():
    try:
        if not is_admin_role():
            return jsonify({'message': 'Admin access is required'}), 401

        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        page = get_or_create_school_public_page(school)
        db.session.commit()
        return jsonify({'public_page': serialize_school_public_page(page)}), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to get school public page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/school_public_page', methods=['PUT', 'PATCH'])
@login_required
def update_current_school_public_page():
    try:
        if not is_admin_role():
            return jsonify({'message': 'Admin access is required'}), 401

        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        page = get_or_create_school_public_page(school)

        if 'active' in data:
            page.active = parse_bool_value(data.get('active'), 'active')
            db.session.add(page)

        if 'show_public_packs' in data:
            page.show_public_packs = parse_bool_value(data.get('show_public_packs'), 'show_public_packs')
            db.session.add(page)

        apply_content_to_draft(page, normalize_public_page_content_fields(data))
        db.session.commit()
        return jsonify({
            'message': 'Draft saved successfully',
            'public_page': serialize_school_public_page(page)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to update school public page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/school_public_page/publish', methods=['POST'])
@login_required
def publish_current_school_public_page():
    try:
        if not is_admin_role():
            return jsonify({'message': 'Admin access is required'}), 401

        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        page = get_or_create_school_public_page(school)
        if page.draft_data is None:
            return jsonify({'message': 'There are no unpublished changes to publish'}), 400

        apply_content_to_live(page, page.draft_data)
        page.draft_data = None
        page.published_at = datetime.now()
        db.session.commit()
        return jsonify({
            'message': 'School public page published successfully',
            'public_page': serialize_school_public_page(page)
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to publish school public page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/school_public_page/draft', methods=['DELETE'])
@login_required
def discard_current_school_public_page_draft():
    try:
        if not is_admin_role():
            return jsonify({'message': 'Admin access is required'}), 401

        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'Current admin has no school assigned'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        page = get_or_create_school_public_page(school)
        page.draft_data = None
        db.session.add(page)
        db.session.commit()
        return jsonify({
            'message': 'Draft discarded',
            'public_page': serialize_school_public_page(page)
        }), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to discard school public page draft: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/super/schools/<int:school_id>/public-page', methods=['GET'])
@login_required
def get_super_school_public_page(school_id):
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access is required'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        page = get_or_create_school_public_page(school)
        db.session.commit()
        return jsonify({'public_page': serialize_school_public_page(page)}), 200
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to get super school public page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/super/schools/<int:school_id>/public-page', methods=['PUT', 'PATCH'])
@login_required
def update_super_school_public_page(school_id):
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access is required'}), 403

        school = Shcool.query.get(school_id)
        if not school:
            return jsonify({'message': 'School not found'}), 404

        data = request.get_json(silent=True) or {}
        requested_name = data.get('school_name') or data.get('name')
        if requested_name is not None:
            requested_name = str(requested_name).strip()
            if not requested_name:
                return jsonify({'message': 'School name is required'}), 400
            if school_name_exists(requested_name, exclude_school_id=school.id):
                return jsonify({'message': 'This school name is already used. Please choose another'}), 409
            school.name = requested_name

        page = get_or_create_school_public_page(school)
        apply_school_public_page_payload(page, data, allow_slug=True)
        db.session.add(school)
        db.session.commit()
        return jsonify({
            'message': 'School public page updated successfully',
            'public_page': serialize_school_public_page(page)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        logging.error('Unable to update super school public page: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


# Create
@admin.route('/create_shcool', methods=['POST'])
def create_shcool():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        if not name:
            raise ValueError('Name is required')
        name = str(name).strip()
        if school_name_exists(name):
            return jsonify({'message': 'This school name is already used. Please choose another'}), 409

        email = data.get('email')
        password = data.get('password')
        if (email and not password) or (password and not email):
            return jsonify({'message': 'email and password must be provided together'}), 400
        email = str(email).strip().lower() if email else None
        if email and User.query.filter_by(email=email).first():
            return jsonify({'message': 'A user with this email already exists'}), 409

        new_shcool = Shcool(name=name)
        db.session.add(new_shcool)
        db.session.flush()
        get_or_create_school_public_page(new_shcool)

        school_admin = None
        if email and password:
            school_admin = Admin(
                username=name,
                email=email,
                password_hashed=bcrypt.generate_password_hash(password).decode('utf-8'),
                created_at=datetime.now(),
                confirmed=True,
                approved=True,
                must_change_password=True
            )
            db.session.add(school_admin)
            db.session.flush()
            db.session.add(User_shcool(user_id=school_admin.id, shcool_id=new_shcool.id))

        db.session.commit()

        log_admin_action('create', 'school', new_shcool.id, f'name={new_shcool.name}')

        result = {
            'id':new_shcool.id,
            'name':new_shcool.name
        }
        response = {'message': 'Shcool created successfully','shcool':result}

        if school_admin:
            email_sent, email_error = send_school_welcome_email(school_admin, new_shcool, password)
            response['admin'] = {
                'id': school_admin.id,
                'email': school_admin.email,
                'username': school_admin.username
            }
            response['welcome_email_sent'] = email_sent
            if email_error:
                response['welcome_email_error'] = email_error

        return jsonify(response), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

# Read
@admin.route('/get_all_shcools', methods=['GET'])
def get_all_shcools():
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        shcools = Shcool.query.all()
        result = [{'id': shcool.id, 'name': shcool.name} for shcool in shcools]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Update
@admin.route('/update_shcool/<int:id>', methods=['PUT'])
def update_shcool(id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        shcool = Shcool.query.get_or_404(id)
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        if not name:
            raise ValueError('Name is required')
        name = str(name).strip()
        if school_name_exists(name, exclude_school_id=shcool.id):
            return jsonify({'message': 'This school name is already used. Please choose another'}), 409
        shcool.name = name
        db.session.commit()
        log_admin_action('update', 'school', id, f'name={name}')
        res ={
            'id':id,
            'name':name
        }
        return jsonify({'message': 'Shcool updated successfully','shcool':res})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Delete
@admin.route('/delete_shcool/<int:id>', methods=['DELETE'])
def delete_shcool(id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        shcool = Shcool.query.get_or_404(id)
        deleted_name = shcool.name
        SchoolPublicPage.query.filter_by(shcool_id=shcool.id).delete(synchronize_session=False)
        db.session.delete(shcool)
        db.session.commit()
        log_admin_action('delete', 'school', id, f'name={deleted_name}')
        return jsonify({'message': 'Shcool deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin.route('/get_one_shcool/<int:id>')
def get_one_shcool(id):
    if not is_super_admin():
        return jsonify({'message': 'Super admin access required'}), 403
    try:
        shcool = Shcool.query.get_or_404(id)
        result = {'id': shcool.id, 'name': shcool.name}
        return jsonify({'shcool': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/generate_template/<int:id>')
def generate_template(id):
    try:
        pack = get_school_pack(id)
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404
        book_packs = Book_pack.query.filter_by(pack_id=id).all()  
        book_pack_data = [book_pack.book_id for book_pack in book_packs]
        new_template =  Pack_template(title=pack.title,level=pack.level,desc = pack.desc,age=pack.age.value,img=pack.img,faq=pack.faq,book_pack_ids=book_pack_data)
        db.session.add(new_template)
        db.session.commit()
        return jsonify({'message': 'Template generated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/import_template/<int:id>')
def import_template(id):
    try:
       
        pack_template = Pack_template.query.get_or_404(id)      
        shcool_user = User_shcool.query.filter_by(user_id=current_user.id).first()

        book_packs_data = pack_template.book_pack_ids

        new_pack =  Pack(title=pack_template.title,level=pack_template.level,desc = pack_template.desc,age=pack_template.age,img=pack_template.img,faq=pack_template.faq,shcool_id=shcool_user.shcool_id)
        db.session.add(new_pack)       
        db.session.commit()
        
        for item in book_packs_data:
            book_pack = Book_pack(pack_id=new_pack.id, book_id=item)
            db.session.add(book_pack)
            db.session.commit()

        return jsonify({'message': 'Template imported successfully'}) 

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/pack_templates/<int:template_id>', methods=['GET'])
def get_pack_template(template_id):
    try:
        # Query the database for the Pack_template object with the given ID
        template = Pack_template.query.get(template_id)
        
        # Check if the template exists
        if template is None:
            # Return a 404 Not Found response if the template does not exist
            return jsonify({'error': 'Template not found'}), 404
        book_packs = []
        for book_pack_id in template.book_pack_ids:

            book = Book.query.get(book_pack_id)
            if book:
                book_packs.append({
                    'id': book.id,
                    'title': book.title,
                    'author': book.author,
                    'img':book.img,
                    'desc':book.desc,
                    'release_date':book.release_date,
                    'page_number':book.page_number,
                    'category':book.category
                    })

        # Serialize the Pack_template object to JSON and return it
        return jsonify({
            'id': template.id,
            'title': template.title,
            'level': template.level,
            'desc': template.desc,
            'age': template.age,
            'img': template.img,
            'faq': template.faq,
            'books': book_packs,
            'template_type': template.template_type.value ,
            'book_number':len(book_packs) 
        })
    except Exception as e:
        # Return a 500 Internal Server Error response if an unexpected error occurs
        return jsonify({'error': 'Internal Server Error', 'message': str(e)}), 500
# Define a route to handle GET requests for all Pack_template objects
@admin.route('/pack_templates', methods=['GET'])
def get_all_pack_templates():
    try:
        # Query the database to retrieve all Pack_template objects
        templates = Pack_template.query.all()

        # Serialize each Pack_template object to JSON
        serialized_templates = []
        for template in templates:
            # Retrieve each book corresponding to the book pack IDs
            book_packs = []
            for book_pack_id in template.book_pack_ids:
                book = Book.query.get(book_pack_id)
                if book:
                    book_packs.append({
                        'id': book.id,
                        'title': book.title,
                        'author': book.author,
                        'img':book.img,
                        'desc':book.desc,
                        'release_date':book.release_date,
                        'page_number':book.page_number,
                        'category':book.category
                        })

            serialized_templates.append({
                'id': template.id,
                'title': template.title,
                'level': template.level,
                'desc': template.desc,
                'age': template.age,
                'img': template.img,
                'faq': template.faq,
                'books': book_packs,
                'template_type': template.template_type.value,
                'book_number':len(book_packs)   
            })

        # Return the list of serialized Pack_template objects as JSON response
        return jsonify(serialized_templates)
    except Exception as e:
        # Return a 500 Internal Server Error response if an unexpected error occurs
        return jsonify({'error': 'Internal Server Error', 'message': str(e)}), 500  


# book Text 
@admin.route('/book_text', methods=['POST'])
def create_book_text():
    try:
        data = request.json
        print(data)
        if not data or not data.get('book_id') or not data.get('text'):
            return jsonify({"error": "Missing 'book_id' or 'text'"}), 400

        book = Book.query.get(data['book_id']) if is_super_admin() else get_school_book(data['book_id'])
        if not book:
            return jsonify({"error": "Book not found"}), 404
        if not is_super_admin() and is_platform_book(book):
            return jsonify({"error": "IRead platform headwords are read-only for school admins"}), 403
        if not is_super_admin() and book.shcool_id != get_current_school_id():
            return jsonify({"error": "This book text is not editable by the current school"}), 403

        new_entry = upsert_book_text(book.id, data['text'])
        db.session.commit()
        return jsonify({"message": "Book text saved successfully", "id": new_entry.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# --------- READ ALL ---------
@admin.route('/book_text', methods=['GET'])
def get_all_book_texts():
    try:
        if is_super_admin():
            entries = Book_text.query.all()
        else:
            book_ids = [book.id for book in school_book_query().all()]
            entries = Book_text.query.filter(Book_text.book_id.in_(book_ids)).all() if book_ids else []
        result = [{
            "id": entry.id,
            "book_id": entry.book_id,
            "text": entry.text
        } for entry in entries]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- READ ONE ---------
@admin.route('/book_text/<int:book_id>', methods=['GET'])
def get_book_text_by_book_id(book_id):
    try:
        if not is_super_admin() and not get_school_book(book_id):
            return jsonify({"error": "Book not found"}), 404
        entry = Book_text.query.filter_by(book_id=book_id).first()
        if not entry:
            return jsonify({"error": "Entry not found for the given book_id"}), 404
        return jsonify({
            "id": entry.id,
            "book_id": entry.book_id,
            "text": entry.text
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- UPDATE ---------
@admin.route('/book_text/<int:book_id>', methods=['PUT'])
def update_book_text_by_book_id(book_id):
    try:
        book = Book.query.get(book_id) if is_super_admin() else get_school_book(book_id)
        if not book:
            return jsonify({"error": "Book not found"}), 404
        if not is_super_admin() and is_platform_book(book):
            return jsonify({"error": "IRead platform headwords are read-only for school admins"}), 403
        if not is_super_admin() and book.shcool_id != get_current_school_id():
            return jsonify({"error": "This book text is not editable by the current school"}), 403

        entry = Book_text.query.filter_by(book_id=book_id).first()
        if not entry:
            return jsonify({"error": "Entry not found for the given book_id"}), 404

        data = request.json
        if data.get('text'):
            entry.text = data['text']

        db.session.commit()
        return jsonify({"message": "Text updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# --------- DELETE ---------
@admin.route('/book_text/<int:id>', methods=['DELETE'])
def delete_book_text(id):
    try:
        entry = Book_text.query.get(id)
        if not entry:
            return jsonify({"error": "Entry not found"}), 404
        book = Book.query.get(entry.book_id) if is_super_admin() else get_school_book(entry.book_id)
        if not book:
            return jsonify({"error": "Book not found"}), 404
        if not is_super_admin() and is_platform_book(book):
            return jsonify({"error": "IRead platform headwords are read-only for school admins"}), 403
        if not is_super_admin() and book.shcool_id != get_current_school_id():
            return jsonify({"error": "This book text is not editable by the current school"}), 403

        db.session.delete(entry)
        db.session.commit()
        return jsonify({"message": "Entry deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


##---------word defenition----------

@admin.route('/define', methods=['GET'])
def define_word():
    try:
        word = request.args.get('word')
        if not word:
            return jsonify({"error": "Please provide a word"}), 400

        definition_en = get_short_definition(word)
        definition_ar = translate_to_arabic(word)

        return jsonify({
            "word": word,
            "definition_en": definition_en,
            "definition_ar": definition_ar
        })

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


##---------word sense / CEFR review queue (Word-Data brief T14-T16)----------

def get_scoped_book_ids(book_id_filter=None):
    """None means 'no restriction' (super admin, no book filter). Otherwise a
    concrete, already-authorized list of book ids to scope word senses to."""
    if is_super_admin():
        return [book_id_filter] if book_id_filter else None

    allowed = [book.id for book in school_book_query().all()]
    if book_id_filter:
        return [book_id_filter] if book_id_filter in allowed else []
    return allowed


def scope_word_sense_query(query, book_id_filter=None):
    book_ids = get_scoped_book_ids(book_id_filter)
    if book_ids is None:
        return query

    sense_ids = [
        row[0] for row in db.session.query(WordOccurrence.word_sense_id)
        .join(Chapter, WordOccurrence.chapter_id == Chapter.id)
        .filter(Chapter.book_id.in_(book_ids))
        .distinct()
        .all()
    ]
    return query.filter(WordSense.id.in_(sense_ids))


def serialize_suggestion(suggestion):
    return {
        'id': suggestion.id,
        'word_sense_id': suggestion.word_sense_id,
        'school_id': suggestion.school_id,
        'school_name': suggestion.school.name if suggestion.school else None,
        'suggestion_type': suggestion.suggestion_type,
        'suggested_cefr_level': suggestion.suggested_cefr_level,
        'suggested_proper_noun_excluded': suggestion.suggested_proper_noun_excluded,
        'suggested_definition': suggestion.suggested_definition,
        'suggested_synonyms': suggestion.suggested_synonyms,
        'suggested_example_sentence': suggestion.suggested_example_sentence,
        'note': suggestion.note,
        'status': suggestion.status,
        'suggested_by': suggestion.suggested_by,
        'suggested_by_name': suggestion.suggester.username if suggestion.suggester else None,
        'suggested_at': suggestion.suggested_at.isoformat(),
        'reviewed_by': suggestion.reviewed_by,
        'reviewed_at': suggestion.reviewed_at.isoformat() if suggestion.reviewed_at else None,
        'review_note': suggestion.review_note,
    }


def serialize_word_sense(sense, viewer_school_id=None):
    occurrences = list(sense.occurrences)
    book_ids = sorted({
        occurrence.chapter.book_id for occurrence in occurrences if occurrence.chapter
    })

    pending_suggestion = None
    if viewer_school_id:
        suggestion = (
            WordSenseSuggestion.query
            .filter_by(word_sense_id=sense.id, school_id=viewer_school_id, status=STATUS_PENDING)
            .order_by(WordSenseSuggestion.suggested_at.desc())
            .first()
        )
        if suggestion:
            pending_suggestion = serialize_suggestion(suggestion)

    return {
        'id': sense.id,
        'lemma': sense.lemma,
        'pos': sense.pos,
        'definition': sense.definition,
        'synonyms': sense.synonyms,
        'example_sentence': sense.example_sentence,
        'cefr_level': sense.cefr_level,
        'cefr_source': sense.cefr_source,
        'cefr_override_level': sense.cefr_override_level,
        'cefr_override_note': sense.cefr_override_note,
        'effective_cefr_level': sense.effective_cefr_level,
        'proper_noun_excluded': sense.proper_noun_excluded,
        'is_unresolved': sense.is_unresolved,
        'occurrence_count': len(occurrences),
        'sample_surface_forms': sorted({o.surface_form for o in occurrences})[:5],
        'book_ids': book_ids,
        'pending_suggestion': pending_suggestion,
    }


@admin.route('/word-senses', methods=['GET'])
def list_word_senses():
    try:
        page, per_page = get_super_admin_pagination_params()
        status = request.args.get('status', 'unresolved')
        search = (request.args.get('search') or '').strip().lower()
        book_id = request.args.get('book_id', type=int)

        query = WordSense.query

        if status == 'unresolved':
            query = query.filter(
                WordSense.cefr_level.is_(None),
                WordSense.cefr_override_level.is_(None),
                WordSense.proper_noun_excluded.is_(False),
            )
        elif status == 'excluded':
            query = query.filter(WordSense.proper_noun_excluded.is_(True))
        elif status == 'resolved':
            query = query.filter(or_(
                WordSense.cefr_level.isnot(None),
                WordSense.cefr_override_level.isnot(None),
            ))
        # status == 'all' -> no extra filter

        if search:
            query = query.filter(WordSense.lemma.like(f'%{search}%'))

        query = scope_word_sense_query(query, book_id)

        total = query.count()
        senses = (
            query.order_by(WordSense.lemma)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Only school admins have a single "own school" whose pending
        # suggestions are worth flagging inline — super admins use the
        # dedicated /word-suggestions review queue for the full picture.
        viewer_school_id = None if is_super_admin() else get_current_school_id()

        return jsonify({
            'items': [serialize_word_sense(sense, viewer_school_id) for sense in senses],
            'total': total,
            'page': page,
            'per_page': per_page,
        }), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/word-senses/quality', methods=['GET'])
def word_sense_quality():
    """T15 — the unresolved-rate signal: a spike should be visible against
    the normal trickle of proper nouns."""
    try:
        book_id = request.args.get('book_id', type=int)
        query = scope_word_sense_query(WordSense.query, book_id)

        total = query.count()
        resolved = query.filter(or_(
            WordSense.cefr_level.isnot(None),
            WordSense.cefr_override_level.isnot(None),
        )).count()
        excluded = query.filter(WordSense.proper_noun_excluded.is_(True)).count()
        unresolved = total - resolved - excluded

        return jsonify({
            'total': total,
            'resolved': resolved,
            'proper_noun_excluded': excluded,
            'unresolved': unresolved,
            'unresolved_rate': round(unresolved / total, 4) if total else 0,
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


VALID_CEFR_LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')


def upsert_pending_suggestion(word_sense_id, school_id, suggestion_type, **fields):
    """Updates the caller's own still-pending suggestion for this word in
    place rather than piling up duplicates when they revise it before review."""
    suggestion = WordSenseSuggestion.query.filter_by(
        word_sense_id=word_sense_id,
        school_id=school_id,
        suggestion_type=suggestion_type,
        status=STATUS_PENDING,
    ).first()

    if suggestion is None:
        suggestion = WordSenseSuggestion(
            word_sense_id=word_sense_id,
            school_id=school_id,
            suggestion_type=suggestion_type,
            suggested_by=current_user.id,
        )
        db.session.add(suggestion)

    for key, value in fields.items():
        setattr(suggestion, key, value)
    suggestion.suggested_by = current_user.id
    suggestion.suggested_at = datetime.now()
    suggestion.status = STATUS_PENDING

    db.session.commit()
    return suggestion


@admin.route('/word-senses/<int:sense_id>', methods=['PUT'])
def update_word_sense(sense_id):
    """Super admins edit directly, always. School admins can only suggest a
    CEFR level or proper-noun exclusion (see /word-senses/<id>/suggest) —
    dictionary content is direct or suggested depending on the platform's
    require_dictionary_approval setting."""
    try:
        sense = WordSense.query.get(sense_id)
        if not sense:
            return jsonify({'message': 'Word sense not found'}), 404

        super_admin = is_super_admin()

        if not super_admin:
            allowed_book_ids = set(get_scoped_book_ids())
            sense_book_ids = {
                occurrence.chapter.book_id for occurrence in sense.occurrences if occurrence.chapter
            }
            if not sense_book_ids & allowed_book_ids:
                return jsonify({'message': 'Not authorized to edit this word'}), 403

        data = request.get_json() or {}

        if not super_admin and ('cefr_override_level' in data or 'proper_noun_excluded' in data):
            return jsonify({
                'message': 'School admins can\'t set a CEFR level or proper-noun exclusion directly — '
                           'use POST /admin/word-senses/<id>/suggest to propose one for review.',
                'code': 'MUST_SUGGEST',
            }), 403

        dictionary_fields = {
            key: data[key] for key in ('definition', 'synonyms', 'example_sentence') if key in data
        }

        if dictionary_fields and not super_admin and PlatformSettings.get().require_dictionary_approval:
            school_id = get_current_school_id()
            suggestion = upsert_pending_suggestion(
                sense.id, school_id, SUGGESTION_TYPE_DICTIONARY,
                suggested_definition=dictionary_fields.get('definition', sense.definition),
                suggested_synonyms=dictionary_fields.get('synonyms', sense.synonyms),
                suggested_example_sentence=dictionary_fields.get('example_sentence', sense.example_sentence),
                note=data.get('note'),
            )
            commit_notification_event(notify_word_suggestion_submitted, suggestion, sense)
            return jsonify({
                'action': 'suggested',
                'message': 'Submitted for super-admin review — not live yet.',
                'suggestion': serialize_suggestion(suggestion),
            }), 202

        if 'definition' in data:
            sense.definition = data['definition']
        if 'synonyms' in data:
            sense.synonyms = data['synonyms']
        if 'example_sentence' in data:
            sense.example_sentence = data['example_sentence']
        if dictionary_fields:
            sense.enrichment_updated_by = current_user.id
            sense.enrichment_updated_at = datetime.now()

        if super_admin and 'proper_noun_excluded' in data:
            sense.proper_noun_excluded = bool(data['proper_noun_excluded'])
        if super_admin and 'cefr_override_level' in data:
            level = (data['cefr_override_level'] or '').strip().upper() or None
            if level and level not in VALID_CEFR_LEVELS:
                return jsonify({'message': 'Invalid CEFR level'}), 400
            sense.cefr_override_level = level
            sense.cefr_override_note = data.get('cefr_override_note')
            sense.cefr_override_by = current_user.id
            sense.cefr_override_at = datetime.now()

        db.session.commit()
        return jsonify({
            'action': 'updated',
            'message': 'Word sense updated successfully',
            'word_sense': serialize_word_sense(sense),
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/word-senses/<int:sense_id>/suggest', methods=['POST'])
def suggest_word_sense_change(sense_id):
    """School admins propose a CEFR level or proper-noun exclusion for an
    unresolved word — never applied live; a super admin must approve it via
    POST /admin/word-suggestions/<id>/approve."""
    try:
        if is_super_admin():
            return jsonify({
                'message': 'Super admins set this directly via PUT /admin/word-senses/<id> — no suggestion needed.',
            }), 400

        sense = WordSense.query.get(sense_id)
        if not sense:
            return jsonify({'message': 'Word sense not found'}), 404

        allowed_book_ids = set(get_scoped_book_ids())
        sense_book_ids = {
            occurrence.chapter.book_id for occurrence in sense.occurrences if occurrence.chapter
        }
        if not sense_book_ids & allowed_book_ids:
            return jsonify({'message': 'Not authorized to suggest for this word'}), 403

        school_id = get_current_school_id()
        if not school_id:
            return jsonify({'message': 'No school context for this account'}), 400

        data = request.get_json() or {}
        cefr_level = (data.get('cefr_level') or '').strip().upper() or None
        proper_noun_excluded = data.get('proper_noun_excluded')

        if cefr_level and cefr_level not in VALID_CEFR_LEVELS:
            return jsonify({'message': 'Invalid CEFR level'}), 400
        if cefr_level is None and proper_noun_excluded is None:
            return jsonify({'message': 'Provide cefr_level or proper_noun_excluded'}), 400

        suggestion = upsert_pending_suggestion(
            sense.id, school_id, SUGGESTION_TYPE_CEFR,
            suggested_cefr_level=cefr_level,
            suggested_proper_noun_excluded=bool(proper_noun_excluded) if proper_noun_excluded is not None else None,
            note=data.get('note'),
        )
        commit_notification_event(notify_word_suggestion_submitted, suggestion, sense)

        return jsonify({
            'message': 'Suggestion submitted for super-admin review.',
            'suggestion': serialize_suggestion(suggestion),
        }), 202
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/word-suggestions', methods=['GET'])
def list_word_suggestions():
    """Super admin's review queue — every pending suggestion, across every
    school, so conflicting suggestions for the same word are visible together."""
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access required'}), 403

        suggestions = (
            WordSenseSuggestion.query
            .filter_by(status=STATUS_PENDING)
            .order_by(WordSenseSuggestion.word_sense_id, WordSenseSuggestion.suggested_at)
            .all()
        )

        grouped = {}
        for suggestion in suggestions:
            sense = suggestion.word_sense
            key = sense.id
            if key not in grouped:
                grouped[key] = {
                    'word_sense_id': sense.id,
                    'lemma': sense.lemma,
                    'pos': sense.pos,
                    'effective_cefr_level': sense.effective_cefr_level,
                    'definition': sense.definition,
                    'suggestions': [],
                }
            grouped[key]['suggestions'].append(serialize_suggestion(suggestion))

        return jsonify({'words': list(grouped.values())}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/word-suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_word_suggestion(suggestion_id):
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access required'}), 403

        suggestion = WordSenseSuggestion.query.get(suggestion_id)
        if not suggestion or suggestion.status != STATUS_PENDING:
            return jsonify({'message': 'No pending suggestion with that id'}), 404

        sense = suggestion.word_sense
        now = datetime.now()

        if suggestion.suggestion_type == SUGGESTION_TYPE_CEFR:
            if suggestion.suggested_cefr_level:
                sense.cefr_override_level = suggestion.suggested_cefr_level
                sense.cefr_override_note = suggestion.note
            if suggestion.suggested_proper_noun_excluded is not None:
                sense.proper_noun_excluded = suggestion.suggested_proper_noun_excluded
            sense.cefr_override_by = current_user.id
            sense.cefr_override_at = now
        else:
            if suggestion.suggested_definition is not None:
                sense.definition = suggestion.suggested_definition
            if suggestion.suggested_synonyms is not None:
                sense.synonyms = suggestion.suggested_synonyms
            if suggestion.suggested_example_sentence is not None:
                sense.example_sentence = suggestion.suggested_example_sentence
            sense.enrichment_updated_by = current_user.id
            sense.enrichment_updated_at = now

        suggestion.status = STATUS_APPROVED
        suggestion.reviewed_by = current_user.id
        suggestion.reviewed_at = now
        suggestion.review_note = (request.get_json(silent=True) or {}).get('note')

        siblings = WordSenseSuggestion.query.filter(
            WordSenseSuggestion.word_sense_id == sense.id,
            WordSenseSuggestion.suggestion_type == suggestion.suggestion_type,
            WordSenseSuggestion.status == STATUS_PENDING,
            WordSenseSuggestion.id != suggestion.id,
        ).all()
        for sibling in siblings:
            sibling.status = STATUS_SUPERSEDED
            sibling.reviewed_by = current_user.id
            sibling.reviewed_at = now

        db.session.commit()
        commit_notification_event(notify_word_suggestion_reviewed, suggestion, sense, True)
        return jsonify({
            'message': 'Suggestion approved and applied.',
            'word_sense': serialize_word_sense(sense),
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/word-suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_word_suggestion(suggestion_id):
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access required'}), 403

        suggestion = WordSenseSuggestion.query.get(suggestion_id)
        if not suggestion or suggestion.status != STATUS_PENDING:
            return jsonify({'message': 'No pending suggestion with that id'}), 404

        data = request.get_json(silent=True) or {}
        suggestion.status = STATUS_REJECTED
        suggestion.reviewed_by = current_user.id
        suggestion.reviewed_at = datetime.now()
        suggestion.review_note = data.get('note')

        db.session.commit()
        sense = suggestion.word_sense
        commit_notification_event(notify_word_suggestion_reviewed, suggestion, sense, False)
        return jsonify({'message': 'Suggestion rejected.'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/settings', methods=['GET'])
def get_platform_settings():
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access required'}), 403

        settings = PlatformSettings.get()
        return jsonify({
            'require_dictionary_approval': settings.require_dictionary_approval,
            'default_trial_seats': settings.default_trial_seats,
        }), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin.route('/settings', methods=['PUT'])
def update_platform_settings():
    try:
        if not is_super_admin():
            return jsonify({'message': 'Super admin access required'}), 403

        data = request.get_json() or {}
        settings = PlatformSettings.get()
        if 'require_dictionary_approval' in data:
            settings.require_dictionary_approval = bool(data['require_dictionary_approval'])
            settings.updated_by = current_user.id
            settings.updated_at = datetime.now()

        if 'default_trial_seats' in data:
            try:
                trial_seats = int(data['default_trial_seats'])
            except (TypeError, ValueError):
                return jsonify({'message': 'default_trial_seats must be a number'}), 400
            if trial_seats < 0:
                return jsonify({'message': 'default_trial_seats cannot be negative'}), 400
            settings.default_trial_seats = trial_seats
            settings.updated_by = current_user.id
            settings.updated_at = datetime.now()

        db.session.commit()
        return jsonify({
            'require_dictionary_approval': settings.require_dictionary_approval,
            'default_trial_seats': settings.default_trial_seats,
        }), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


##---------reader achievement/progress visibility (admin-facing)----------

def get_scoped_school_ids(school_id_filter=None):
    """Mirrors get_scoped_book_ids's shape for schools: None means 'no
    restriction' (super admin, no filter)."""
    if is_super_admin():
        return [school_id_filter] if school_id_filter else None

    allowed = [m.shcool_id for m in User_shcool.query.filter_by(user_id=current_user.id).all()]
    if school_id_filter:
        return [school_id_filter] if school_id_filter in allowed else []
    return allowed


@admin.route('/reader-progress', methods=['GET'])
def list_reader_progress():
    try:
        page, per_page = get_super_admin_pagination_params()
        search = (request.args.get('search') or '').strip().lower()
        school_id = request.args.get('school_id', type=int)

        school_ids = get_scoped_school_ids(school_id)

        query = Reader.query
        if school_ids is not None:
            reader_ids = [
                m.user_id for m in User_shcool.query.filter(User_shcool.shcool_id.in_(school_ids)).all()
            ]
            query = query.filter(Reader.id.in_(reader_ids))
        if search:
            query = query.filter(or_(
                Reader.username.like('%' + search + '%'),
                Reader.email.like('%' + search + '%'),
            ))

        total = query.count()
        readers = (
            query.order_by(Reader.username)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return jsonify({
            'items': [serialize_reader_progress(reader) for reader in readers],
            'total': total,
            'page': page,
            'per_page': per_page,
        }), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

'''

Show all teacher postulate
Accept an Reader to be Teacher (We will a table that contain a id of the reader and incomming informations)
Deactivate a session
Read Upadate  Book
Create Read Upadate Delete Session
Create Read Upadate Delete Pack
Create Read Update Delete Reader,Teacher

'''


    
