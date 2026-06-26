import json
import os
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from apps.audiobooks.alignment import (
    AudioAlignmentError,
    AudioAlignmentUnavailable,
    generate_model_alignment,
)
from config import ConfigClass
from extensions import db
from models.audio_book import AudioBook, AudioBookPage, AudioBookProgress
from models.book import Book
from models.shcool import Shcool
from models.user import User
from models.user_shcool import User_shcool


admin_audiobooks = Blueprint('admin_audiobooks', __name__, url_prefix='/admin')
teacher_audiobooks = Blueprint('teacher_audiobooks', __name__, url_prefix='/teacher')
reader_audiobooks = Blueprint('reader_audiobooks', __name__, url_prefix='/reader')

AUDIO_BOOK_STATUSES = {'draft', 'published', 'archived'}
PAGE_ALIGNMENT_STATUSES = {
    'draft',
    'queued-local',
    'processing-local',
    'review-required',
    'ready',
    'approved',
    'failed',
}
ALIGNMENT_WORD_STATUSES = {
    'matched',
    'interpolated',
    'unmatched',
    'manually-edited',
    'not-spoken',
}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'webm', 'ogg'}
ALLOWED_IMAGE_MIME_PREFIXES = ('image/jpeg', 'image/png', 'image/webp')
ALLOWED_AUDIO_MIME_TYPES = {
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/x-wav',
    'audio/wave',
    'audio/mp4',
    'audio/m4a',
    'audio/x-m4a',
    'audio/webm',
    'audio/ogg',
    'application/ogg',
    'application/octet-stream',
    'binary/octet-stream',
}
PAGE_IMAGE_POSITIONS = {'above', 'below'}
MIN_PAGE_FONT_SIZE = 12
MAX_PAGE_FONT_SIZE = 48


def is_active_role(*roles):
    return (
        current_user.is_authenticated and
        current_user.type in roles and
        current_user.confirmed and
        current_user.approved
    )


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_active_role('admin', 'super_admin'):
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_active_role('teacher', 'admin', 'super_admin'):
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function


def is_super_admin():
    return is_active_role('super_admin')


def get_positive_int(value, name):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number')
    if value < 1:
        raise ValueError(f'{name} must be greater than 0')
    return value


def get_optional_positive_int(value, name):
    if value is None or value == '':
        return None
    return get_positive_int(value, name)


def get_request_data():
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        return request.form
    return request.get_json(silent=True) or {}


def get_request_school_id():
    data = get_request_data()
    school_id = (
        request.args.get('school')
        or request.args.get('school_id')
        or request.args.get('shcool_id')
        or data.get('school')
        or data.get('school_id')
        or data.get('shcool_id')
    )
    return get_optional_positive_int(school_id, 'school_id')


def get_user_school_ids(user_id):
    return [
        membership.shcool_id
        for membership in User_shcool.query.filter_by(user_id=user_id).all()
    ]


def get_current_school_id():
    membership = User_shcool.query.filter_by(user_id=current_user.id).first()
    return membership.shcool_id if membership else None


def resolve_school_scope_for_creator():
    if is_super_admin():
        school_id = get_request_school_id()
        if school_id is not None and not Shcool.query.get(school_id):
            raise ValueError('School not found')
        return school_id

    school_ids = get_user_school_ids(current_user.id)
    if not school_ids:
        raise PermissionError('No school access')

    requested_school_id = get_request_school_id()
    if requested_school_id is None:
        if len(school_ids) == 1:
            return school_ids[0]
        raise ValueError('school_id is required')

    if requested_school_id not in school_ids:
        raise PermissionError('You do not have access to this school')
    return requested_school_id


def can_access_source_book(source_book, school_id=None):
    if not source_book or not getattr(source_book, 'active', True):
        return False
    if is_super_admin():
        return True
    accessible_school_ids = get_user_school_ids(current_user.id)
    if school_id is None:
        school_id = get_current_school_id()
    return (
        source_book.shcool_id is None or
        source_book.shcool_id in accessible_school_ids or
        (school_id is not None and source_book.shcool_id == school_id)
    )


def get_manageable_source_book(book_id, school_id=None):
    source_book = Book.query.filter_by(id=book_id).first()
    if not can_access_source_book(source_book, school_id=school_id):
        return None
    return source_book


def get_audio_book_for_source_book(source_book, school_id):
    query = AudioBook.query.filter_by(
        book_id=source_book.id,
        shcool_id=school_id,
        active=True
    )
    return query.order_by(AudioBook.updated_at.desc()).first()


def create_audio_book_from_source_book(source_book, school_id):
    data = get_request_data()
    title = str(data.get('title') or source_book.title or '').strip()
    book = AudioBook(
        title=title,
        description=data.get('description', source_book.desc),
        language=str(data.get('language') or 'en').strip()[:20] or 'en',
        level=data.get('level'),
        category=data.get('category', source_book.category),
        book_id=source_book.id,
        status='draft',
        shcool_id=school_id,
        created_by_id=current_user.id,
        created_by_role=current_user.type,
        active=True,
    )
    if not book.title:
        raise ValueError('Title is required')
    db.session.add(book)
    db.session.flush()
    save_cover_image(book)
    return book


def resolve_school_scope_for_source_book(source_book):
    if is_super_admin():
        requested_school_id = get_request_school_id()
        if requested_school_id is not None and not Shcool.query.get(requested_school_id):
            raise ValueError('School not found')
        return requested_school_id if requested_school_id is not None else source_book.shcool_id

    school_ids = get_user_school_ids(current_user.id)
    if not school_ids:
        raise PermissionError('No school access')
    if source_book.shcool_id in school_ids:
        return source_book.shcool_id

    requested_school_id = get_request_school_id()
    if requested_school_id is not None:
        if requested_school_id not in school_ids:
            raise PermissionError('You do not have access to this school')
        return requested_school_id

    if len(school_ids) == 1:
        return school_ids[0]
    raise ValueError('school_id is required')


def serialize_source_book(source_book):
    return {
        'id': source_book.id,
        'title': source_book.title,
        'description': source_book.desc,
        'author': source_book.author,
        'category': source_book.category,
        'school_id': source_book.shcool_id,
        'source': 'platform' if source_book.shcool_id is None else 'school',
    }


def can_manage_audio_book(book):
    if not book or not book.active:
        return False
    if is_super_admin():
        return True
    if current_user.type == 'admin':
        school_id = get_current_school_id()
        return bool(school_id and book.shcool_id == school_id)
    if current_user.type == 'teacher':
        return (
            book.created_by_id == current_user.id and
            book.shcool_id in get_user_school_ids(current_user.id)
        )
    return False


def get_manageable_audio_book(book_id):
    book = AudioBook.query.filter_by(id=book_id, active=True).first()
    if not can_manage_audio_book(book):
        return None
    return book


