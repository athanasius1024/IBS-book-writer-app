"""Front matter pages (Dedication, Quote) and the authors of a book."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from access import ensure_editable, owned_author_or_404, owned_book_or_404, owned_page_or_404
from layout import PAGE_STYLE_CHOICES, PAGE_STYLE_DEFAULTS, page_style
from media import save_image
from models import PAGE_TYPE_KEYS, PAGE_TYPES, Book, BookAuthor, BookPage, MediaAsset, db

bp = Blueprint('matter', __name__)

MAX_BODY = 5000
MAX_LINE = 300
MAX_BIO = 10000


def _renumber(items):
    for position, item in enumerate(items, start=1):
        item.sort_order = position


def _swap(items, target, direction):
    """Swap `target` with its neighbour and renumber sort_order 1..n."""
    items = list(items)
    index = items.index(target)
    other = index - 1 if direction == 'up' else index + 1
    if 0 <= other < len(items):
        items[index], items[other] = items[other], items[index]
    _renumber(items)


def _direction():
    direction = request.form.get('direction')
    if direction not in ('up', 'down'):
        abort(400)
    return direction


# ---- Dedication / Quote pages ----------------------------------------------------------------

def _style_from_form():
    style = {key: request.form.get(key) for key in PAGE_STYLE_CHOICES}
    style['italic'] = 'italic' in request.form
    return page_style(style)


def _apply_page_form(page):
    body = (request.form.get('body') or '').replace('\r\n', '\n').strip('\n')
    if not body.strip():
        return 'Please enter the text for this page.'
    if len(body) > MAX_BODY:
        return f'The text is limited to {MAX_BODY} characters.'
    attribution = (request.form.get('attribution') or '').strip()
    if len(attribution) > MAX_LINE:
        return f'The attribution is limited to {MAX_LINE} characters.'
    page.body = body
    page.attribution = attribution or None
    page.style = _style_from_form()
    return None


def _page_form_context(page, is_new):
    # Values to show: the submitted ones after an error, otherwise the stored ones.
    style = _style_from_form() if request.method == 'POST' else page_style(page.style)
    return {'page': page, 'is_new': is_new, 'style': style, 'choices': PAGE_STYLE_CHOICES,
            'type_label': dict(PAGE_TYPES)[page.page_type]}


@bp.route('/books/<int:book_id>/pages/new', methods=['GET', 'POST'])
@login_required
def page_new(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    page_type = request.args.get('type') or request.form.get('page_type')
    if page_type not in PAGE_TYPE_KEYS:
        abort(404)
    existing = next((p for p in book.pages if p.page_type == 'dedication'), None)
    if page_type == 'dedication' and existing is not None:
        flash('This book already has a Dedication page. You can edit it here.', 'info')
        return redirect(url_for('matter.page_edit', page_id=existing.page_id))

    page = BookPage(page_type=page_type, body='', style=dict(PAGE_STYLE_DEFAULTS))
    if request.method == 'POST':
        error = _apply_page_form(page)
        if error:
            flash(error, 'danger')
        else:
            orders = [p.sort_order for p in book.pages]
            # a Dedication belongs before the Quote pages; a Quote goes last
            page.sort_order = (min(orders) - 1) if (page_type == 'dedication' and orders) else (max(orders, default=0) + 1)
            book.pages.append(page)
            _renumber(sorted(book.pages, key=lambda p: (p.sort_order, p.page_id or 10 ** 9)))
            book.touch()
            db.session.commit()
            flash(f'{dict(PAGE_TYPES)[page_type]} page added.', 'success')
            return redirect(url_for('books.detail', book_id=book.book_id))
    return render_template('matter/page_form.html', book=book, **_page_form_context(page, True))


@bp.route('/pages/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
def page_edit(page_id):
    page = owned_page_or_404(page_id)
    book = page.book
    ensure_editable(book)
    if request.method == 'POST':
        error = _apply_page_form(page)
        if error:
            flash(error, 'danger')
            db.session.rollback()
        else:
            book.touch()
            db.session.commit()
            flash('Page saved.', 'success')
            return redirect(url_for('books.detail', book_id=book.book_id))
    return render_template('matter/page_form.html', book=book, **_page_form_context(page, False))


@bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
def page_delete(page_id):
    page = owned_page_or_404(page_id)
    book = page.book
    ensure_editable(book)
    db.session.delete(page)
    book.touch()
    db.session.commit()
    flash('Page deleted.', 'success')
    return redirect(url_for('books.detail', book_id=book.book_id))


@bp.route('/pages/<int:page_id>/move', methods=['POST'])
@login_required
def page_move(page_id):
    page = owned_page_or_404(page_id)
    book = page.book
    ensure_editable(book)
    _swap(book.pages, page, _direction())
    book.touch()
    db.session.commit()
    return redirect(url_for('books.detail', book_id=book.book_id))


# ---- Authors --------------------------------------------------------------------------------------

def _other_authors():
    """Authors from the user's other books, for 'add from an earlier book'."""
    return (BookAuthor.query.join(Book, BookAuthor.book_id == Book.book_id)
            .filter(Book.user_id == current_user.user_id)
            .order_by(BookAuthor.name, BookAuthor.author_id).all())


