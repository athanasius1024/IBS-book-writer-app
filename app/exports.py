"""Page layout settings, the Page view, and PDF / EPUB downloads."""
import io
import logging

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from werkzeug.utils import secure_filename

import layout as layout_module
from access import ensure_editable, owned_book_or_404
from epub import build_epub
from models import BookLayout, db
from render import get_layout

bp = Blueprint('exports', __name__)
log = logging.getLogger(__name__)


def _download_name(book, extension):
    return f'{secure_filename(book.title) or "book"}.{extension}'


def _render_or_fail(book, build):
    """Run a (possibly slow) renderer; on failure log it and send the user back with a clear message."""
    try:
        return build()
    except Exception:
        log.exception('Export failed for book %s', book.book_id)
        flash('The book could not be built. Check for unusual characters or images, then try again.', 'danger')
        return None


@bp.route('/books/<int:book_id>/layout', methods=['GET', 'POST'])
@login_required
def layout_edit(book_id):
    book = owned_book_or_404(book_id)
    settings = layout_module.get_settings(book)
    if request.method == 'POST':
        ensure_editable(book)
        if request.form.get('reset'):
            if book.layout is not None:
                db.session.delete(book.layout)
            book.touch()
            db.session.commit()
            flash('Layout reset to the defaults.', 'success')
            return redirect(url_for('exports.layout_edit', book_id=book.book_id))
        new_settings, errors = layout_module.parse_form(request.form, settings)
        if errors:
            for message in errors:
                flash(message, 'danger')
            settings = new_settings        # keep what the user typed on screen
        else:
            if book.layout is None:
                book.layout = BookLayout(settings=new_settings)
            else:
                book.layout.settings = new_settings
            book.touch()
            db.session.commit()
            flash('Layout saved. The Page view below shows the result.', 'success')
            return redirect(url_for('exports.layout_edit', book_id=book.book_id))
    return render_template('layout/edit.html', book=book, settings=settings, presets=layout_module.PRESETS,
                           fonts=layout_module.FONTS, enums=layout_module.ENUMS)


@bp.route('/books/<int:book_id>/layout/preview.pdf')
@login_required
def page_view(book_id):
    """The Page view: the exact PDF an export would produce, shown inline in the browser."""
    book = owned_book_or_404(book_id)
    result = _render_or_fail(book, lambda: get_layout(book))
    if result is None:
        return redirect(url_for('exports.layout_edit', book_id=book.book_id))
    return send_file(io.BytesIO(result.pdf), mimetype='application/pdf', download_name=_download_name(book, 'pdf'))


@bp.route('/books/<int:book_id>/export/pdf')
@login_required
def export_pdf(book_id):
    book = owned_book_or_404(book_id)
    result = _render_or_fail(book, lambda: get_layout(book))
    if result is None:
        return redirect(url_for('books.detail', book_id=book.book_id))
    return send_file(io.BytesIO(result.pdf), mimetype='application/pdf', as_attachment=True,
                     download_name=_download_name(book, 'pdf'))


@bp.route('/books/<int:book_id>/export/epub')
@login_required
def export_epub(book_id):
    book = owned_book_or_404(book_id)
    data = _render_or_fail(book, lambda: build_epub(book, get_layout(book)))
    if data is None:
        return redirect(url_for('books.detail', book_id=book.book_id))
    return send_file(io.BytesIO(data), mimetype='application/epub+zip', as_attachment=True,
                     download_name=_download_name(book, 'epub'))
