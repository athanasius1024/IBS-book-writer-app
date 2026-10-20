"""Image uploads and the per-user media library.

Files are stored outside ``static`` and served only to their owner.
"""
import uuid
from pathlib import Path

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from access import owned_asset_or_404
from imagespec import parse_crop
from imaging import derive, inline_usage_counts, remove_derivative_files
from models import BookCover, ContentBlock, MediaAsset, db

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


def asset_usage(asset_id, inline=None):
    """How many covers and content blocks reference this asset. Blocks include text blocks that show
    it inline; pass `inline` (from inline_usage_counts) to avoid scanning the text for every asset."""
    covers = BookCover.query.filter_by(asset_id=asset_id).count()
    blocks = ContentBlock.query.filter_by(asset_id=asset_id).count()
    if inline is None:
        inline = inline_usage_counts(current_user.user_id)
    return covers, blocks + inline.get(asset_id, 0)


@bp.route('/media/<int:asset_id>')
@login_required
def serve(asset_id):
    asset = owned_asset_or_404(asset_id)
    return send_from_directory(current_app.config['UPLOAD_DIR'], asset.file_path,
                               mimetype=asset.mime_type, max_age=0)


@bp.route('/media/<int:asset_id>/crop')
@login_required
def serve_crop(asset_id):
    """The picture cropped to ?c=x,y,w,h (fractions of the original), as shown in chapter text."""
    asset = owned_asset_or_404(asset_id)
    derivative = derive(asset, parse_crop(request.args.get('c')))
    if derivative is None:                      # no usable crop, or the original is small enough
        return redirect(url_for('media.serve', asset_id=asset.asset_id))
    return send_from_directory(current_app.config['UPLOAD_DIR'], derivative.file_path,
                               mimetype=derivative.mime_type, max_age=0)


def _asset_json(asset):
    return {'id': asset.asset_id, 'name': asset.asset_name, 'url': url_for('media.serve', asset_id=asset.asset_id),
            'size': asset.file_size or 0}


@bp.route('/media/library.json')
@login_required
def library_json():
    """The current user's pictures, for the Insert image picker in the chapter editor."""
    assets = (MediaAsset.query.filter_by(user_id=current_user.user_id)
              .order_by(MediaAsset.created_at.desc(), MediaAsset.asset_id.desc()).all())
    return jsonify({'assets': [_asset_json(a) for a in assets]})


@bp.route('/media/upload.json', methods=['POST'])
@login_required
def upload_json():
    """Upload pictures from the Insert image picker; answers with the new library entries."""
    files = [f for f in request.files.getlist('image') if f and f.filename]
    if not files:
        return jsonify({'assets': [], 'errors': ['Choose at least one image to upload.']}), 400
    created, errors = [], []
    for upload_file in files:
        try:
            asset = save_image(upload_file, current_user.user_id)
        except ValueError as exc:
            errors.append(f'{upload_file.filename}: {exc}')
            continue
        db.session.add(asset)
        created.append(asset)
    db.session.commit()
    return jsonify({'assets': [_asset_json(a) for a in created], 'errors': errors}), (200 if created else 400)


@bp.route('/media')
@login_required
def library():
    assets = (MediaAsset.query.filter_by(user_id=current_user.user_id)
              .order_by(MediaAsset.created_at.desc(), MediaAsset.asset_id.desc()).all())
    inline = inline_usage_counts(current_user.user_id)
    usage = {a.asset_id: asset_usage(a.asset_id, inline) for a in assets}
    return render_template('media/library.html', assets=assets, usage=usage)


@bp.route('/media/upload', methods=['POST'])
@login_required
def upload():
    files = [f for f in request.files.getlist('image') if f and f.filename]
    if not files:
        flash('Choose at least one image to upload.', 'danger')
        return redirect(url_for('media.library'))
    saved = 0
    for upload_file in files:
        try:
            asset = save_image(upload_file, current_user.user_id)
        except ValueError as exc:
            flash(f'{upload_file.filename}: {exc}', 'danger')
            continue
        db.session.add(asset)
        saved += 1
    db.session.commit()
    if saved:
        flash(f'Uploaded {saved} image{"" if saved == 1 else "s"}.', 'success')
    return redirect(url_for('media.library'))


@bp.route('/media/<int:asset_id>/delete', methods=['POST'])
@login_required
def delete(asset_id):
    asset = owned_asset_or_404(asset_id)
    covers, blocks = asset_usage(asset.asset_id)
    if covers or blocks:
        flash(f'"{asset.asset_name}" is still used in {covers + blocks} place(s) and cannot be deleted.',
              'warning')
        return redirect(url_for('media.library'))

    root = Path(current_app.config['UPLOAD_DIR']).resolve()
    path = (root / asset.file_path).resolve()
    if root in path.parents and path.is_file():
        path.unlink()
    remove_derivative_files(asset)
    name = asset.asset_name
    db.session.delete(asset)
    db.session.commit()
    flash(f'Deleted "{name}".', 'success')
    return redirect(url_for('media.library'))
