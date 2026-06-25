import os
from uuid import uuid4

from flask import Blueprint,abort,jsonify,request
from flask_login import login_required,current_user

from models.user import Teacher
from models.book import Book
from models.book_pack import Book_pack
from models.book_story import BookStory
from models.pack import Pack
from models.school_book_instance import SchoolBookInstance
from models.session import Session
from models.user_shcool import User_shcool

from functools import wraps
from apps.reader.routes import bcrypt
from apps.jitsi import is_online_session, serialize_jitsi_call
from extensions import db
from config import ConfigClass
from werkzeug.utils import secure_filename

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.type not in ['teacher','admin']:
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function


teacher = Blueprint('teacher', __name__, url_prefix='/teacher')

def parse_bool_value(value, name):
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f'{name} is required')
    value = str(value).strip().lower()
    if value in ['true', '1', 'yes']:
        return True
    if value in ['false', '0', 'no']:
        return False
    raise ValueError(f'{name} must be true or false')

def get_positive_int_arg(name, default_value):
    value = request.args.get(name, default_value)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number')
    if value < 1:
        raise ValueError(f'{name} must be greater than 0')
    return value

def get_teacher_school_ids():
    memberships = User_shcool.query.filter_by(user_id=current_user.id).all()
    return [membership.shcool_id for membership in memberships]

def get_teacher_book(book_id):
    school_ids = get_teacher_school_ids()
    if not school_ids:
        return None
    return (
        db.session.query(Book)
        .outerjoin(Book_pack, Book.id == Book_pack.book_id)
        .outerjoin(Pack, Book_pack.pack_id == Pack.id)
        .outerjoin(
            SchoolBookInstance,
            (SchoolBookInstance.book_id == Book.id) &
            (SchoolBookInstance.shcool_id.in_(school_ids)) &
            (SchoolBookInstance.active.is_(True))
        )
        .filter(
            Book.id == book_id,
            Book.active.is_(True),
            (
                Book.shcool_id.in_(school_ids) |
                Pack.shcool_id.in_(school_ids) |
                (SchoolBookInstance.id.isnot(None))
            )
        )
        .first()
    )

def get_teacher_book_school_id(book_id):
    school_ids = get_teacher_school_ids()
    if not school_ids:
        return None
    book = Book.query.get(book_id)
    if book and book.shcool_id in school_ids:
        return book.shcool_id
    instance = SchoolBookInstance.query.filter(
        SchoolBookInstance.book_id == book_id,
        SchoolBookInstance.shcool_id.in_(school_ids),
        SchoolBookInstance.active.is_(True)
    ).first()
    if instance:
        return instance.shcool_id
    pack = (
        db.session.query(Pack)
        .join(Book_pack, Pack.id == Book_pack.pack_id)
        .filter(Book_pack.book_id == book_id, Pack.shcool_id.in_(school_ids))
        .first()
    )
    return pack.shcool_id if pack else None

def get_teacher_story(story_id):
    school_ids = get_teacher_school_ids()
    if not school_ids:
        return None
    return BookStory.query.filter(BookStory.id == story_id, BookStory.shcool_id.in_(school_ids)).first()

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
    upload_dir = os.path.join(upload_root, str(school_id), str(book_id))
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

def serialize_book_story(story):
    return {
        'id': story.id,
        'book_id': story.book_id,
        'school_id': story.shcool_id,
        'source': 'platform' if story.shcool_id is None else 'school',
        'read_only': story.shcool_id is None,
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

def paginate_query(query, serializer, collection_name):
    page = get_positive_int_arg('page', 1)
    per_page = min(get_positive_int_arg('per_page', 20), 100)
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
            'max_per_page': 100
        }
    }

@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    Teacher.query.filter_by(email=current_user.email).first()

    return jsonify({
        'username':current_user.username,
        'email':current_user.email,
        'description':current_user.description,
        'study_level':current_user.study_level
        }),200

@teacher.route('/sessions/<int:session_id>/video-call', methods=['GET'])
@login_required
@teacher_required
def get_teacher_session_video_call(session_id):
    try:
        session = Session.query.get(session_id)
        if not session:
            return jsonify({'message': 'Session not found'}), 404
        if session.teacher_id != current_user.id:
            return jsonify({'message': 'You are not assigned to this session'}), 403
        if not is_online_session(session):
            return jsonify({'message': 'Video call is available only for online sessions'}), 400

        call_data = serialize_jitsi_call(session, current_user, is_moderator=True)
        db.session.commit()
        return jsonify(call_data), 200
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@teacher.route('/books/<int:book_id>/stories', methods=['GET'])
@login_required
@teacher_required
def get_teacher_book_stories(book_id):
    try:
        book = get_teacher_book(book_id)
        school_id = get_teacher_book_school_id(book_id)
        if not book or not school_id:
            return jsonify({'message': 'Book not found'}), 404

        if getattr(book, 'is_platform_book', False):
            stories_query = BookStory.query.filter(
                BookStory.book_id == book.id,
                BookStory.shcool_id.is_(None)
            ).order_by(BookStory.id.desc())
        else:
            stories_query = BookStory.query.filter_by(book_id=book.id, shcool_id=school_id).order_by(BookStory.id.desc())
        return jsonify(paginate_query(stories_query, serialize_book_story, 'stories')), 200
    except ValueError as error:
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@teacher.route('/books/<int:book_id>/stories', methods=['POST'])
@login_required
@teacher_required
def upload_teacher_book_story(book_id):
    saved_file_path = None
    try:
        book = get_teacher_book(book_id)
        school_id = get_teacher_book_school_id(book_id)
        if not book or not school_id:
            return jsonify({'message': 'Book not found'}), 404
        if getattr(book, 'is_platform_book', False):
            return jsonify({'message': 'IRead platform story PDFs are read-only for teachers'}), 403
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
            file_url='',
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
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@teacher.route('/stories/<int:story_id>', methods=['PUT'])
@login_required
@teacher_required
def update_teacher_book_story(story_id):
    try:
        story = get_teacher_story(story_id)
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
        return jsonify({'message': 'Story updated successfully', 'story': serialize_book_story(story)}), 200
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500

@teacher.route('/stories/<int:story_id>', methods=['DELETE'])
@login_required
@teacher_required
def delete_teacher_book_story(story_id):
    try:
        story = get_teacher_story(story_id)
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
