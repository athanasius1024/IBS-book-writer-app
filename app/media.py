"""Image uploads. Files are stored outside ``static`` and served only to their owner."""
import uuid
from pathlib import Path

from flask import Blueprint, current_app, send_from_directory
from flask_login import login_required
from werkzeug.utils import secure_filename

from access import owned_asset_or_404
from models import MediaAsset

bp = Blueprint('media', __name__)

# extension -> (mime type, signature check)
_IMAGE_TYPES = {
    'png': ('image/png', lambda h: h.startswith(b'\x89PNG\r\n\x1a\n')),
    'jpg': ('image/jpeg', lambda h: h.startswith(b'\xff\xd8\xff')),
    'jpeg': ('image/jpeg', lambda h: h.startswith(b'\xff\xd8\xff')),
    'gif': ('image/gif', lambda h: h.startswith((b'GIF87a', b'GIF89a'))),
    'webp': ('image/webp', lambda h: h[:4] == b'RIFF' and h[8:12] == b'WEBP'),
}


def save_image(file_storage, user_id):
    """Validate and store an uploaded image. Returns an uncommitted MediaAsset.

    Raises ValueError with a user-presentable message if the file is not an
    acceptable image.
    """
    original = secure_filename(file_storage.filename or '')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in _IMAGE_TYPES:
        raise ValueError('Images must be PNG, JPG, GIF or WEBP files.')
    mime, signature_ok = _IMAGE_TYPES[ext]

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not signature_ok(header):
        raise ValueError('That file does not look like a valid image.')

    folder = Path(current_app.config['UPLOAD_DIR']) / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f'{uuid.uuid4().hex}.{ext}'
    destination = folder / stored_name
    file_storage.save(destination)

    return MediaAsset(user_id=user_id, asset_name=original or stored_name,
                      file_path=f'{user_id}/{stored_name}',
                      file_size=destination.stat().st_size, mime_type=mime)


@bp.route('/media/<int:asset_id>')
@login_required
def serve(asset_id):
    asset = owned_asset_or_404(asset_id)
    return send_from_directory(current_app.config['UPLOAD_DIR'], asset.file_path,
                               mimetype=asset.mime_type, max_age=0)
