## @file
# Public delivery of files held in the self-hosted school storage.
#
# These URLs go into the database (book.img, pack.img, user.img, public-page
# logos) and are rendered as plain `<img src>` / `<audio src>` by all four
# frontends, so the route is deliberately unauthenticated: a cookie-gated URL
# would not load in an `<img>` tag from a different origin, which is exactly
# the case that broke when Cloudinary was removed. What protects a school's
# files is that stored names carry a uuid, making them unguessable, rather than
# a session check.
#
# Because it is public, path handling is the security boundary: every request
# goes through apps.storage.absolute_path, which refuses anything resolving
# outside the storage root. Without that a `..` in the URL would turn this into
# an arbitrary-file read of the server.
import os

from flask import Blueprint, jsonify, send_file

from apps.storage import MEDIA_URL_PREFIX, StorageError, absolute_path

media = Blueprint('media', __name__, url_prefix=MEDIA_URL_PREFIX)


## @brief Serve one stored file.
#
# @param relative_path: path under the storage root, e.g.
#        `school_12/packs/images/packs-images-9f3c.png`.
@media.route('/<path:relative_path>', methods=['GET'])
def serve_media(relative_path):
    try:
        file_path = absolute_path(relative_path)
    except StorageError:
        return jsonify({'message': 'File not found'}), 404

    if not os.path.isfile(file_path):
        return jsonify({'message': 'File not found'}), 404

    # conditional=True gives us ETag/If-None-Match and, importantly for the
    # audiobook player, HTTP Range support -- without it a browser cannot seek
    # within an audio file, it can only replay from the start.
    response = send_file(file_path, as_attachment=False, conditional=True)
    # These files are immutable: replacing an asset writes a new uuid name and
    # a new URL, so a long cache is safe and keeps repeat page loads off disk.
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response
