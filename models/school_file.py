## @file
# @class SchoolFile
#
# Index of every file held in a school's own storage folder on the server.
#
# The rows are an index, not the storage itself: the bytes live on disk under
# `<SCHOOL_STORAGE_DIR>/<owner_folder>/<category>/<stored_filename>` and this
# table records who owns each one, how big it is and what it is attached to.
# Without it, "how much disk is this school using?" and "show me the images I
# already uploaded" would both require walking the filesystem on every request.
from datetime import datetime

from extensions import db
from models.shcool import Shcool
from models.user import User


## @brief Storage buckets a file can belong to.
#
# The values double as the on-disk sub-path, so the folder layout is derived
# from this single list rather than restated anywhere else.
STORAGE_CATEGORIES = (
    'stories/audio',
    'stories/images',
    'books/covers',
    'books/files',
    'packs/images',
    'general',
)


class SchoolFile(db.Model):
    __tablename__ = 'school_file'
    id = db.Column(db.Integer, primary_key=True)
    ## @brief Owning school. NULL means a platform-owned (super-admin) asset,
    # matching how Book/Pack/BookStory already encode "not school-specific".
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=True, index=True)
    ## @brief One of STORAGE_CATEGORIES; also the on-disk sub-folder.
    category = db.Column(db.String(40), nullable=False, index=True)
    ## @brief Path relative to the storage root, e.g.
    # `school_12/packs/images/pack-9f3c.png`. Stored with forward slashes on
    # every platform so the same value works as a URL suffix and as a lookup
    # key regardless of which OS wrote it.
    relative_path = db.Column(db.String(500), nullable=False, unique=True)
    stored_filename = db.Column(db.String(255), nullable=False)
    ## @brief What the admin's file was called before it was renamed to a
    # collision-proof stored name -- the only label they would recognise.
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    ## @brief Size in bytes. BigInteger because a school's audio library
    # summed over a term can exceed the 2 GB an Integer column tops out at.
    file_size = db.Column(db.BigInteger, nullable=False, default=0)
    uploaded_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True)
    ## @brief Optional admin-supplied label, shown in the storage manager
    # instead of the raw filename when set.
    title = db.Column(db.String(255), nullable=True)
    ## @brief What the file is attached to ('book', 'pack', 'user', 'story',
    # 'audio_book', 'public_page'), for the "where is this used?" column and
    # to warn before deleting something still referenced.
    linked_type = db.Column(db.String(40), nullable=True)
    linked_id = db.Column(db.Integer, nullable=True)
    ## @brief Soft-delete flag. A file whose bytes are gone but which is still
    # referenced by an old row is kept inactive rather than removed, so the
    # storage manager can explain a broken image instead of showing nothing.
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    school = db.relationship(Shcool, backref='storage_files')
    uploader = db.relationship(User, backref='uploaded_storage_files')

    def __repr__(self):
        return '<SchoolFile %s>' % self.relative_path
