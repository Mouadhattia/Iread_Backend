## @file
# Self-hosted per-school file storage.
#
# Every asset a school uploads lives on our own disk under a folder owned by
# that school, replacing the former Cloudinary hosting:
#
#     <SCHOOL_STORAGE_DIR>/
#         school_<id>/
#             stories/audio/     stories/images/
#             books/covers/      books/files/
#             packs/images/
#             general/
#         platform/              (super-admin assets, same sub-tree)
#
# This module owns the rules that keep that tree consistent -- where a file may
# be written, what may be written there, how much a school is allowed to use,
# and what URL the file is reachable at. Route modules call in here rather than
# touching `os` directly, so a new upload endpoint cannot accidentally skip the
# quota check or write outside a school's own folder.
import mimetypes
import os
import re
from uuid import uuid4

from flask import request
from sqlalchemy import func
from werkzeug.utils import secure_filename

from config import ConfigClass
from extensions import db
from models.school_file import STORAGE_CATEGORIES, SchoolFile
from models.shcool import Shcool

## @brief Raised for any caller mistake worth showing an admin verbatim --
# unsupported type, oversized file, quota exhausted, unknown category. Route
# handlers map it to a 400 with the message, so the wording here is user-facing.
#
# Subclasses ValueError on purpose: the story and audiobook upload routes
# already funnel `except ValueError` into a 400 carrying the exception text,
# which is exactly the right handling for these. Without that inheritance a
# quota rejection in one of those routes would surface as an opaque 500.
class StorageError(ValueError):
    pass


## @brief Bytes per megabyte, spelled once so the quota maths reads clearly.
BYTES_PER_MB = 1024 * 1024

## @brief The folder a platform-owned (school-less) asset goes in. Mirrors the
# 'platform' owner folder the pre-existing story/audiobook uploads already use.
PLATFORM_FOLDER = 'platform'

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'}
AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac', 'webm', 'mp4'}
DOCUMENT_EXTENSIONS = {'pdf'}

## @brief What each bucket is allowed to hold, and the per-file ceiling to use.
#
# Keeping the allow-list per category (rather than one global list) is what
# stops a 50 MB audio file being uploaded as a pack image, and what lets the
# storage manager show an accurate "accepted types" hint per section.
CATEGORY_RULES = {
    'stories/audio': {
        'label': 'Story audio',
        'extensions': AUDIO_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_AUDIO_UPLOAD_MB',
        'kind': 'audio'
    },
    'stories/images': {
        'label': 'Story images',
        'extensions': IMAGE_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_IMAGE_UPLOAD_MB',
        'kind': 'image'
    },
    'books/covers': {
        'label': 'Book covers',
        'extensions': IMAGE_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_IMAGE_UPLOAD_MB',
        'kind': 'image'
    },
    'books/files': {
        'label': 'Book files',
        'extensions': DOCUMENT_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_DOCUMENT_UPLOAD_MB',
        'kind': 'document'
    },
    'packs/images': {
        'label': 'Pack images',
        'extensions': IMAGE_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_IMAGE_UPLOAD_MB',
        'kind': 'image'
    },
    'general': {
        'label': 'General',
        'extensions': IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS,
        'max_mb_setting': 'MAX_MEDIA_DOCUMENT_UPLOAD_MB',
        'kind': 'mixed'
    }
}

## @brief URL prefix the public media blueprint is mounted at. Referenced from
# both the URL builder and the reverse (URL -> relative path) parser, so the
# two cannot drift apart.
MEDIA_URL_PREFIX = '/media'

## @brief Matches a stored media URL, absolute or relative, and captures the
# path relative to the storage root. Used to recognise our own URLs when an
# entity's image is replaced, so the superseded file can be found and deleted.
MEDIA_URL_PATTERN = re.compile(
    r'^(?:https?://[^/]+)?' + re.escape(MEDIA_URL_PREFIX) + r'/(?P<path>.+)$'
)


def storage_root():
    return os.path.abspath(ConfigClass.SCHOOL_STORAGE_DIR)


## @brief The owner folder name for a school id.
#
# @param school_id: school primary key, or None for platform-owned assets.
def owner_folder(school_id):
    if school_id is None:
        return PLATFORM_FOLDER
    return 'school_%s' % int(school_id)


