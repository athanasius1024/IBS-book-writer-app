"""Stored rendered books: the author's kept PDF, EPUB, HTML and ODT copies of a book.

Each copy is a file under UPLOAD_DIR/renders/<user>/ (with a generated name, never one taken from user
input) plus a RenderedBook row. A copy can be downloaded (the browser's Save dialog picks the folder),
viewed or printed (PDF and HTML), saved to a configured export folder, replaced by a freshly built
version, or deleted. A copy is flagged out of date when the book has been edited since.
"""
import hashlib
import io
import logging
import re
import secrets
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from access import owned_book_or_404, owned_render_or_404
from epub import build_epub
from html_export import build_html
from imaging import upload_root
from models import MAX_RENDERS_PER_FORMAT, RENDER_FORMAT_KEYS, RENDER_FORMATS, RenderedBook, db
from odt import build_odt
from render import get_layout

bp = Blueprint('renders', __name__)
log = logging.getLogger(__name__)

EXTENSIONS = {key: ext for key, _, ext, _ in RENDER_FORMATS}
LABELS = {key: label for key, label, _, _ in RENDER_FORMATS}
PRINTABLE = ('pdf', 'html')
VIEW_CSP = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; "
            "base-uri 'none'; form-action 'none'; sandbox")


# ---- the service ---------------------------------------------------------------------------------

def renders_root():
    return upload_root() / 'renders'


def stored_path(render):
    """Absolute path of a stored copy, or None if it is missing or outside the renders folder."""
    root = renders_root().resolve()
    path = (upload_root() / render.file_path).resolve()
    return path if root in path.parents and path.is_file() else None


def download_name(book, fmt):
    base = secure_filename(f'{book.title} v{book.version}') or 'book'
    return f'{base}.{EXTENSIONS[fmt]}'


def build_bytes(book, fmt, result):
    """(bytes, PDF page count or None) of the book in one format, built from one shared layout result."""
    if fmt == 'pdf':
        return result.pdf, result.physical_pages
    if fmt == 'epub':
        return build_epub(book, result), None
    if fmt == 'html':
        return build_html(book, result), None
    if fmt == 'odt':
        return build_odt(book, result), None
    raise ValueError(f'Unknown format {fmt}')


def _write(book, fmt, data):
    relative = f'renders/{book.user_id}/{uuid.uuid4().hex}.{EXTENSIONS[fmt]}'
    destination = upload_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(destination)
    return relative


def _remove_file(render):
    path = stored_path(render)
    if path is not None:
        path.unlink()


def store(book, fmt, data, page_count, generated_at, existing=None):
    """Save `data` as a stored copy of `book`; with `existing`, that copy is replaced in place."""
    relative = _write(book, fmt, data)
    old_path = stored_path(existing) if existing is not None else None
    row = existing or RenderedBook(book_id=book.book_id, user_id=book.user_id, format=fmt)
    row.file_path, row.file_name = relative, download_name(book, fmt)
    row.file_size, row.sha256 = len(data), hashlib.sha256(data).hexdigest()
    row.book_version, row.book_modified_at = book.version, book.modified_at
    row.page_count, row.generated_at = page_count, generated_at
    if existing is None:
        db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        (upload_root() / relative).unlink(missing_ok=True)
        raise
    if old_path is not None:
        old_path.unlink(missing_ok=True)
    return row


def count_for(book, fmt):
    return RenderedBook.query.filter_by(book_id=book.book_id, format=fmt).count()


def generate(book, formats, replace=None):
    """Build `formats` (or just replace the copy `replace`) from ONE fresh layout, so every copy made by
    this action carries the same version and 'Generated' date. Returns (rows, errors)."""
    if replace is not None:
        formats = [replace.format]
    try:
        result = get_layout(book, fresh=True)
    except Exception:
        log.exception('Could not lay out book %s', book.book_id)
        return [], ['The book could not be built. Check for unusual characters or images, then try again.']
    generated_at = datetime.utcnow()
    rows, errors = [], []
    for fmt in formats:
        if replace is None and count_for(book, fmt) >= MAX_RENDERS_PER_FORMAT:
            errors.append(f'You already keep {MAX_RENDERS_PER_FORMAT} {LABELS[fmt]} copies of this book. '
                          'Delete or replace one first.')
            continue
        try:
            data, pages = build_bytes(book, fmt, result)
            rows.append(store(book, fmt, data, pages, generated_at, existing=replace))
        except Exception:
            log.exception('Could not build the %s of book %s', fmt, book.book_id)
            errors.append(f'The {LABELS[fmt]} could not be built. Check for unusual characters or images, then try again.')
    return rows, errors