def get_book_page(book, page_id):
    return AudioBookPage.query.filter_by(
        id=page_id,
        audio_book_id=book.id,
        active=True
    ).first()


def get_file_size(file_storage):
    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return file_size


def get_file_extension(file_storage):
    filename = secure_filename(file_storage.filename or '')
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def is_allowed_image_file(file_storage):
    if not file_storage or not file_storage.filename:
        return False
    extension = get_file_extension(file_storage)
    mimetype = (file_storage.mimetype or '').lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS and (
        mimetype in ALLOWED_IMAGE_MIME_PREFIXES or mimetype == 'application/octet-stream'
    )


def is_allowed_audio_file(file_storage):
    if not file_storage or not file_storage.filename:
        return False
    extension = get_file_extension(file_storage)
    mimetype = (file_storage.mimetype or '').lower()
    return extension in ALLOWED_AUDIO_EXTENSIONS and mimetype in ALLOWED_AUDIO_MIME_TYPES


def validate_upload_size(file_storage, max_mb, label):
    file_size = get_file_size(file_storage)
    max_file_size = max_mb * 1024 * 1024
    if file_size > max_file_size:
        raise ValueError(f'{label} file is too large. Max size is {max_mb} MB')
    return file_size


def get_audio_book_upload_dir(book, *parts):
    upload_root = os.path.abspath(ConfigClass.AUDIOBOOK_UPLOAD_DIR)
    owner_folder = str(book.shcool_id) if book.shcool_id is not None else 'platform'
    upload_dir = os.path.join(upload_root, owner_folder, str(book.id), *[str(part) for part in parts])
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_uploaded_file(file_storage, upload_dir, prefix):
    original_filename = secure_filename(file_storage.filename)
    extension = get_file_extension(file_storage)
    stored_filename = f'{prefix}-{uuid4().hex}.{extension}'
    saved_file_path = os.path.join(upload_dir, stored_filename)
    file_storage.save(saved_file_path)
    return saved_file_path, original_filename


def remove_file_if_exists(file_path):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


def parse_alignment_json(value):
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            raise ValueError('alignment_json must be valid JSON')
    raise ValueError('alignment_json must be an object')


def validate_alignment_json(alignment, audio_duration_ms=None, official_text=None):
    if not isinstance(alignment, dict):
        raise ValueError('alignment_json must be an object')

    if alignment.get('version') != 1:
        raise ValueError('alignment_json.version must be 1')

    alignment_official_text = alignment.get('officialText')
    if not isinstance(alignment_official_text, str) or not alignment_official_text.strip():
        raise ValueError('alignment_json.officialText is required')

    if official_text is not None and alignment_official_text.strip() != official_text.strip():
        raise ValueError('alignment_json.officialText must match official_text')

    alignment_duration = alignment.get('audioDurationMs')
    if alignment_duration is not None:
        try:
            alignment_duration = int(alignment_duration)
        except (TypeError, ValueError):
            raise ValueError('alignment_json.audioDurationMs must be a number')
        if alignment_duration < 0:
            raise ValueError('alignment_json.audioDurationMs must be greater than or equal to 0')
        if audio_duration_ms is None:
            audio_duration_ms = alignment_duration

    words = alignment.get('words')
    if not isinstance(words, list):
        raise ValueError('alignment_json.words must be an array')

    previous_index = -1
    for word in words:
        if not isinstance(word, dict):
            raise ValueError('alignment_json.words items must be objects')
        index = word.get('index')
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise ValueError('alignment word index must be a number')
        if index <= previous_index:
            raise ValueError('alignment word indexes must be ordered')
        previous_index = index

        if not isinstance(word.get('text'), str):
            raise ValueError('alignment word text is required')

        status = word.get('status')
        if status not in ALIGNMENT_WORD_STATUSES:
            raise ValueError('alignment word status is invalid')

        start_ms = word.get('startMs')
        end_ms = word.get('endMs')
        if status == 'not-spoken' and (start_ms is None or end_ms is None):
            continue
        try:
            start_ms = int(start_ms)
            end_ms = int(end_ms)
        except (TypeError, ValueError):
            raise ValueError('alignment word timestamps must be numbers')
        if start_ms < 0:
            raise ValueError('alignment word startMs must be greater than or equal to 0')
        if end_ms < start_ms:
            raise ValueError('alignment word endMs must be greater than or equal to startMs')
        if audio_duration_ms is not None and end_ms > audio_duration_ms:
            raise ValueError('alignment word endMs cannot exceed audioDurationMs')

    return True


def parse_audio_duration_ms(data):
    value = data.get('audio_duration_ms') or data.get('audioDurationMs')
    if value is None or value == '':
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError('audio_duration_ms must be a number')
    if value < 0:
        raise ValueError('audio_duration_ms must be greater than or equal to 0')
    return value


def parse_similarity(data, alignment=None):
    value = data.get('similarity')
    if value is None and alignment:
        value = alignment.get('similarity')
    if value is None or value == '':
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('similarity must be a number')
    if value < 0 or value > 1:
        raise ValueError('similarity must be between 0 and 1')
    return value


def parse_page_number(data):
    page_number = data.get('page_number') or data.get('pageNumber')
    if page_number is None:
        raise ValueError('page_number is required')
    return get_positive_int(page_number, 'page_number')


def parse_page_display_settings(data, page=None):
    image_position = (
        data.get('image_position')
        or data.get('imagePosition')
        or getattr(page, 'image_position', None)
        or 'above'
    )
    image_position = str(image_position).strip().lower()
    if image_position not in PAGE_IMAGE_POSITIONS:
        raise ValueError('image_position must be above or below')

    font_size = data.get('font_size') or data.get('fontSize')
    if font_size is None or font_size == '':
        font_size = getattr(page, 'font_size', None) or 18
    try:
        font_size = int(font_size)
    except (TypeError, ValueError):
        raise ValueError('font_size must be a number')
    if font_size < MIN_PAGE_FONT_SIZE or font_size > MAX_PAGE_FONT_SIZE:
        raise ValueError(
            f'font_size must be between {MIN_PAGE_FONT_SIZE} and {MAX_PAGE_FONT_SIZE}'
        )
    return image_position, font_size


def parse_bool_value(value, default=None):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in ['true', '1', 'yes']:
        return True
    if value in ['false', '0', 'no']:
        return False
    raise ValueError('Boolean value is invalid')


def page_status_from_alignment(alignment):
    review = alignment.get('review') if isinstance(alignment, dict) else None
    if isinstance(review, dict) and review.get('requiresReview'):
        return 'review-required'
    return 'ready'


def parse_review_confirmed(data):
    for key in [
        'reviewed',
        'reviewed_timestamps',
        'reviewedTimestamped',
        'review_confirmed',
        'reviewConfirmed',
    ]:
        if key in data:
            return parse_bool_value(data.get(key), default=False)
    return False


