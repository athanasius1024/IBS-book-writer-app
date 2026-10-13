"""Chapters and their markdown content blocks."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from access import ensure_editable, owned_block_or_404, owned_book_or_404, owned_chapter_or_404
from models import Chapter, ContentBlock, db

bp = Blueprint('chapters', __name__)

MAX_BLOCK = 100000


def _next_order(items):
    return (max((i.sort_order for i in items), default=0) or 0) + 1


def _move(items, target, direction):
    """Swap ``target`` with its neighbour and renumber ``sort_order`` 1..n."""
    items = list(items)
    index = items.index(target)
    swap = index - 1 if direction == 'up' else index + 1
    if 0 <= swap < len(items):
        items[index], items[swap] = items[swap], items[index]
    for position, item in enumerate(items, start=1):
        item.sort_order = position


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
    return render_template('chapters/edit.html', chapter=chapter, book=chapter.book)


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
    chapter = owned_chapter_or_404(chapter_id)
    ensure_editable(chapter.book)
    text = (request.form.get('content_text') or '')[:MAX_BLOCK]
    if not text.strip():
        abort(400)
    block = ContentBlock(content_text=text, sort_order=_next_order(chapter.blocks))
    chapter.blocks.append(block)
    chapter.book.touch()
    db.session.commit()
    return render_template('chapters/_block.html', block=block, book=chapter.book)


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
    return render_template('chapters/_block_form.html', block=block)


@bp.route('/blocks/<int:block_id>/save', methods=['POST'])
@login_required
def block_save(block_id):
    block = owned_block_or_404(block_id)
    book = block.chapter.book
    ensure_editable(book)
    text = (request.form.get('content_text') or '')[:MAX_BLOCK]
    if not text.strip():
        abort(400)
    block.content_text = text
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