def delete_render(render):
    _remove_file(render)
    db.session.delete(render)


def delete_book_files(book):
    """Remove the stored files of a book that is about to be deleted (the rows go with the book)."""
    for render in list(book.renders):
        _remove_file(render)


def save_to_export_folder(render):
    """Copy a stored book into the configured export folder; returns the path written."""
    folder = current_app.config.get('EXPORT_DIR')
    source = stored_path(render)
    if not folder or source is None:
        raise FileNotFoundError('No export folder is configured, or the stored file is missing.')
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(render.file_name).stem, Path(render.file_name).suffix
    target, number = folder / render.file_name, 1
    while target.exists():                                  # never overwrite what is already there
        number += 1
        target = folder / f'{stem}-{number}{suffix}'
    target.write_bytes(source.read_bytes())
    return target


# ---- helpers for the routes ---------------------------------------------------------------------

def _back(book):
    return redirect(url_for('renders.list_renders', book_id=book.book_id))


def _selected(book):
    """The stored copies of this book ticked on the form (ids that are not this book's are ignored)."""
    wanted = {int(v) for v in request.form.getlist('ids') if v.isdigit()}
    return [r for r in book.renders if r.render_id in wanted and r.user_id == current_user.user_id]


def _read(render):
    path = stored_path(render)
    if path is None:
        flash('That file is no longer on disk. Use Replace to build it again.', 'danger')
        return None
    return path


# ---- pages ----------------------------------------------------------------------------------------------

@bp.route('/books/<int:book_id>/renders')
@login_required
def list_renders(book_id):
    book = owned_book_or_404(book_id)
    rows = [{'render': r, 'present': stored_path(r) is not None} for r in book.renders]
    counts = {fmt: count_for(book, fmt) for fmt in RENDER_FORMAT_KEYS}
    return render_template('renders/list.html', book=book, rows=rows, formats=RENDER_FORMATS, counts=counts,
                           maximum=MAX_RENDERS_PER_FORMAT, printable=PRINTABLE,
                           export_dir=current_app.config.get('EXPORT_DIR'))


@bp.route('/books/<int:book_id>/renders/generate', methods=['POST'])
@login_required
def generate_renders(book_id):
    book = owned_book_or_404(book_id)
    formats = [f for f in request.form.getlist('formats') if f in RENDER_FORMAT_KEYS]
    if request.form.get('all'):
        formats = list(RENDER_FORMAT_KEYS)
    if not formats:
        flash('Choose at least one format to generate.', 'warning')
        return _back(book)
    rows, errors = generate(book, formats)
    for message in errors:
        flash(message, 'danger')
    if rows:
        flash('Generated ' + ', '.join(LABELS[r.format] for r in rows) + f' (version {book.version}).', 'success')
    return _back(book)


@bp.route('/renders/<int:render_id>/replace', methods=['POST'])
@login_required
def replace_render(render_id):
    render = owned_render_or_404(render_id)
    book = render.book
    rows, errors = generate(book, [render.format], replace=render)
    for message in errors:
        flash(message, 'danger')
    if rows:
        flash(f'{LABELS[render.format]} replaced with a freshly generated version.', 'success')
    return _back(book)


@bp.route('/renders/<int:render_id>/delete', methods=['POST'])
@login_required
def delete_one(render_id):
    render = owned_render_or_404(render_id)
    book = render.book
    delete_render(render)
    db.session.commit()
    flash('Deleted.', 'success')
    return _back(book)