def mark_alignment_reviewed(alignment, role=None):
    if not isinstance(alignment, dict):
        return alignment

    reviewed_alignment = dict(alignment)
    review = reviewed_alignment.get('review')
    if not isinstance(review, dict):
        review = {}
    else:
        review = dict(review)

    reviewed_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace('+00:00', 'Z')
    )
    review['requiresReview'] = False
    review['reviewedTimestampedAt'] = reviewed_at
    review['reviewedAt'] = reviewed_at
    review['reviewedByRole'] = role

    try:
        if current_user and current_user.is_authenticated:
            review['reviewedById'] = current_user.id
            review['reviewedByRole'] = role or current_user.type
    except RuntimeError:
        pass

    reviewed_alignment['review'] = review
    reviewed_words = []
    for word in reviewed_alignment.get('words') or []:
        if not isinstance(word, dict):
            reviewed_words.append(word)
            continue
        if word.get('status') != 'interpolated':
            reviewed_words.append(word)
            continue
        reviewed_word = dict(word)
        reviewed_word['status'] = 'manually-edited'
        reviewed_words.append(reviewed_word)
    reviewed_alignment['words'] = reviewed_words
    return reviewed_alignment


def is_page_number_duplicate_error(error):
    message = str(getattr(error, 'orig', error))
    return (
        'uq_audio_book_page_number' in message or
        ('Duplicate entry' in message and 'audio_book_page' in str(error))
    )


def get_upload_file(*names):
    for name in names:
        file_storage = request.files.get(name)
        if file_storage and file_storage.filename:
            return file_storage
    return None


def save_cover_image(book):
    cover_file = get_upload_file('cover_image', 'cover', 'image')
    if not cover_file:
        return None
    if not is_allowed_image_file(cover_file):
        raise ValueError('Only jpg, jpeg, png, or webp cover images are allowed')
    validate_upload_size(cover_file, ConfigClass.MAX_AUDIOBOOK_IMAGE_UPLOAD_MB, 'Cover image')
    saved_file_path, _ = save_uploaded_file(cover_file, get_audio_book_upload_dir(book, 'cover'), 'cover')
    old_path = book.cover_image_path
    book.cover_image_path = saved_file_path
    book.cover_image_url = f'/admin/audio-books/{book.id}/cover'
    remove_file_if_exists(old_path)
    return saved_file_path


def save_page_image(book, page):
    image_file = get_upload_file('image', 'page_image', 'pageImage')
    if not image_file:
        return None
    if not is_allowed_image_file(image_file):
        raise ValueError('Only jpg, jpeg, png, or webp page images are allowed')
    file_size = validate_upload_size(image_file, ConfigClass.MAX_AUDIOBOOK_IMAGE_UPLOAD_MB, 'Page image')
    saved_file_path, _ = save_uploaded_file(image_file, get_audio_book_upload_dir(book, 'pages', page.id), 'image')
    old_path = page.image_path
    page.image_path = saved_file_path
    page.image_url = f'/admin/audio-books/{book.id}/pages/{page.id}/image'
    page.image_mime_type = image_file.mimetype or None
    page.image_file_size = file_size
    remove_file_if_exists(old_path)
    return saved_file_path


def save_page_audio(book, page):
    audio_file = get_upload_file('audio', 'audio_file', 'audioFile')
    if not audio_file:
        return None
    if not is_allowed_audio_file(audio_file):
        raise ValueError('Only mp3, wav, m4a, webm, or ogg audio files are allowed')
    file_size = validate_upload_size(audio_file, ConfigClass.MAX_AUDIOBOOK_AUDIO_UPLOAD_MB, 'Audio')
    saved_file_path, _ = save_uploaded_file(audio_file, get_audio_book_upload_dir(book, 'pages', page.id), 'audio')
    old_path = page.audio_path
    page.audio_path = saved_file_path
    page.audio_url = f'/admin/audio-books/{book.id}/pages/{page.id}/audio'
    page.audio_mime_type = audio_file.mimetype or None
    page.audio_file_size = file_size
    remove_file_if_exists(old_path)
    return saved_file_path


def active_pages_query(book):
    return AudioBookPage.query.filter_by(audio_book_id=book.id, active=True).order_by(AudioBookPage.page_number.asc())


def approved_pages_query(book):
    return (
        AudioBookPage.query
        .filter_by(audio_book_id=book.id, active=True, alignment_status='approved')
        .order_by(AudioBookPage.page_number.asc())
    )


def pages_query_for_role(book, role='admin'):
    return approved_pages_query(book) if role == 'reader' else active_pages_query(book)


def mark_audio_book_draft_for_content_change(book):
    if book and getattr(book, 'status', None) == 'published':
        book.status = 'draft'
        book.published_at = None


def get_audio_book_progress(book_id):
    if not current_user.is_authenticated:
        return None
    return AudioBookProgress.query.filter_by(user_id=current_user.id, audio_book_id=book_id).first()


def serialize_progress(progress):
    if not progress:
        return {
            'current_page_number': 1,
            'current_time_ms': 0,
            'completed': False,
            'completed_at': None,
            'updated_at': None,
        }
    return {
        'current_page_number': progress.current_page_number,
        'current_time_ms': progress.current_time_ms,
        'completed': progress.completed,
        'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
        'updated_at': progress.updated_at.isoformat() if progress.updated_at else None,
    }


def serialize_audio_book_page(page, role='admin', include_alignment=True):
    book_id = page.audio_book_id
    if role == 'reader':
        image_url = f'/reader/audio-books/{book_id}/pages/{page.page_number}/image'
        audio_url = f'/reader/audio-books/{book_id}/pages/{page.page_number}/audio'
    elif role == 'teacher':
        image_url = f'/teacher/audio-books/{book_id}/pages/{page.id}/image'
        audio_url = f'/teacher/audio-books/{book_id}/pages/{page.id}/audio'
    else:
        image_url = f'/admin/audio-books/{book_id}/pages/{page.id}/image'
        audio_url = f'/admin/audio-books/{book_id}/pages/{page.id}/audio'

    data = {
        'id': page.id,
        'audio_book_id': page.audio_book_id,
        'page_number': page.page_number,
        'image_url': image_url if page.image_path else None,
        'audio_url': audio_url if page.audio_path else None,
        'official_text': page.official_text,
        'language': page.language,
        'audio_duration_ms': page.audio_duration_ms,
        'image_position': getattr(page, 'image_position', None) or 'above',
        'font_size': getattr(page, 'font_size', None) or 18,
        'alignment_status': page.alignment_status,
        'similarity': page.similarity,
        'image_mime_type': page.image_mime_type,
        'image_file_size': page.image_file_size,
        'audio_mime_type': page.audio_mime_type,
        'audio_file_size': page.audio_file_size,
        'active': page.active,
        'created_at': page.created_at.isoformat() if page.created_at else None,
        'updated_at': page.updated_at.isoformat() if page.updated_at else None,
    }
    if include_alignment:
        data['alignment_json'] = page.alignment_json
    return data