## @brief Parse an owner folder name back to a school id.
#
# @return the school id, or None for the platform folder.
def school_id_from_folder(folder_name):
    if folder_name == PLATFORM_FOLDER:
        return None
    match = re.fullmatch(r'school_(\d+)', folder_name or '')
    if not match:
        raise StorageError('Unrecognised storage folder: %s' % folder_name)
    return int(match.group(1))


def validate_category(category):
    if category not in STORAGE_CATEGORIES:
        raise StorageError(
            'Unknown storage category. Expected one of: %s' % ', '.join(STORAGE_CATEGORIES)
        )
    return category


## @brief Absolute directory for a bucket, created if missing.
def category_dir(school_id, category):
    validate_category(category)
    # Split on '/' so the nested categories ('stories/audio') become real
    # nested folders on Windows too, where os.sep is a backslash.
    directory = os.path.join(storage_root(), owner_folder(school_id), *category.split('/'))
    os.makedirs(directory, exist_ok=True)
    return directory


## @brief Create a school's full folder tree up front.
#
# Called when a school is created so an admin opening the storage manager sees
# the same set of sections as everyone else instead of an empty page that fills
# in only as files happen to be uploaded.
def ensure_school_tree(school_id):
    for category in STORAGE_CATEGORIES:
        category_dir(school_id, category)
    return os.path.join(storage_root(), owner_folder(school_id))


## @brief Absolute path for a stored relative path, refusing anything that
# escapes the storage root.
#
# Every path that reaches the filesystem passes through here. `relative_path`
# can come from a URL (the public media route) or from an old database row, so
# it is treated as untrusted: `..` segments and absolute paths would otherwise
# turn the media route into an arbitrary-file-read of the whole server.
def absolute_path(relative_path):
    if not relative_path:
        raise StorageError('Missing file path.')
    root = storage_root()
    candidate = os.path.abspath(os.path.join(root, *str(relative_path).split('/')))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise StorageError('Invalid file path.')
    return candidate


## @brief The path-relative-to-root form used in the database and in URLs.
#
# Always forward-slashed, so a row written by a Windows dev box and one written
# on the Linux server are the same value and resolve to the same URL.
def relative_path_from_absolute(absolute_file_path):
    root = storage_root()
    relative = os.path.relpath(os.path.abspath(absolute_file_path), root)
    return relative.replace(os.sep, '/')


## @brief The absolute URL a stored file is served at.
#
# The result is written into the database (book.img, pack.img, user.img, ...)
# and read by all four frontends, so it has to be absolute. PUBLIC_MEDIA_BASE_URL
# is the configured answer; falling back to the current request's host keeps
# local development working without extra setup, and only fails outside a
# request context (a CLI script), where the config must be set anyway.
def public_url(relative_path):
    base = ConfigClass.PUBLIC_MEDIA_BASE_URL
    if not base:
        base = request.host_url.rstrip('/') if request else ''
    return '%s%s/%s' % (base, MEDIA_URL_PREFIX, relative_path)


## @brief If `url` is one of our own media URLs, return its relative path.
#
# @return the storage-relative path, or None when the URL points elsewhere
#         (a Cloudinary leftover, an external image, a data URI).
def relative_path_from_url(url):
    if not url:
        return None
    match = MEDIA_URL_PATTERN.match(str(url).strip())
    if not match:
        return None
    path = match.group('path').split('?')[0].split('#')[0]
    try:
        absolute_path(path)
    except StorageError:
        return None
    return path


def file_extension(filename):
    name = secure_filename(filename or '')
    if '.' not in name:
        return ''
    return name.rsplit('.', 1)[1].lower()


## @brief Size of an uploaded stream, without reading it into memory.
def uploaded_file_size(file_storage):
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size


## @brief The MB ceiling configured for a category's kind of file.
def category_max_mb(category):
    rules = CATEGORY_RULES[validate_category(category)]
    return int(getattr(ConfigClass, rules['max_mb_setting']))


## @brief A school's disk allowance in bytes.
def quota_bytes(school_id):
    quota_mb = None
    if school_id is not None:
        school = Shcool.query.get(school_id)
        quota_mb = school.storage_quota_mb if school else None
    if quota_mb is None:
        quota_mb = ConfigClass.SCHOOL_STORAGE_QUOTA_MB
    return int(quota_mb) * BYTES_PER_MB


