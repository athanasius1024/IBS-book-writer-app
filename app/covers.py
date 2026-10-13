"""Book cover editor: front, spine (binding), back, inside front, inside back."""
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from access import ensure_editable, owned_book_or_404
from media import save_image
from models import COVER_PANEL_KEYS, BookCover, db

bp = Blueprint('covers', __name__)

HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
MAX_TEXT = 20000


@bp.route('/books/<int:book_id>/cover')
@login_required
def editor(book_id):
    book = owned_book_or_404(book_id)
    if not book.is_completed and len(book.covers) < len(COVER_PANEL_KEYS):
        book.init_covers()  # repair books created before all panels existed
        db.session.commit()
    return render_template('covers/editor.html', book=book)


@bp.route('/books/<int:book_id>/cover/layout')
@login_required
def layout(book_id):
    """Flat wrap-around view (back | spine | front) plus both inside covers."""
    book = owned_book_or_404(book_id)
    return render_template('covers/layout.html', book=book)


@bp.route('/books/<int:book_id>/cover/<panel>', methods=['POST'])
@login_required
def save_panel(book_id, panel):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    if panel not in COVER_PANEL_KEYS:
        abort(404)

    cover = book.cover(panel)
    if cover is None:
        cover = BookCover(panel=panel)
        book.covers.append(cover)

    error = None
    background = (request.form.get('background_color') or cover.background_color).strip()
    text_color = (request.form.get('text_color') or cover.text_color).strip()
    if not (HEX_COLOR.match(background) and HEX_COLOR.match(text_color)):
        error = 'Colors must be in #rrggbb format.'
    else:
        cover.content_text = (request.form.get('content_text') or '')[:MAX_TEXT]
        cover.background_color = background
        cover.text_color = text_color

        upload = request.files.get('image')
        if upload and upload.filename:
            try:
                asset = save_image(upload, book.user_id)
            except ValueError as exc:
                error = str(exc)
            else:
                db.session.add(asset)
                db.session.flush()
                cover.asset_id = asset.asset_id
        elif request.form.get('remove_image'):
            cover.asset_id = None

    if error is None:
        book.touch()
        db.session.commit()
    else:
        db.session.rollback()
        cover = book.cover(panel)  # discard unsaved edits

    if not request.headers.get('HX-Request'):
        flash(error or f'{cover.label} saved.', 'danger' if error else 'success')
        return redirect(url_for('covers.editor', book_id=book.book_id))
    return render_template('covers/_panel.html', book=book, cover=cover,
                           saved=error is None, error=error)