def serialize_audio_book(book, include_pages=False, role='admin'):
    pages_query = pages_query_for_role(book, role=role)
    pages = pages_query.all() if include_pages else []
    pages_count = len(pages) if include_pages else pages_query.count()
    approved_pages_count = (
        sum(1 for page in pages if page.alignment_status == 'approved')
        if include_pages else
        AudioBookPage.query.filter_by(audio_book_id=book.id, active=True, alignment_status='approved').count()
    )
    creator = User.query.get(book.created_by_id)
    source_book = Book.query.get(book.book_id) if book.book_id else None
    cover_url = None
    if book.cover_image_path:
        if role == 'reader':
            cover_url = f'/reader/audio-books/{book.id}/cover'
        elif role == 'teacher':
            cover_url = f'/teacher/audio-books/{book.id}/cover'
        else:
            cover_url = f'/admin/audio-books/{book.id}/cover'

    data = {
        'id': book.id,
        'title': book.title,
        'description': book.description,
        'cover_image_url': cover_url,
        'language': book.language,
        'level': book.level,
        'category': book.category,
        'book_id': book.book_id,
        'source_book': {
            'id': source_book.id,
            'title': source_book.title,
            'author': source_book.author,
            'school_id': source_book.shcool_id,
        } if source_book else None,
        'status': book.status,
        'school_id': book.shcool_id,
        'source': 'platform' if book.shcool_id is None else 'school',
        'created_by_id': book.created_by_id,
        'created_by_role': book.created_by_role,
        'creator': {
            'id': creator.id,
            'username': creator.username,
            'email': creator.email,
            'role': creator.type
        } if creator else None,
        'pages_count': pages_count,
        'approved_pages_count': approved_pages_count,
        'active': book.active,
        'published_at': book.published_at.isoformat() if book.published_at else None,
        'created_at': book.created_at.isoformat() if book.created_at else None,
        'updated_at': book.updated_at.isoformat() if book.updated_at else None,
    }
    if role == 'reader':
        data['progress'] = serialize_progress(get_audio_book_progress(book.id))
    if include_pages:
        data['pages'] = [serialize_audio_book_page(page, role=role) for page in pages]
    return data


def paginate_query(query, serializer, collection_name):
    page = get_positive_int(request.args.get('page', 1), 'page')
    per_page = min(get_positive_int(request.args.get('per_page', 20), 'per_page'), 100)
    total = query.order_by(None).count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    pages = (total + per_page - 1) // per_page if total else 0
    return {
        collection_name: [serializer(item) for item in items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
            'has_next': page < pages,
            'has_prev': page > 1,
            'max_per_page': 100,
        }
    }


def apply_audio_book_metadata(book, data, require_title=False):
    source_book_id = data.get('book_id') or data.get('bookId')
    source_book = None
    if source_book_id:
        source_book = get_manageable_source_book(
            get_positive_int(source_book_id, 'book_id'),
            school_id=book.shcool_id
        )
        if not source_book:
            raise PermissionError('Book not found or not accessible')
        book.book_id = source_book.id

    if require_title and not str(data.get('title') or '').strip():
        raise ValueError('Title is required')

    if 'title' in data:
        title = str(data.get('title') or getattr(source_book, 'title', '') or '').strip()
        if not title:
            raise ValueError('Title cannot be empty')
        book.title = title
    if 'description' in data:
        book.description = data.get('description', getattr(source_book, 'desc', None))
    if 'language' in data:
        language = str(data.get('language') or '').strip() or 'en'
        book.language = language[:20]
    if 'level' in data:
        book.level = data.get('level')
    if 'category' in data:
        book.category = data.get('category', getattr(source_book, 'category', None))
    return book


def create_audio_book_for_current_user():
    data = get_request_data()
    school_id = resolve_school_scope_for_creator()
    source_book_id = data.get('book_id') or data.get('bookId')
    source_book = None
    if not source_book_id:
        raise ValueError('book_id is required')
    source_book = get_manageable_source_book(
        get_positive_int(source_book_id, 'book_id'),
        school_id=school_id
    )
    if not source_book:
        raise PermissionError('Book not found or not accessible')
    book = AudioBook(
        title=str(data.get('title') or getattr(source_book, 'title', '') or '').strip(),
        description=data.get('description', getattr(source_book, 'desc', None)),
        language=str(data.get('language') or 'en').strip()[:20] or 'en',
        level=data.get('level'),
        category=data.get('category', getattr(source_book, 'category', None)),
        book_id=getattr(source_book, 'id', None),
        status='draft',
        shcool_id=school_id,
        created_by_id=current_user.id,
        created_by_role=current_user.type,
        active=True,
    )
    if not book.title:
        raise ValueError('Title is required')
    db.session.add(book)
    db.session.flush()
    save_cover_image(book)
    return book


def update_audio_book_for_current_user(book):
    data = get_request_data()
    apply_audio_book_metadata(book, data)
    save_cover_image(book)
    return book


def create_page_for_book(book):
    data = get_request_data()
    page_number = parse_page_number(data)
    official_text = str(data.get('official_text') or data.get('officialText') or '').strip()
    image_file = get_upload_file('image', 'page_image', 'pageImage')
    audio_file = get_upload_file('audio', 'audio_file', 'audioFile')
    if not audio_file:
        raise ValueError('Audio file is required')
    image_position, font_size = parse_page_display_settings(data)

    existing_page = AudioBookPage.query.filter_by(
        audio_book_id=book.id,
        page_number=page_number
    ).first()
    if existing_page and existing_page.active:
        raise ValueError('page_number already exists for this audiobook')

    if existing_page:
        page = existing_page
        page.official_text = official_text
        page.language = str(data.get('language') or book.language or 'en').strip()[:20] or 'en'
        page.audio_duration_ms = parse_audio_duration_ms(data)
        page.image_position = image_position
        page.font_size = font_size
        page.alignment_json = None
        page.alignment_status = 'draft'
        page.similarity = None
        page.active = True
    else:
        page = AudioBookPage(
            audio_book_id=book.id,
            page_number=page_number,
            official_text=official_text,
            language=str(data.get('language') or book.language or 'en').strip()[:20] or 'en',
            audio_duration_ms=parse_audio_duration_ms(data),
            image_position=image_position,
            font_size=font_size,
            alignment_status='draft',
            active=True,
        )
        db.session.add(page)

    db.session.flush()

    save_page_image(book, page)
    save_page_audio(book, page)

    alignment = parse_alignment_json(data.get('alignment_json') or data.get('alignmentJson'))
    if alignment:
        validation_text = page.official_text if page.official_text.strip() else None
        validate_alignment_json(alignment, page.audio_duration_ms, validation_text)
        if not page.official_text.strip():
            page.official_text = str(alignment.get('officialText') or '').strip()
        page.alignment_json = alignment
        page.similarity = parse_similarity(data, alignment)
        page.alignment_status = page_status_from_alignment(alignment)
    mark_audio_book_draft_for_content_change(book)
    return page