## @brief Total indexed bytes currently held by a school.
def used_bytes(school_id):
    total = db.session.query(func.coalesce(func.sum(SchoolFile.file_size), 0)).filter(
        SchoolFile.shcool_id == school_id,
        SchoolFile.active.is_(True)
    ).scalar()
    return int(total or 0)


## @brief Per-category and overall usage for the storage manager.
#
# Reports every category, including empty ones, so the UI can render a stable
# set of sections rather than one that appears and disappears with content.
def usage_summary(school_id):
    rows = db.session.query(
        SchoolFile.category,
        func.count(SchoolFile.id),
        func.coalesce(func.sum(SchoolFile.file_size), 0)
    ).filter(
        SchoolFile.shcool_id == school_id,
        SchoolFile.active.is_(True)
    ).group_by(SchoolFile.category).all()

    by_category = {category: {'file_count': 0, 'bytes': 0} for category in STORAGE_CATEGORIES}
    for category, file_count, total_bytes in rows:
        # A category that was removed from STORAGE_CATEGORIES after files were
        # written to it still counts against the quota, so keep it visible
        # rather than silently dropping its bytes from the total.
        entry = by_category.setdefault(category, {'file_count': 0, 'bytes': 0})
        entry['file_count'] = int(file_count or 0)
        entry['bytes'] = int(total_bytes or 0)

    total = sum(entry['bytes'] for entry in by_category.values())
    file_count = sum(entry['file_count'] for entry in by_category.values())
    limit = quota_bytes(school_id)

    return {
        'school_id': school_id,
        'used_bytes': total,
        'quota_bytes': limit,
        'available_bytes': max(limit - total, 0),
        'percent_used': round((total / limit) * 100, 2) if limit else 0,
        'file_count': file_count,
        'categories': [
            {
                'category': category,
                'label': CATEGORY_RULES.get(category, {}).get('label', category),
                'file_count': values['file_count'],
                'bytes': values['bytes']
            }
            for category, values in by_category.items()
        ]
    }