@bp.route('/renders/<int:render_id>/download')
@login_required
def download(render_id):
    render = owned_render_or_404(render_id)
    path = _read(render)
    if path is None:
        return _back(render.book)
    return send_file(path, mimetype=render.mime_type, as_attachment=True, download_name=render.file_name)


@bp.route('/renders/<int:render_id>/view')
@login_required
def view(render_id):
    """Show a stored PDF or HTML in the browser. HTML is locked down (no scripts, no network, sandboxed)."""
    render = owned_render_or_404(render_id)
    if render.format not in PRINTABLE:
        abort(404)
    path = _read(render)
    if path is None:
        return _back(render.book)
    if render.format == 'pdf':
        return send_file(path, mimetype='application/pdf', as_attachment=False, download_name=render.file_name)
    html = path.read_text(encoding='utf-8')
    csp = VIEW_CSP
    if request.args.get('print') == '1':
        # Only this one inline script (identified by its nonce) may run, to open the print dialog.
        nonce = secrets.token_urlsafe(16)
        html = html.replace('</body>', f'<script nonce="{nonce}">window.addEventListener("load",'
                                       f'function(){{window.print();}});</script></body>', 1)
        csp = VIEW_CSP.replace("sandbox", f"script-src 'nonce-{nonce}'; sandbox allow-scripts allow-modals")
    response = Response(html, mimetype='text/html')
    response.headers['Content-Security-Policy'] = csp
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/renders/<int:render_id>/print')
@login_required
def print_render(render_id):
    """Open the browser's print dialog for a stored PDF or HTML (the dialog lists the computer's printers)."""
    render = owned_render_or_404(render_id)
    if render.format not in PRINTABLE:
        abort(404)
    if _read(render) is None:
        return _back(render.book)
    if render.format == 'html':
        return redirect(url_for('renders.view', render_id=render.render_id, print=1))
    return render_template('renders/print.html', render=render, book=render.book)


@bp.route('/renders/<int:render_id>/save-to-folder', methods=['POST'])
@login_required
def save_to_folder(render_id):
    render = owned_render_or_404(render_id)
    if not current_app.config.get('EXPORT_DIR'):
        abort(404)
    try:
        target = save_to_export_folder(render)
    except OSError as exc:
        log.warning('Export folder save failed: %s', exc)
        flash('The copy could not be saved to the export folder.', 'danger')
    else:
        flash(f'Saved a copy to {target}.', 'success')
    return _back(render.book)


@bp.route('/books/<int:book_id>/renders/selected', methods=['POST'])
@login_required
def selected_action(book_id):
    """Download as one zip, delete, or save to the export folder: the copies that are ticked."""
    book = owned_book_or_404(book_id)
    action = request.form.get('action')
    chosen = _selected(book)
    if not chosen:
        flash('Tick at least one stored copy first.', 'warning')
        return _back(book)
    if action == 'delete':
        for render in chosen:
            delete_render(render)
        db.session.commit()
        flash(f'Deleted {len(chosen)} stored cop{"y" if len(chosen) == 1 else "ies"}.', 'success')
        return _back(book)
    if action == 'save-to-folder':
        if not current_app.config.get('EXPORT_DIR'):
            abort(404)
        saved = 0
        for render in chosen:
            try:
                save_to_export_folder(render)
                saved += 1
            except OSError:
                pass
        flash(f'Saved {saved} of {len(chosen)} to the export folder.', 'success' if saved == len(chosen) else 'warning')
        return _back(book)
    if action == 'zip':
        buffer, names = io.BytesIO(), set()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for render in chosen:
                path = stored_path(render)
                if path is None:
                    continue
                name = render.file_name
                if name in names:                          # two copies of the same version: keep both
                    name = f'{Path(name).stem}-{render.render_id}{Path(name).suffix}'
                names.add(name)
                archive.write(path, name)
        if not names:
            flash('None of the ticked files are on disk any more.', 'danger')
            return _back(book)
        buffer.seek(0)
        zip_name = f'{secure_filename(book.title) or "book"}-{re.sub(r"[^0-9A-Za-z.]+", "", book.version)}.zip'
        return send_file(buffer, mimetype='application/zip', as_attachment=True, download_name=zip_name)
    abort(400)