def update_page_for_book(book, page):
    data = get_request_data()
    reset_alignment = False

    if 'page_number' in data or 'pageNumber' in data:
        new_page_number = parse_page_number(data)
        existing = AudioBookPage.query.filter(
            AudioBookPage.audio_book_id == book.id,
            AudioBookPage.page_number == new_page_number,
            AudioBookPage.id != page.id
        ).first()
        if existing:
            raise ValueError('page_number already exists for this audiobook')
        page.page_number = new_page_number

    if 'official_text' in data or 'officialText' in data:
        official_text = str(data.get('official_text') or data.get('officialText') or '').strip()
        if official_text != page.official_text:
            reset_alignment = True
            page.official_text = official_text

    if 'language' in data:
        page.language = str(data.get('language') or book.language or 'en').strip()[:20] or 'en'

    if 'audio_duration_ms' in data or 'audioDurationMs' in data:
        page.audio_duration_ms = parse_audio_duration_ms(data)

    if (
        'image_position' in data or
        'imagePosition' in data or
        'font_size' in data or
        'fontSize' in data
    ):
        page.image_position, page.font_size = parse_page_display_settings(data, page=page)

    if get_upload_file('image', 'page_image', 'pageImage'):
        save_page_image(book, page)

    if get_upload_file('audio', 'audio_file', 'audioFile'):
        save_page_audio(book, page)
        reset_alignment = True

    alignment = parse_alignment_json(data.get('alignment_json') or data.get('alignmentJson'))
    if alignment:
        validation_text = page.official_text if page.official_text.strip() else None
        validate_alignment_json(alignment, page.audio_duration_ms, validation_text)
        if not page.official_text.strip():
            page.official_text = str(alignment.get('officialText') or '').strip()
        page.alignment_json = alignment
        page.similarity = parse_similarity(data, alignment)
        page.alignment_status = page_status_from_alignment(alignment)
        mark_audio_book_draft_for_content_change(book)
    elif reset_alignment:
        page.alignment_json = None
        page.similarity = None
        page.alignment_status = 'draft'
        mark_audio_book_draft_for_content_change(book)

    return page


def save_page_alignment(book, page):
    data = get_request_data()
    alignment = parse_alignment_json(data.get('alignment_json') or data.get('alignmentJson') or data)
    validation_text = page.official_text if str(page.official_text or '').strip() else None
    validate_alignment_json(alignment, page.audio_duration_ms, validation_text)
    if not str(page.official_text or '').strip():
        page.official_text = str(alignment.get('officialText') or '').strip()
    if parse_review_confirmed(data):
        alignment = mark_alignment_reviewed(alignment)
    page.alignment_json = alignment
    page.similarity = parse_similarity(data, alignment)
    page.alignment_status = page_status_from_alignment(alignment)
    mark_audio_book_draft_for_content_change(book)
    return page


def parse_model_alignment_options():
    data = get_request_data()
    options = {}
    if data.get('model'):
        options['model'] = str(data.get('model')).strip()
    if data.get('device'):
        options['device'] = str(data.get('device')).strip()
    if 'vad' in data:
        options['vad'] = parse_bool_value(data.get('vad'), default=None)
    return options


def should_generate_text_from_audio(page):
    data = get_request_data()
    for key in [
        'source_text_from_audio',
        'sourceTextFromAudio',
        'generate_text_from_audio',
        'generateTextFromAudio',
        'replace_text_from_audio',
        'replaceTextFromAudio',
    ]:
        if key in data:
            return parse_bool_value(data.get(key), default=False)
    return not bool(str(page.official_text or '').strip())


def generate_page_alignment(book, page):
    if not page.audio_path or not os.path.exists(page.audio_path):
        raise ValueError('Page audio is required before model alignment')

    options = parse_model_alignment_options()
    source_text_from_audio = should_generate_text_from_audio(page)
    official_text = None if source_text_from_audio else page.official_text
    if not source_text_from_audio and not str(official_text or '').strip():
        raise ValueError('Official text is required before model alignment')

    alignment = generate_model_alignment(
        page.audio_path,
        official_text,
        audio_duration_ms=page.audio_duration_ms,
        language=page.language or book.language,
        options=options,
    )
    alignment_text = str(alignment.get('officialText') or '').strip()
    if source_text_from_audio or not str(page.official_text or '').strip():
        page.official_text = alignment_text
    if alignment.get('audioDurationMs'):
        page.audio_duration_ms = max(
            int(page.audio_duration_ms or 0),
            int(alignment.get('audioDurationMs'))
        )

    validate_alignment_json(alignment, page.audio_duration_ms, page.official_text)
    page.alignment_json = alignment
    page.similarity = parse_similarity({}, alignment)
    page.alignment_status = page_status_from_alignment(alignment)
    mark_audio_book_draft_for_content_change(book)
    return page


def page_can_be_approved(page):
    if not page.audio_path:
        return False, 'Page audio is required before approval'
    if not page.official_text or not page.official_text.strip():
        return False, 'Official text is required before approval'
    if not page.alignment_json:
        return False, 'Alignment JSON is required before approval'
    validate_alignment_json(page.alignment_json, page.audio_duration_ms, page.official_text)
    review = page.alignment_json.get('review') if isinstance(page.alignment_json, dict) else None
    if isinstance(review, dict) and review.get('requiresReview'):
        return False, 'Alignment requires review before approval'
    for word in page.alignment_json.get('words') or []:
        if word.get('status') == 'interpolated':
            return False, 'Estimated timestamps cannot be approved. Generate model alignment or manually review timings first'
    return True, None


def publish_errors(book):
    pages = active_pages_query(book).all()
    errors = []
    if not pages:
        errors.append('Audiobook must have at least one page')
    for page in pages:
        if not page.audio_path:
            errors.append(f'Page {page.page_number} is missing audio')
        if not page.official_text or not page.official_text.strip():
            errors.append(f'Page {page.page_number} is missing official text')
        if page.alignment_status != 'approved':
            errors.append(f'Page {page.page_number} is not approved')
        if not page.alignment_json:
            errors.append(f'Page {page.page_number} is missing alignment JSON')
        else:
            try:
                validate_alignment_json(page.alignment_json, page.audio_duration_ms, page.official_text)
            except ValueError as error:
                errors.append(f'Page {page.page_number}: {error}')
    return errors


