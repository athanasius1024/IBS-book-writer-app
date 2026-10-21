"""Chapters and their content blocks (text, heading, list, table, image, icon)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from access import (bad_request, ensure_editable, owned_block_or_404, owned_book_or_404,
                    owned_chapter_or_404)
from blocks import apply_block_form
from models import BLOCK_TYPE_KEYS, BLOCK_TYPES, Chapter, ContentBlock, MediaAsset, db

bp = Blueprint('chapters', __name__)


def _next_order(items):
    return (max((i.sort_order for i in items), default=0) or 0) + 1


def _renumber(items):
    for position, item in enumerate(items, start=1):
        item.sort_order = position


def _move(items, target, direction):
    """Swap ``target`` with its neighbour and renumber ``sort_order`` 1..n."""
    items = list(items)
    index = items.index(target)
    swap = index - 1 if direction == 'up' else index + 1
    if 0 <= swap < len(items):
        items[index], items[swap] = items[swap], items[index]
    _renumber(items)


def _user_assets():
    return (MediaAsset.query.filter_by(user_id=current_user.user_id)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.asset_id.desc()).all())


# ---- chapters -------------------------------------------------------------

@bp.route('/books/<int:book_id>/chapters/new', methods=['POST'])
@login_required
def chapter_new(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    title = (request.form.get('title') or '').strip()
    if not title:
        flash('A chapter title is required.', 'danger')
        return redirect(url_for('books.detail', book_id=book.book_id))
    chapter = Chapter(title=title[:300], sort_order=_next_order(book.chapters))
    book.chapters.append(chapter)
    book.touch()
    db.session.commit()
    return redirect(url_for('chapters.chapter_edit', chapter_id=chapter.chapter_id))


@bp.route('/chapters/<int:chapter_id>')
@login_required
def chapter_edit(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    return render_template('chapters/edit.html', chapter=chapter, book=chapter.book,
                           block_types=BLOCK_TYPES, assets=_user_assets())


@bp.route('/chapters/<int:chapter_id>/rename', methods=['POST'])
@login_required
def chapter_rename(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    ensure_editable(chapter.book)
    title = (request.form.get('title') or '').strip()
    if title:
        chapter.title = title[:300]
        chapter.book.touch()
        db.session.commit()
        flash('Chapter renamed.', 'success')
    else:
        flash('A chapter title is required.', 'danger')
    return redirect(url_for('chapters.chapter_edit', chapter_id=chapter.chapter_id))


MAX_EPIGRAPH = 2000
MAX_EPIGRAPH_SOURCE = 300


@bp.route('/chapters/<int:chapter_id>/epigraph', methods=['POST'])
@login_required
def chapter_epigraph(chapter_id):
    """Set, change or (with empty text) remove the epigraph shown under the chapter title."""
    chapter = owned_chapter_or_404(chapter_id)
    ensure_editable(chapter.book)
    text = (request.form.get('epigraph_text') or '').replace('\r\n', '\n').strip('\n')
    source = (request.form.get('epigraph_source') or '').strip()
    if len(text) > MAX_EPIGRAPH:
        flash(f'The epigraph is limited to {MAX_EPIGRAPH} characters.', 'danger')
    elif len(source) > MAX_EPIGRAPH_SOURCE:
        flash(f'The source is limited to {MAX_EPIGRAPH_SOURCE} characters.', 'danger')
    else:
        if text.strip():
            chapter.epigraph_text, chapter.epigraph_source = text, source or None
            flash('Epigraph saved.', 'success')
        else:                                   # no text: no epigraph (a source alone means nothing)
            chapter.epigraph_text = chapter.epigraph_source = None
            flash('Epigraph removed.', 'success')
        chapter.book.touch()
        db.session.commit()
    return redirect(url_for('chapters.chapter_edit', chapter_id=chapter.chapter_id))


@bp.route('/chapters/<int:chapter_id>/move', methods=['POST'])
@login_required
def chapter_move(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    book = chapter.book
    ensure_editable(book)
    direction = request.form.get('direction')
    if direction not in ('up', 'down'):
        abort(400)
    _move(book.chapters, chapter, direction)
    book.touch()
    db.session.commit()
    return redirect(url_for('books.detail', book_id=book.book_id))


@bp.route('/chapters/<int:chapter_id>/delete', methods=['POST'])
@login_required
def chapter_delete(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    book = chapter.book
    ensure_editable(book)
    db.session.delete(chapter)
    book.touch()
    db.session.commit()
    flash('Chapter deleted.', 'success')
    return redirect(url_for('books.detail', book_id=book.book_id))


# ---- content blocks (HTMX partials) --------------------------------------

@bp.route('/chapters/<int:chapter_id>/blocks/new', methods=['POST'])
@login_required
def block_new(chapter_id):
    """Create a block. An optional ``position`` (1-based) inserts it there (used by Undo)."""
    chapter = owned_chapter_or_404(chapter_id)
    book = chapter.book
    ensure_editable(book)

    block_type = request.form.get('block_type') or 'text'
    if block_type not in BLOCK_TYPE_KEYS:
        bad_request('Unknown block type.')
    block = ContentBlock(block_type=block_type)
    error = apply_block_form(block, request.form, request.files, book.user_id)
    if error:
        db.session.rollback()
        bad_request(error)

    position = request.form.get('position', type=int)
    if position and position > 0:
        chapter.blocks.insert(min(position - 1, len(chapter.blocks)), block)
        _renumber(chapter.blocks)
    else:
        block.sort_order = _next_order(chapter.blocks)
        chapter.blocks.append(block)
    book.touch()
    db.session.commit()
    return render_template('chapters/_block.html', block=block, book=book)


@bp.route('/blocks/<int:block_id>')
@login_required
def block_view(block_id):
    block = owned_block_or_404(block_id)
    return render_template('chapters/_block.html', block=block, book=block.chapter.book)


@bp.route('/blocks/<int:block_id>/edit', methods=['GET'])
@login_required
def block_edit_form(block_id):
    block = owned_block_or_404(block_id)
    ensure_editable(block.chapter.book)
    return render_template('chapters/_block_form.html', block=block, assets=_user_assets())


@bp.route('/blocks/<int:block_id>/save', methods=['POST'])
@login_required
def block_save(block_id):
    block = owned_block_or_404(block_id)
    book = block.chapter.book
    ensure_editable(book)
    error = apply_block_form(block, request.form, request.files, book.user_id)
    if error:
        db.session.rollback()
        bad_request(error)
    book.touch()
    db.session.commit()
    return render_template('chapters/_block.html', block=block, book=book)


@bp.route('/blocks/<int:block_id>/move', methods=['POST'])
@login_required
def block_move(block_id):
    block = owned_block_or_404(block_id)
    chapter = block.chapter
    ensure_editable(chapter.book)
    direction = request.form.get('direction')
    if direction not in ('up', 'down'):
        abort(400)
    _move(chapter.blocks, block, direction)
    chapter.book.touch()
    db.session.commit()
    return redirect(url_for('chapters.chapter_edit', chapter_id=chapter.chapter_id))


@bp.route('/blocks/<int:block_id>/delete', methods=['DELETE', 'POST'])
@login_required
def block_delete(block_id):
    block = owned_block_or_404(block_id)
    chapter = block.chapter
    ensure_editable(chapter.book)
    db.session.delete(block)
    chapter.book.touch()
    db.session.commit()
    if request.headers.get('HX-Request'):
        return '', 200
    return redirect(url_for('chapters.chapter_edit', chapter_id=chapter.chapter_id))
