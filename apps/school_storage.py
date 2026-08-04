## @file
# Storage management API for the school-admin and super-admin dashboards.
#
# Gives an admin the three things the old Cloudinary setup never did: see how
# much disk their school is using, browse what has already been uploaded, and
# reuse an existing file instead of uploading the same cover twice. The image
# pickers throughout the dashboard read from these same endpoints, which is why
# the listing supports category filtering and search rather than only totals.
#
# Every route here is school-scoped through get_current_school_id(); a school
# admin can never name another school's id. Super-admins additionally get the
# platform folder and a cross-school overview, since they own platform assets
# and are the ones who raise a school's quota.
import os

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from apps.admin.routes import (
    admin_assistant_or_content_required,
    admin_or_assistant_required,
    admin_required,
    can_manage_content,
    get_current_school_id,
    is_super_admin,
    log_admin_action,
)
from apps.storage import (
    StorageError,
    absolute_path,
    delete_file,
    ensure_school_tree,
    owner_folder,
    save_upload,
    serialize_categories,
    serialize_file,
    usage_summary,
    validate_category,
)
from config import ConfigClass
from extensions import db
from models.school_file import STORAGE_CATEGORIES, SchoolFile
from models.shcool import Shcool
from models.user import User

storage_api = Blueprint('storage_api', __name__, url_prefix='/admin/storage')

DEFAULT_PER_PAGE = 24
MAX_PER_PAGE = 100


## @brief Which storage folder the caller is acting on.
#
# A school admin always gets their own school. Platform-wide roles (super admin,
# content manager) may pass `?scope=platform` to work in the platform folder,
# which is where covers for platform-wide books and ready-made packs belong --
# without it they would have no way to upload an asset that is not owned by one
# particular school.
#
# @return the school id, or None for the platform folder.
# @raises StorageError when a school-scoped role asks for the platform scope, or
#         when an admin has no school membership at all.
def resolve_scope():
    scope = (request.args.get('scope') or request.form.get('scope') or '').strip().lower()
    if scope == 'platform':
        if not can_manage_content():
            raise StorageError('Only a platform administrator can manage platform storage.')
        return None

    school_id = get_current_school_id()
    if school_id is None:
        if can_manage_content():
            # Platform roles usually have no school membership, so the platform
            # folder is the sensible default rather than an error.
            return None
        raise StorageError('Your account is not linked to a school.')
    return school_id


## @brief Fetch one file inside the caller's own scope.
#
# Filtering on the scope in the query (rather than checking after loading) is
# what makes a guessed id from another school return 404 instead of leaking that
# the file exists.
def get_scoped_file(file_id, school_id):
    query = SchoolFile.query.filter_by(id=file_id)
    if school_id is None:
        query = query.filter(SchoolFile.shcool_id.is_(None))
    else:
        query = query.filter(SchoolFile.shcool_id == school_id)
    return query.first()


def storage_error_response(error):
    return jsonify({'message': str(error)}), 400


## @brief Disk usage and quota for the caller's storage folder.
#
# Also returns the category catalogue so the dashboard renders its sections and
# its "accepted types / max size" hints from the limits the API actually
# enforces, instead of a duplicated copy in JavaScript.
@storage_api.route('/usage', methods=['GET'])
@login_required
@admin_assistant_or_content_required
def get_storage_usage():
    try:
        school_id = resolve_scope()
    except StorageError as error:
        return storage_error_response(error)

    try:
        summary = usage_summary(school_id)
        school = Shcool.query.get(school_id) if school_id is not None else None
        summary['school_name'] = school.name if school else 'Platform'
        summary['scope'] = 'platform' if school_id is None else 'school'
        summary['folder'] = owner_folder(school_id)
        summary['quota_mb'] = summary['quota_bytes'] // (1024 * 1024)
        summary['categories_meta'] = serialize_categories()
        return jsonify(summary), 200
    except Exception as error:
        return jsonify({'message': 'Unable to load storage usage: %s' % error}), 500