def list_books_query_for_current_admin():
    query = AudioBook.query.filter_by(active=True)
    source_book_id = request.args.get('book_id') or request.args.get('bookId')
    if source_book_id:
        query = query.filter(AudioBook.book_id == get_positive_int(source_book_id, 'book_id'))
    if is_super_admin():
        school_id = get_request_school_id()
        if school_id is not None:
            query = query.filter(AudioBook.shcool_id == school_id)
        source = request.args.get('source')
        if source == 'platform':
            query = query.filter(AudioBook.shcool_id.is_(None))
        elif source == 'school':
            query = query.filter(AudioBook.shcool_id.isnot(None))
        return query
    school_id = get_current_school_id()
    if not school_id:
        return query.filter(False)
    return query.filter(AudioBook.shcool_id == school_id)


def list_books_query_for_current_teacher():
    query = AudioBook.query.filter_by(active=True)
    source_book_id = request.args.get('book_id') or request.args.get('bookId')
    if source_book_id:
        query = query.filter(AudioBook.book_id == get_positive_int(source_book_id, 'book_id'))
    if is_super_admin():
        return query
    if current_user.type == 'admin':
        school_id = get_current_school_id()
        return query.filter(AudioBook.shcool_id == school_id) if school_id else query.filter(False)
    return query.filter(AudioBook.created_by_id == current_user.id)


def reader_can_access_audio_book(book):
    if not book or not book.active or book.status != 'published':
        return False
    if book.shcool_id is None:
        return current_user.is_authenticated
    return User_shcool.query.filter_by(user_id=current_user.id, shcool_id=book.shcool_id).first() is not None


def reader_audio_books_query():
    memberships = get_user_school_ids(current_user.id)
    query = (
        AudioBook.query
        .join(AudioBookPage, AudioBookPage.audio_book_id == AudioBook.id)
        .filter(
            AudioBook.active.is_(True),
            AudioBook.status == 'published',
            AudioBookPage.active.is_(True),
            AudioBookPage.alignment_status == 'approved',
        )
        .distinct()
    )
    selected_school_id = get_request_school_id()
    if selected_school_id:
        if selected_school_id not in memberships:
            raise PermissionError('You do not have access to this school')
        return query.filter(or_(AudioBook.shcool_id == selected_school_id, AudioBook.shcool_id.is_(None)))
    if memberships:
        return query.filter(or_(AudioBook.shcool_id.in_(memberships), AudioBook.shcool_id.is_(None)))
    return query.filter(AudioBook.shcool_id.is_(None))


def media_response(file_path, mimetype, missing_message):
    if not file_path or not os.path.exists(file_path):
        return jsonify({'message': missing_message}), 404
    return send_file(file_path, mimetype=mimetype, as_attachment=False)