def _apply_author_form(author, book):
    name = (request.form.get('name') or '').strip()
    if not name:
        return 'The author needs a name.'
    role = (request.form.get('role') or '').strip()
    bio = (request.form.get('bio') or '').replace('\r\n', '\n').strip()
    if len(name) > MAX_LINE or len(role) > MAX_LINE:
        return f'Name and role are limited to {MAX_LINE} characters.'
    if len(bio) > MAX_BIO:
        return f'The bio is limited to {MAX_BIO} characters.'

    upload = request.files.get('photo')
    photo_id = request.form.get('photo_asset_id', type=int)
    new_photo = None
    if upload and upload.filename:
        try:
            new_photo = save_image(upload, book.user_id)
        except ValueError as exc:
            return str(exc)
        db.session.add(new_photo)
        db.session.flush()
    elif photo_id:
        new_photo = MediaAsset.query.filter_by(asset_id=photo_id, user_id=book.user_id).first()
        if new_photo is None:
            return 'That photo was not found in your library.'

    author.name, author.role, author.bio = name, role or None, bio or None
    if new_photo is not None:
        author.photo_asset_id = new_photo.asset_id
    elif request.form.get('remove_photo'):
        author.photo_asset_id = None
    return None


def _library():
    return (MediaAsset.query.filter_by(user_id=current_user.user_id)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.asset_id.desc()).all())


@bp.route('/books/<int:book_id>/authors')
@login_required
def authors(book_id):
    book = owned_book_or_404(book_id)
    return render_template('matter/authors.html', book=book, others=_other_authors())


@bp.route('/books/<int:book_id>/authors/new', methods=['GET', 'POST'])
@login_required
def author_new(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    author = BookAuthor(name='')
    prefill = None
    source_id = request.args.get('from', type=int)
    if source_id and request.method == 'GET':
        source = next((a for a in _other_authors() if a.author_id == source_id), None)
        if source is None:
            abort(404)
        # The text is copied, so the original book's bio stays exactly as it was written.
        author.name, author.role, author.bio = source.name, source.role, source.bio
        author.photo_asset_id = source.photo_asset_id
        prefill = source
    if request.method == 'POST':
        error = _apply_author_form(author, book)
        if error:
            flash(error, 'danger')
            db.session.rollback()
        else:
            author.sort_order = max((a.sort_order for a in book.authors), default=0) + 1
            book.authors.append(author)
            book.touch()
            db.session.commit()
            flash(f'Author "{author.name}" added.', 'success')
            return redirect(url_for('matter.authors', book_id=book.book_id))
    return render_template('matter/author_form.html', book=book, author=author, is_new=True,
                           library=_library(), prefill=prefill)


@bp.route('/authors/<int:author_id>/edit', methods=['GET', 'POST'])
@login_required
def author_edit(author_id):
    author = owned_author_or_404(author_id)
    book = author.book
    ensure_editable(book)
    if request.method == 'POST':
        error = _apply_author_form(author, book)
        if error:
            flash(error, 'danger')
            db.session.rollback()
            author = owned_author_or_404(author_id)
        else:
            book.touch()
            db.session.commit()
            flash('Author saved.', 'success')
            return redirect(url_for('matter.authors', book_id=book.book_id))
    return render_template('matter/author_form.html', book=book, author=author, is_new=False,
                           library=_library(), prefill=None)


@bp.route('/authors/<int:author_id>/delete', methods=['POST'])
@login_required
def author_delete(author_id):
    author = owned_author_or_404(author_id)
    book = author.book
    ensure_editable(book)
    db.session.delete(author)
    book.touch()
    db.session.commit()
    flash('Author removed.', 'success')
    return redirect(url_for('matter.authors', book_id=book.book_id))


@bp.route('/authors/<int:author_id>/move', methods=['POST'])
@login_required
def author_move(author_id):
    author = owned_author_or_404(author_id)
    book = author.book
    ensure_editable(book)
    _swap(book.authors, author, _direction())
    book.touch()
    db.session.commit()
    return redirect(url_for('matter.authors', book_id=book.book_id))