## @brief Reject an upload that would take the school over its allowance.
#
# @param replaces_bytes: size of a file this upload supersedes, which is about
#        to be freed. Without it, replacing a 9 MB image in a school sitting at
#        its limit would be refused even though the net change is a decrease.
def assert_within_quota(school_id, incoming_bytes, replaces_bytes=0):
    limit = quota_bytes(school_id)
    projected = used_bytes(school_id) - int(replaces_bytes or 0) + int(incoming_bytes)
    if projected > limit:
        raise StorageError(
            'This upload would exceed the school storage limit of %s MB. '
            'Delete unused files or ask for a larger allowance.'
            % (limit // BYTES_PER_MB)
        )


## @brief Check an uploaded file against its category's rules.
#
# @return (extension, size_in_bytes)
def validate_upload(file_storage, category):
    rules = CATEGORY_RULES[validate_category(category)]
    if file_storage is None or not (file_storage.filename or '').strip():
        raise StorageError('No file was selected.')

    extension = file_extension(file_storage.filename)
    if extension not in rules['extensions']:
        raise StorageError(
            '%s only accepts these file types: %s'
            % (rules['label'], ', '.join(sorted(rules['extensions'])))
        )

    max_mb = category_max_mb(category)
    size = uploaded_file_size(file_storage)
    if size <= 0:
        raise StorageError('This file is empty.')
    if size > max_mb * BYTES_PER_MB:
        raise StorageError('This file is too large. The limit is %s MB.' % max_mb)

    return extension, size


def _stored_filename(category, extension):
    # The uuid, not the admin's filename, is what makes the name unique and
    # unguessable -- the media route is public, so a predictable name would
    # make one school's uploads discoverable from another's.
    prefix = category.replace('/', '-')
    return '%s-%s.%s' % (prefix, uuid4().hex, extension)


## @brief Guess a mime type when the browser did not send a useful one.
def resolve_mime_type(file_storage, stored_filename):
    mimetype = (getattr(file_storage, 'mimetype', '') or '').lower()
    if mimetype and mimetype != 'application/octet-stream':
        return mimetype
    guessed, _ = mimetypes.guess_type(stored_filename)
    return guessed or 'application/octet-stream'


## @brief Store an uploaded file in a school's folder and index it.
#
# The single entry point for new uploads: it validates, enforces the quota,
# writes the bytes and records the SchoolFile row. The row is added to the
# session but not committed, so a caller that also updates the entity pointing
# at the file (a book cover, a pack image) commits both together and cannot end
# up with one without the other.
#
# On any failure after the bytes land on disk the partial file is removed --
# otherwise a rolled-back transaction would leave an orphan consuming quota
# that nothing in the index can account for.
#
# @param school_id: owning school, or None for a platform asset.
# @param category: one of STORAGE_CATEGORIES.
# @param file_storage: the werkzeug FileStorage from request.files.
# @param uploaded_by: acting user id, for the storage manager's audit column.
# @param title: optional admin-facing label.
# @param linked_type/linked_id: what the file is attached to, if known.
# @param replaces_bytes: see assert_within_quota.
# @return the uncommitted SchoolFile row.
def save_upload(school_id, category, file_storage, uploaded_by=None, title=None,
                linked_type=None, linked_id=None, replaces_bytes=0):
    extension, size = validate_upload(file_storage, category)
    assert_within_quota(school_id, size, replaces_bytes=replaces_bytes)

    directory = category_dir(school_id, category)
    stored_filename = _stored_filename(category, extension)
    destination = os.path.join(directory, stored_filename)
    file_storage.save(destination)

    try:
        record = SchoolFile(
            shcool_id=school_id,
            category=category,
            relative_path=relative_path_from_absolute(destination),
            stored_filename=stored_filename,
            original_filename=secure_filename(file_storage.filename) or stored_filename,
            mime_type=resolve_mime_type(file_storage, stored_filename),
            file_size=size,
            uploaded_by=uploaded_by,
            title=(title or '').strip() or None,
            linked_type=linked_type,
            linked_id=linked_id
        )
        db.session.add(record)
        db.session.flush()
        return record
    except Exception:
        remove_from_disk(destination)
        raise


## @brief Index a file that was written to the tree by other code.
#
# The story-PDF and audiobook upload routes save their own files (they need the
# path immediately, for parsing and alignment). This registers those files so
# they count toward the school's usage and appear in the storage manager,
# instead of being invisible disk consumption.
#
# Idempotent by relative_path, so re-running the indexing script over an
# existing tree updates sizes rather than creating duplicate rows.
def register_existing_file(school_id, category, absolute_file_path, uploaded_by=None,
                           original_filename=None, title=None, linked_type=None,
                           linked_id=None, mime_type=None):
    validate_category(category)
    relative = relative_path_from_absolute(absolute_file_path)
    record = SchoolFile.query.filter_by(relative_path=relative).first()
    size = os.path.getsize(absolute_file_path) if os.path.exists(absolute_file_path) else 0
    stored_filename = os.path.basename(absolute_file_path)
    guessed_mime = mime_type or mimetypes.guess_type(stored_filename)[0] or 'application/octet-stream'

    if record:
        record.file_size = size
        record.active = True
        record.category = category
        record.shcool_id = school_id
        if title:
            record.title = title
        if linked_type:
            record.linked_type = linked_type
            record.linked_id = linked_id
        return record

    record = SchoolFile(
        shcool_id=school_id,
        category=category,
        relative_path=relative,
        stored_filename=stored_filename,
        original_filename=original_filename or stored_filename,
        mime_type=guessed_mime,
        file_size=size,
        uploaded_by=uploaded_by,
        title=(title or '').strip() or None,
        linked_type=linked_type,
        linked_id=linked_id
    )
    db.session.add(record)
    db.session.flush()
    return record


## @brief Best-effort unlink.
#
# Deliberately swallows OS errors: the caller's real work (deleting a book,
# replacing an image) must not fail because a file was already gone or is
# briefly locked. The row is what the quota is computed from, so a stale file
# is a disk-space problem for the indexing script, not a broken request.
def remove_from_disk(absolute_file_path):
    if absolute_file_path and os.path.exists(absolute_file_path):
        try:
            os.remove(absolute_file_path)
            return True
        except OSError:
            return False
    return False


## @brief Delete an indexed file: bytes then row.
def delete_file(record):
    remove_from_disk(absolute_path(record.relative_path))
    db.session.delete(record)


## @brief True when a path lies inside the storage tree.
#
# Legacy rows (written before storage management, under the old uploads roots)
# hold absolute paths outside the tree; those files have no index row and must
# be handled by plain unlink rather than looked up.
def is_inside_storage(absolute_file_path):
    if not absolute_file_path:
        return False
    root = storage_root()
    candidate = os.path.abspath(absolute_file_path)
    return candidate.startswith(root + os.sep)


## @brief Delete a file by its absolute path, dropping its index row too.
#
# Used by the story/audiobook delete routes, which track files by path rather
# than by SchoolFile id. Handles both new files inside the storage tree and
# legacy ones outside it, so those routes need no branching of their own.
#
# The row is deleted but not committed -- the caller is already in a
# transaction removing the owning entity, and both should land together.
def delete_by_absolute_path(absolute_file_path):
    if not absolute_file_path:
        return False
    if is_inside_storage(absolute_file_path):
        relative = relative_path_from_absolute(absolute_file_path)
        record = SchoolFile.query.filter_by(relative_path=relative).first()
        if record:
            db.session.delete(record)
    return remove_from_disk(absolute_file_path)


## @brief Find the index row behind a stored media URL, if we own it.
#
# Deliberately a lookup and not a delete. Replacing a book's cover must NOT
# delete the file it pointed at: the storage manager exists so an image can be
# picked once and reused across several books and packs, and auto-deleting on
# replace would pull a shared asset out from under the others. Reclaiming space
# is an explicit action in the storage manager, where the "still used by" warning
# can be shown first.
#
# @return the SchoolFile row, or None when the URL points elsewhere (an external
#         image, a Cloudinary leftover) or is not ours.
def find_by_url(url, school_id=None):
    relative = relative_path_from_url(url)
    if not relative:
        return None
    record = SchoolFile.query.filter_by(relative_path=relative).first()
    if not record:
        return None
    if school_id is not None and record.shcool_id != school_id:
        return None
    return record


## @brief Prefix marking an index row for a file outside the storage tree.
#
# The pre-existing story-PDF and audiobook upload trees sit outside this root and
# their files are referenced by absolute path from other tables, so they are
# indexed where they lie rather than moved. They still consume the school's disk,
# so leaving them out would make the quota bar understate real usage -- but they
# have no path under the root, so no /media URL can reach them either. The prefix
# lets both facts be true at once: counted, but not presented as servable.
LEGACY_PATH_PREFIX = 'legacy/'


def is_legacy_record(record):
    return str(record.relative_path or '').startswith(LEGACY_PATH_PREFIX)


## @brief The storage manager's view of one file.
def serialize_file(record):
    legacy = is_legacy_record(record)
    return {
        'id': record.id,
        'school_id': record.shcool_id,
        'category': record.category,
        'category_label': CATEGORY_RULES.get(record.category, {}).get('label', record.category),
        'kind': CATEGORY_RULES.get(record.category, {}).get('kind', 'mixed'),
        'title': record.title,
        'original_filename': record.original_filename,
        'stored_filename': record.stored_filename,
        'relative_path': record.relative_path,
        # A legacy file has no servable URL. Returning None rather than a URL that
        # would 404 is what lets the UI label it honestly instead of rendering a
        # broken thumbnail and a dead "open" button.
        'is_legacy': legacy,
        'url': None if legacy else public_url(record.relative_path),
        'mime_type': record.mime_type,
        'file_size': int(record.file_size or 0),
        'uploaded_by': record.uploaded_by,
        'linked_type': record.linked_type,
        'linked_id': record.linked_id,
        'active': record.active,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None
    }


## @brief The category catalogue the storage UI renders its sections from.
#
# Served to the frontend so the accepted extensions and size limits shown to an
# admin are the ones actually enforced here, rather than a second copy in JS
# that drifts out of step with the config.
def serialize_categories():
    return [
        {
            'category': category,
            'label': CATEGORY_RULES[category]['label'],
            'kind': CATEGORY_RULES[category]['kind'],
            'extensions': sorted(CATEGORY_RULES[category]['extensions']),
            'max_mb': category_max_mb(category)
        }
        for category in STORAGE_CATEGORIES
    ]