def handle_create_book(role):
    try:
        book = create_audio_book_for_current_user()
        db.session.commit()
        return jsonify({
            'message': 'Audiobook created successfully',
            'audio_book': serialize_audio_book(book, include_pages=True, role=role)
        }), 201
    except PermissionError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except PermissionError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 403
    except IntegrityError as error:
        db.session.rollback()
        if is_page_number_duplicate_error(error):
            return jsonify({'message': 'page_number already exists for this audiobook'}), 400
        return jsonify({'message': 'Database constraint error', 'error': str(error)}), 409
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_list_books(query_builder, role):
    try:
        query = query_builder().order_by(AudioBook.updated_at.desc())
        status = request.args.get('status')
        if status:
            query = query.filter(AudioBook.status == status)
        return jsonify(paginate_query(query, lambda book: serialize_audio_book(book, role=role), 'audio_books')), 200
    except PermissionError as error:
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_get_source_book_audio_book(source_book_id, role):
    try:
        source_book = get_manageable_source_book(source_book_id)
        if not source_book:
            return jsonify({'message': 'Book not found'}), 404
        school_id = resolve_school_scope_for_source_book(source_book)
        book = get_audio_book_for_source_book(source_book, school_id)
        return jsonify({
            'source_book': serialize_source_book(source_book),
            'audio_book': serialize_audio_book(book, include_pages=True, role=role) if book else None,
        }), 200
    except PermissionError as error:
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_create_source_book_audio_book(source_book_id, role):
    try:
        source_book = get_manageable_source_book(source_book_id)
        if not source_book:
            return jsonify({'message': 'Book not found'}), 404
        school_id = resolve_school_scope_for_source_book(source_book)
        book = get_audio_book_for_source_book(source_book, school_id)
        created = False
        if not book:
            book = create_audio_book_from_source_book(source_book, school_id)
            created = True
        db.session.commit()
        return jsonify({
            'message': 'Audio story created successfully' if created else 'Audio story already exists',
            'source_book': serialize_source_book(source_book),
            'audio_book': serialize_audio_book(book, include_pages=True, role=role)
        }), 201 if created else 200
    except PermissionError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_get_book(book_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        return jsonify({'audio_book': serialize_audio_book(book, include_pages=True, role=role)}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_update_book(book_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        update_audio_book_for_current_user(book)
        db.session.commit()
        return jsonify({
            'message': 'Audiobook updated successfully',
            'audio_book': serialize_audio_book(book, include_pages=True, role=role)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except PermissionError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 403
    except IntegrityError as error:
        db.session.rollback()
        if is_page_number_duplicate_error(error):
            return jsonify({'message': 'page_number already exists for this audiobook'}), 400
        return jsonify({'message': 'Database constraint error', 'error': str(error)}), 409
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_delete_book(book_id):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        book.active = False
        book.status = 'archived'
        for page in active_pages_query(book).all():
            page.active = False
        db.session.commit()
        return jsonify({'message': 'Audiobook deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_create_page(book_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = create_page_for_book(book)
        db.session.commit()
        return jsonify({
            'message': 'Audiobook page created successfully',
            'page': serialize_audio_book_page(page, role=role)
        }), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_update_page(book_id, page_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        update_page_for_book(book, page)
        db.session.commit()
        return jsonify({
            'message': 'Audiobook page updated successfully',
            'page': serialize_audio_book_page(page, role=role)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_delete_page(book_id, page_id):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        page.active = False
        mark_audio_book_draft_for_content_change(book)
        db.session.commit()
        return jsonify({'message': 'Audiobook page deleted successfully'}), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_reorder_pages(book_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        data = get_request_data()
        page_ids = data.get('page_ids') or data.get('pageIds')
        if page_ids is None and isinstance(data.get('pages'), list):
            page_ids = [page.get('id') for page in data.get('pages')]
        if not isinstance(page_ids, list) or not page_ids:
            return jsonify({'message': 'page_ids array is required'}), 400

        pages_by_id = {page.id: page for page in active_pages_query(book).all()}
        clean_page_ids = [get_positive_int(page_id, 'page_id') for page_id in page_ids]
        if set(clean_page_ids) != set(pages_by_id.keys()):
            return jsonify({'message': 'page_ids must include every active page exactly once'}), 400

        for index, page_id in enumerate(clean_page_ids, start=1):
            pages_by_id[page_id].page_number = -index
        db.session.flush()
        for index, page_id in enumerate(clean_page_ids, start=1):
            pages_by_id[page_id].page_number = index
        mark_audio_book_draft_for_content_change(book)
        db.session.commit()
        return jsonify({
            'message': 'Audiobook pages reordered successfully',
            'pages': [serialize_audio_book_page(page, role=role) for page in active_pages_query(book).all()]
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_save_alignment(book_id, page_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        save_page_alignment(book, page)
        db.session.commit()
        return jsonify({
            'message': 'Alignment saved successfully',
            'page': serialize_audio_book_page(page, role=role)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_generate_alignment(book_id, page_id, role):
    page = None
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404

        page.alignment_status = 'processing-local'
        db.session.commit()

        generate_page_alignment(book, page)
        db.session.commit()
        return jsonify({
            'message': 'Model alignment generated successfully',
            'page': serialize_audio_book_page(page, role=role)
        }), 200
    except AudioAlignmentUnavailable as error:
        db.session.rollback()
        if page:
            page.alignment_status = 'failed'
            db.session.commit()
        return jsonify({'message': str(error)}), 503
    except (AudioAlignmentError, ValueError) as error:
        db.session.rollback()
        if page:
            page.alignment_status = 'failed'
            db.session.commit()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        if page:
            page.alignment_status = 'failed'
            db.session.commit()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_approve_page(book_id, page_id, role):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        data = get_request_data()
        if page.alignment_json and parse_review_confirmed(data):
            page.alignment_json = mark_alignment_reviewed(page.alignment_json, role=role)
        ok, message = page_can_be_approved(page)
        if not ok:
            return jsonify({'message': message}), 400
        page.alignment_status = 'approved'
        db.session.commit()
        return jsonify({
            'message': 'Audiobook page approved successfully',
            'page': serialize_audio_book_page(page, role=role)
        }), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_publish_book(book_id, publish=True, role='admin'):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        if publish:
            errors = publish_errors(book)
            if errors:
                return jsonify({'message': 'Audiobook cannot be published', 'errors': errors}), 400
            book.status = 'published'
            book.published_at = datetime.now()
            message = 'Audiobook published successfully'
        else:
            book.status = 'draft'
            book.published_at = None
            message = 'Audiobook unpublished successfully'
        db.session.commit()
        return jsonify({'message': message, 'audio_book': serialize_audio_book(book, include_pages=True, role=role)}), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_media(book_id, page_id, media_type, role='admin'):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        page = get_book_page(book, page_id)
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        if media_type == 'image':
            return media_response(page.image_path, page.image_mime_type, 'Page image file not found')
        return media_response(page.audio_path, page.audio_mime_type, 'Page audio file not found')
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


def handle_cover(book_id):
    try:
        book = get_manageable_audio_book(book_id)
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        return media_response(book.cover_image_path, None, 'Cover image file not found')
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@admin_audiobooks.route('/audio-books', methods=['POST'])
@login_required
@admin_required
def admin_create_audio_book():
    return handle_create_book('admin')


@admin_audiobooks.route('/audio-books', methods=['GET'])
@login_required
@admin_required
def admin_list_audio_books():
    return handle_list_books(list_books_query_for_current_admin, 'admin')


@admin_audiobooks.route('/books/<int:source_book_id>/audio-book', methods=['GET'])
@login_required
@admin_required
def admin_get_source_book_audio_book(source_book_id):
    return handle_get_source_book_audio_book(source_book_id, 'admin')


@admin_audiobooks.route('/books/<int:source_book_id>/audio-book', methods=['POST'])
@login_required
@admin_required
def admin_create_source_book_audio_book(source_book_id):
    return handle_create_source_book_audio_book(source_book_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>', methods=['GET'])
@login_required
@admin_required
def admin_get_audio_book(book_id):
    return handle_get_book(book_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>', methods=['PUT', 'PATCH'])
@login_required
@admin_required
def admin_update_audio_book(book_id):
    return handle_update_book(book_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_audio_book(book_id):
    return handle_delete_book(book_id)


@admin_audiobooks.route('/audio-books/<int:book_id>/cover', methods=['GET'])
@login_required
@admin_required
def admin_get_audio_book_cover(book_id):
    return handle_cover(book_id)


@admin_audiobooks.route('/audio-books/<int:book_id>/pages', methods=['POST'])
@login_required
@admin_required
def admin_create_audio_book_page(book_id):
    return handle_create_page(book_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>', methods=['PUT', 'PATCH'])
@login_required
@admin_required
def admin_update_audio_book_page(book_id, page_id):
    return handle_update_page(book_id, page_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_audio_book_page(book_id, page_id):
    return handle_delete_page(book_id, page_id)


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/reorder', methods=['PUT', 'PATCH'])
@login_required
@admin_required
def admin_reorder_audio_book_pages(book_id):
    return handle_reorder_pages(book_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/alignment', methods=['PUT', 'PATCH'])
@login_required
@admin_required
def admin_save_audio_book_alignment(book_id, page_id):
    return handle_save_alignment(book_id, page_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/generate-alignment', methods=['POST'])
@login_required
@admin_required
def admin_generate_audio_book_alignment(book_id, page_id):
    return handle_generate_alignment(book_id, page_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/approve', methods=['POST'])
@login_required
@admin_required
def admin_approve_audio_book_page(book_id, page_id):
    return handle_approve_page(book_id, page_id, 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/publish', methods=['POST'])
@login_required
@admin_required
def admin_publish_audio_book(book_id):
    return handle_publish_book(book_id, publish=True, role='admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/unpublish', methods=['POST'])
@login_required
@admin_required
def admin_unpublish_audio_book(book_id):
    return handle_publish_book(book_id, publish=False, role='admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/image', methods=['GET'])
@login_required
@admin_required
def admin_get_audio_book_page_image(book_id, page_id):
    return handle_media(book_id, page_id, 'image', 'admin')


@admin_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/audio', methods=['GET'])
@login_required
@admin_required
def admin_get_audio_book_page_audio(book_id, page_id):
    return handle_media(book_id, page_id, 'audio', 'admin')


@teacher_audiobooks.route('/audio-books', methods=['POST'])
@login_required
@teacher_required
def teacher_create_audio_book():
    return handle_create_book('teacher')


@teacher_audiobooks.route('/audio-books', methods=['GET'])
@login_required
@teacher_required
def teacher_list_audio_books():
    return handle_list_books(list_books_query_for_current_teacher, 'teacher')


@teacher_audiobooks.route('/books/<int:source_book_id>/audio-book', methods=['GET'])
@login_required
@teacher_required
def teacher_get_source_book_audio_book(source_book_id):
    return handle_get_source_book_audio_book(source_book_id, 'teacher')


@teacher_audiobooks.route('/books/<int:source_book_id>/audio-book', methods=['POST'])
@login_required
@teacher_required
def teacher_create_source_book_audio_book(source_book_id):
    return handle_create_source_book_audio_book(source_book_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>', methods=['GET'])
@login_required
@teacher_required
def teacher_get_audio_book(book_id):
    return handle_get_book(book_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>', methods=['PUT', 'PATCH'])
@login_required
@teacher_required
def teacher_update_audio_book(book_id):
    return handle_update_book(book_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>', methods=['DELETE'])
@login_required
@teacher_required
def teacher_delete_audio_book(book_id):
    return handle_delete_book(book_id)


@teacher_audiobooks.route('/audio-books/<int:book_id>/cover', methods=['GET'])
@login_required
@teacher_required
def teacher_get_audio_book_cover(book_id):
    return handle_cover(book_id)


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages', methods=['POST'])
@login_required
@teacher_required
def teacher_create_audio_book_page(book_id):
    return handle_create_page(book_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>', methods=['PUT', 'PATCH'])
@login_required
@teacher_required
def teacher_update_audio_book_page(book_id, page_id):
    return handle_update_page(book_id, page_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>', methods=['DELETE'])
@login_required
@teacher_required
def teacher_delete_audio_book_page(book_id, page_id):
    return handle_delete_page(book_id, page_id)


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/reorder', methods=['PUT', 'PATCH'])
@login_required
@teacher_required
def teacher_reorder_audio_book_pages(book_id):
    return handle_reorder_pages(book_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/alignment', methods=['PUT', 'PATCH'])
@login_required
@teacher_required
def teacher_save_audio_book_alignment(book_id, page_id):
    return handle_save_alignment(book_id, page_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/generate-alignment', methods=['POST'])
@login_required
@teacher_required
def teacher_generate_audio_book_alignment(book_id, page_id):
    return handle_generate_alignment(book_id, page_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/approve', methods=['POST'])
@login_required
@teacher_required
def teacher_approve_audio_book_page(book_id, page_id):
    return handle_approve_page(book_id, page_id, 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/publish', methods=['POST'])
@login_required
@teacher_required
def teacher_publish_audio_book(book_id):
    return handle_publish_book(book_id, publish=True, role='teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/unpublish', methods=['POST'])
@login_required
@teacher_required
def teacher_unpublish_audio_book(book_id):
    return handle_publish_book(book_id, publish=False, role='teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/image', methods=['GET'])
@login_required
@teacher_required
def teacher_get_audio_book_page_image(book_id, page_id):
    return handle_media(book_id, page_id, 'image', 'teacher')


@teacher_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_id>/audio', methods=['GET'])
@login_required
@teacher_required
def teacher_get_audio_book_page_audio(book_id, page_id):
    return handle_media(book_id, page_id, 'audio', 'teacher')


@reader_audiobooks.route('/audio-books', methods=['GET'])
@login_required
def reader_list_audio_books():
    try:
        query = reader_audio_books_query().order_by(AudioBook.updated_at.desc())
        return jsonify(paginate_query(query, lambda book: serialize_audio_book(book, role='reader'), 'audio_books')), 200
    except PermissionError as error:
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>', methods=['GET'])
@login_required
def reader_get_audio_book(book_id):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        return jsonify({'audio_book': serialize_audio_book(book, include_pages=True, role='reader')}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/books/<int:source_book_id>/audio-book', methods=['GET'])
@login_required
def reader_get_source_book_audio_book(source_book_id):
    try:
        book = (
            reader_audio_books_query()
            .filter(AudioBook.book_id == source_book_id)
            .order_by(AudioBook.updated_at.desc())
            .first()
        )
        if not book:
            return jsonify({'message': 'Audiobook not found'}), 404
        return jsonify({'audio_book': serialize_audio_book(book, include_pages=True, role='reader')}), 200
    except PermissionError as error:
        return jsonify({'message': str(error)}), 403
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>/cover', methods=['GET'])
@login_required
def reader_get_audio_book_cover(book_id):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        return media_response(book.cover_image_path, None, 'Cover image file not found')
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_number>', methods=['GET'])
@login_required
def reader_get_audio_book_page(book_id, page_number):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        page = AudioBookPage.query.filter_by(
            audio_book_id=book.id,
            page_number=page_number,
            active=True,
            alignment_status='approved'
        ).first()
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        return jsonify({'page': serialize_audio_book_page(page, role='reader')}), 200
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_number>/image', methods=['GET'])
@login_required
def reader_get_audio_book_page_image(book_id, page_number):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        page = AudioBookPage.query.filter_by(
            audio_book_id=book.id,
            page_number=page_number,
            active=True,
            alignment_status='approved'
        ).first()
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        return media_response(page.image_path, page.image_mime_type, 'Page image file not found')
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>/pages/<int:page_number>/audio', methods=['GET'])
@login_required
def reader_get_audio_book_page_audio(book_id, page_number):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        page = AudioBookPage.query.filter_by(
            audio_book_id=book.id,
            page_number=page_number,
            active=True,
            alignment_status='approved'
        ).first()
        if not page:
            return jsonify({'message': 'Audiobook page not found'}), 404
        return media_response(page.audio_path, page.audio_mime_type, 'Page audio file not found')
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


@reader_audiobooks.route('/audio-books/<int:book_id>/progress', methods=['POST', 'PUT'])
@login_required
def reader_update_audio_book_progress(book_id):
    try:
        book = AudioBook.query.filter_by(id=book_id, active=True).first()
        if not reader_can_access_audio_book(book):
            return jsonify({'message': 'Audiobook not found'}), 404
        data = get_request_data()

        progress = AudioBookProgress.query.filter_by(user_id=current_user.id, audio_book_id=book.id).first()
        if not progress:
            progress = AudioBookProgress(user_id=current_user.id, audio_book_id=book.id)
            db.session.add(progress)

        if 'current_page_number' in data or 'currentPageNumber' in data:
            progress.current_page_number = get_positive_int(
                data.get('current_page_number') or data.get('currentPageNumber'),
                'current_page_number'
            )
        if 'current_time_ms' in data or 'currentTimeMs' in data:
            current_time_ms = int(data.get('current_time_ms') or data.get('currentTimeMs') or 0)
            if current_time_ms < 0:
                return jsonify({'message': 'current_time_ms must be greater than or equal to 0'}), 400
            progress.current_time_ms = current_time_ms
        if 'completed' in data:
            progress.completed = parse_bool_value(data.get('completed'), default=False)
            if progress.completed and not progress.completed_at:
                progress.completed_at = datetime.now()
        progress.updated_at = datetime.now()
        db.session.commit()
        return jsonify({'progress': serialize_progress(progress)}), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500
