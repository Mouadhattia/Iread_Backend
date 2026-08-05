## @file
# Canonical delivery of the shared profile-avatar library.
#
# The 24 icons under `apps/static/avatars/icons` are pre-rendered from
# `boring-avatars` by `Dashboard-iread-last-version/scripts/generate-avatars.js`,
# which owns `avatarLibrary.json` -- the shared contract naming each icon's
# variant, seed and palette. A copy of that manifest is served here so any
# client can build a picker without hardcoding the list.
#
# WHY THE BACKEND SERVES THEM: `User.img` is a 300-character column, so a picked
# avatar is persisted as a *URL*, not inline SVG. The admin dashboard used to
# write `window.location.origin + /avatars/icons/<id>.svg`, which pinned every
# saved avatar to whichever frontend host the picker happened to run on -- the
# reader web app and the mobile app do not serve those files, so the same user
# rendered as a broken image there. Serving them from the API gives all four
# frontends plus the mobile app one URL that always resolves.
#
# Deliberately unauthenticated, for the same reason as `apps/media.py`: these
# URLs are rendered as plain `<img src>` from other origins, where a
# cookie-gated URL would not load. There is nothing private in them -- they are
# 24 fixed, identical-for-everyone shapes.
import os

from flask import Blueprint, jsonify, send_file

avatars = Blueprint('avatars', __name__, url_prefix='/avatars')

_AVATARS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'avatars')
_ICONS_ROOT = os.path.join(_AVATARS_ROOT, 'icons')

# Immutable: changing an icon means adding a new id, never rewriting one, so a
# saved User.img keeps pointing at the artwork the user actually chose.
_CACHE_CONTROL = 'public, max-age=31536000, immutable'


## @brief The shared manifest: every icon's id, variant, seed and palette.
#
# @return: JSON, the contents of avatarLibrary.json.
@avatars.route('/library.json', methods=['GET'])
def avatar_library():
    manifest = os.path.join(_AVATARS_ROOT, 'avatarLibrary.json')
    if not os.path.isfile(manifest):
        return jsonify({'message': 'Avatar library not found'}), 404

    response = send_file(manifest, mimetype='application/json', conditional=True)
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


## @brief Serve one pre-rendered avatar.
#
# @param icon_id: the library id, e.g. `beam-2`.
# @return: the SVG file, or 404.
@avatars.route('/icons/<icon_id>.svg', methods=['GET'])
def avatar_icon(icon_id):
    # The id goes into a filesystem path, so anything but a plain library id is
    # rejected outright rather than normalised -- no separators, no traversal,
    # no room for a `..` to turn this into an arbitrary-file read.
    if not icon_id.replace('-', '').replace('_', '').isalnum():
        return jsonify({'message': 'Avatar not found'}), 404

    file_path = os.path.join(_ICONS_ROOT, f'{icon_id}.svg')
    if not os.path.isfile(file_path):
        return jsonify({'message': 'Avatar not found'}), 404

    response = send_file(file_path, mimetype='image/svg+xml', conditional=True)
    response.headers['Cache-Control'] = _CACHE_CONTROL
    return response