## @brief Browse the caller's stored files.
#
# Paginated because a school with a full audiobook library has thousands of
# files, and the image pickers open straight onto this listing.
#
# Query: category, q (search), page, per_page, kind (image|audio|document).
@storage_api.route('/files', methods=['GET'])
@login_required
@admin_assistant_or_content_required
def list_storage_files():
    try:
        school_id = resolve_scope()
    except StorageError as error:
        return storage_error_response(error)

    try:
        query = SchoolFile.query.filter(SchoolFile.active.is_(True))
        if school_id is None:
            query = query.filter(SchoolFile.shcool_id.is_(None))
        else:
            query = query.filter(SchoolFile.shcool_id == school_id)

        category = (request.args.get('category') or '').strip()
        if category:
            # Accept a category prefix ('stories') as well as a full bucket
            # ('stories/audio'), so the UI can offer a group-level filter
            # without the API needing a separate parameter for it.
            if category in STORAGE_CATEGORIES:
                query = query.filter(SchoolFile.category == category)
            else:
                query = query.filter(SchoolFile.category.like('%s/%%' % category.rstrip('/')))

        kind = (request.args.get('kind') or '').strip().lower()
        if kind == 'image':
            query = query.filter(SchoolFile.category.in_(
                ['stories/images', 'books/covers', 'packs/images', 'general']
            ))
        elif kind == 'audio':
            query = query.filter(SchoolFile.category == 'stories/audio')
        elif kind == 'document':
            query = query.filter(SchoolFile.category.in_(['books/files', 'general']))

        search = (request.args.get('q') or '').strip()
        if search:
            pattern = '%%%s%%' % search
            query = query.filter(or_(
                SchoolFile.original_filename.ilike(pattern),
                SchoolFile.title.ilike(pattern)
            ))

        try:
            page = max(int(request.args.get('page') or 1), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = int(request.args.get('per_page') or DEFAULT_PER_PAGE)
        except (TypeError, ValueError):
            per_page = DEFAULT_PER_PAGE
        per_page = min(max(per_page, 1), MAX_PER_PAGE)

        pagination = query.order_by(SchoolFile.created_at.desc(), SchoolFile.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # One lookup for the uploader names shown in the table, rather than a
        # relationship access per row (this list is up to 100 rows deep).
        uploader_ids = {item.uploaded_by for item in pagination.items if item.uploaded_by}
        uploaders = {}
        if uploader_ids:
            uploaders = {
                user.id: (user.username or user.email)
                for user in User.query.filter(User.id.in_(uploader_ids)).all()
            }

        files = []
        for record in pagination.items:
            data = serialize_file(record)
            data['uploaded_by_name'] = uploaders.get(record.uploaded_by)
            # Reported so the UI can flag a row whose bytes have vanished (a
            # manual deletion on the server) instead of rendering a silently
            # broken thumbnail. Legacy rows point outside the storage tree by
            # design, so the existence check does not apply to them -- running it
            # anyway would mark every one of them "missing".
            if data['is_legacy']:
                data['missing'] = False
            else:
                data['missing'] = not os.path.isfile(absolute_path(record.relative_path))
            files.append(data)

        return jsonify({
            'files': files,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }), 200
    except Exception as error:
        return jsonify({'message': 'Unable to list files: %s' % error}), 500


## @brief Upload a file into one of the caller's storage buckets.
#
# multipart/form-data: file, category, and optional title / linked_type /
# linked_id. Returns the created record including the public URL, which is what
# the dashboard's image pickers write into the entity being edited.
@storage_api.route('/files', methods=['POST'])
@login_required
@admin_assistant_or_content_required
def upload_storage_file():
    try:
        school_id = resolve_scope()
        category = validate_category((request.form.get('category') or '').strip())
    except StorageError as error:
        return storage_error_response(error)

    file_storage = request.files.get('file')
    if file_storage is None:
        return jsonify({'message': 'No file was selected.'}), 400

    linked_id = request.form.get('linked_id')
    try:
        linked_id = int(linked_id) if linked_id else None
    except (TypeError, ValueError):
        linked_id = None

    try:
        record = save_upload(
            school_id,
            category,
            file_storage,
            uploaded_by=current_user.id if current_user.is_authenticated else None,
            title=request.form.get('title'),
            linked_type=(request.form.get('linked_type') or '').strip() or None,
            linked_id=linked_id
        )
        db.session.commit()
    except StorageError as error:
        db.session.rollback()
        return storage_error_response(error)
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Unable to upload this file: %s' % error}), 500

    log_admin_action(
        'upload', 'storage_file', record.id,
        details='%s (%s bytes) into %s' % (record.original_filename, record.file_size, category)
    )
    return jsonify({
        'message': 'File uploaded.',
        'file': serialize_file(record),
        'usage': usage_summary(school_id)
    }), 201


## @brief Rename a stored file's admin-facing label.
#
# The stored filename is a uuid and must not change (URLs already in the
# database point at it), so only the display title is editable.
@storage_api.route('/files/<int:file_id>', methods=['PUT'])
@login_required
@admin_or_assistant_required
def update_storage_file(file_id):
    try:
        school_id = resolve_scope()
    except StorageError as error:
        return storage_error_response(error)

    record = get_scoped_file(file_id, school_id)
    if not record:
        return jsonify({'message': 'File not found'}), 404

    payload = request.get_json(silent=True) or {}
    if 'title' in payload:
        record.title = (payload.get('title') or '').strip() or None

    try:
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Unable to update this file: %s' % error}), 500

    return jsonify({'message': 'File updated.', 'file': serialize_file(record)}), 200


## @brief Delete a stored file, bytes and index row together.
#
# A file that something still points at is refused unless `?force=true`: the
# reference is only a URL string in another table, so nothing would stop the
# deletion at the database level and the first sign of trouble would be a broken
# image on a reader's screen. The caller is told what it is attached to so the
# confirmation can say so.
@storage_api.route('/files/<int:file_id>', methods=['DELETE'])
@login_required
@admin_or_assistant_required
def delete_storage_file(file_id):
    try:
        school_id = resolve_scope()
    except StorageError as error:
        return storage_error_response(error)

    record = get_scoped_file(file_id, school_id)
    if not record:
        return jsonify({'message': 'File not found'}), 404

    force = (request.args.get('force') or '').lower() in ('1', 'true', 'yes')
    if record.linked_type and not force:
        return jsonify({
            'message': 'This file is still used by a %s. Deleting it will leave a broken '
                       'image or missing audio. Confirm to delete it anyway.'
                       % record.linked_type.replace('_', ' '),
            'code': 'FILE_IN_USE',
            'linked_type': record.linked_type,
            'linked_id': record.linked_id
        }), 409

    filename = record.original_filename
    try:
        delete_file(record)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Unable to delete this file: %s' % error}), 500

    log_admin_action('delete', 'storage_file', file_id, details=filename)
    return jsonify({
        'message': 'File deleted.',
        'usage': usage_summary(school_id)
    }), 200


## @brief Create the folder tree for the caller's school.
#
# Useful for a school that existed before storage management shipped: it gives
# the admin a way to lay out the folders without waiting for a first upload.
@storage_api.route('/initialize', methods=['POST'])
@login_required
@admin_or_assistant_required
def initialize_storage_tree():
    try:
        school_id = resolve_scope()
        ensure_school_tree(school_id)
    except StorageError as error:
        return storage_error_response(error)
    except OSError as error:
        return jsonify({'message': 'Unable to create the storage folders: %s' % error}), 500

    return jsonify({
        'message': 'Storage folders ready.',
        'usage': usage_summary(school_id)
    }), 200


## @brief Cross-school storage overview for the platform administrator.
#
# The person who decides whether a school's quota should be raised needs to see
# every school's usage in one place; a school admin only ever sees their own.
@storage_api.route('/schools', methods=['GET'])
@login_required
@admin_required
def list_school_storage():
    if not is_super_admin():
        return jsonify({'message': 'Only a platform administrator can view this.'}), 403

    try:
        rows = []
        for school in Shcool.query.order_by(Shcool.name.asc()).all():
            summary = usage_summary(school.id)
            rows.append({
                'school_id': school.id,
                'school_name': school.name,
                'folder': owner_folder(school.id),
                'quota_mb': summary['quota_bytes'] // (1024 * 1024),
                'quota_override_mb': school.storage_quota_mb,
                'used_bytes': summary['used_bytes'],
                'quota_bytes': summary['quota_bytes'],
                'percent_used': summary['percent_used'],
                'file_count': summary['file_count']
            })

        platform_summary = usage_summary(None)
        return jsonify({
            'schools': rows,
            'platform': {
                'folder': owner_folder(None),
                'used_bytes': platform_summary['used_bytes'],
                'file_count': platform_summary['file_count']
            },
            'default_quota_mb': ConfigClass.SCHOOL_STORAGE_QUOTA_MB
        }), 200
    except Exception as error:
        return jsonify({'message': 'Unable to load school storage: %s' % error}), 500


## @brief Set or clear a school's storage allowance.
#
# A null/blank quota clears the override so the school follows the platform
# default -- meaningfully different from 0, which would leave it unable to
# upload anything at all.
@storage_api.route('/schools/<int:school_id>/quota', methods=['PUT'])
@login_required
@admin_required
def update_school_quota(school_id):
    if not is_super_admin():
        return jsonify({'message': 'Only a platform administrator can change quotas.'}), 403

    school = Shcool.query.get(school_id)
    if not school:
        return jsonify({'message': 'School not found'}), 404

    payload = request.get_json(silent=True) or {}
    raw_quota = payload.get('storage_quota_mb')

    if raw_quota in (None, '', 'null'):
        school.storage_quota_mb = None
    else:
        try:
            quota = int(raw_quota)
        except (TypeError, ValueError):
            return jsonify({'message': 'The storage quota must be a number of MB.'}), 400
        if quota < 0:
            return jsonify({'message': 'The storage quota cannot be negative.'}), 400
        school.storage_quota_mb = quota

    try:
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        return jsonify({'message': 'Unable to update the quota: %s' % error}), 500

    log_admin_action(
        'update', 'school_storage_quota', school_id,
        details='quota_mb=%s' % (school.storage_quota_mb if school.storage_quota_mb is not None else 'default')
    )
    return jsonify({
        'message': 'Storage quota updated.',
        'usage': usage_summary(school_id)
    }), 200
