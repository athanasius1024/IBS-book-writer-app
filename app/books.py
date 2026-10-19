"""Book management: dashboard, create/edit, complete, copy-to-edit, delete, preview."""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from access import ensure_editable, owned_book_or_404
from models import STATUS_COMPLETED, Book, Chapter, ContentBlock, MediaAsset, db

bp = Blueprint('books', __name__)


def _apply_form(book):
    """Copy the metadata form fields onto ``book``. Returns an error string or None."""
    title = (request.form.get('title') or '').strip()
    if not title:
        return 'A title is required.'
    if len(title) > 300:
        return 'The title is too long (300 characters max).'

    year_raw = (request.form.get('copyright_year') or '').strip()
    year = None
    if year_raw:
        if not year_raw.isdigit() or not (1 <= int(year_raw) <= 9999):
            return 'Copyright year must be a valid year.'
        year = int(year_raw)

    version = (request.form.get('version') or '').strip() or '0.1'
    if len(version) > 20:
        return 'Version is too long (20 characters max).'

    book.title = title
    book.subtitle = (request.form.get('subtitle') or '').strip() or None
    book.author_name = (request.form.get('author_name') or '').strip() or None
    book.copyright_holder = (request.form.get('copyright_holder') or '').strip() or None
    book.copyright_year = year
    book.version = version
    return None


def _user_books():
    return (Book.query.filter_by(user_id=current_user.user_id)
            .order_by(Book.modified_at.desc(), Book.book_id.desc()).all())


@bp.route('/')
@login_required
def dashboard():
    """Overview: stat cards, recent books, status of the latest book, quick actions."""
    uid = current_user.user_id
    books = _user_books()
    stats = {
        'books': len(books),
        'drafts': sum(1 for b in books if not b.is_completed),
        'completed': sum(1 for b in books if b.is_completed),
        'chapters': (db.session.query(func.count(Chapter.chapter_id)).select_from(Chapter)
                     .join(Book, Chapter.book_id == Book.book_id)
                     .filter(Book.user_id == uid).scalar()),
        'blocks': (db.session.query(func.count(ContentBlock.block_id)).select_from(ContentBlock)
                   .join(Chapter, ContentBlock.chapter_id == Chapter.chapter_id)
                   .join(Book, Chapter.book_id == Book.book_id)
                   .filter(Book.user_id == uid).scalar()),
        'images': MediaAsset.query.filter_by(user_id=uid).count(),
    }
    latest = books[0] if books else None
    latest_draft = next((b for b in books if not b.is_completed), None)
    return render_template('books/dashboard.html', stats=stats, recent=books[:5],
                           latest=latest, latest_draft=latest_draft)


@bp.route('/books', endpoint='list')
@login_required
def book_list():
    return render_template('books/list.html', books=_user_books())


@bp.route('/books/new', methods=['GET', 'POST'])
@login_required
def new():
    book = Book(user_id=current_user.user_id, title='')
    if request.method == 'POST':
        error = _apply_form(book)
        if error:
            flash(error, 'danger')
        else:
            if book.copyright_year is None:
                book.copyright_year = datetime.utcnow().year
            if not book.copyright_holder:
                book.copyright_holder = book.author_name
            book.init_covers()
            db.session.add(book)
            db.session.commit()
            flash(f'Book "{book.title}" created.', 'success')
            return redirect(url_for('books.detail', book_id=book.book_id))
    return render_template('books/form.html', book=book, is_new=True)


@bp.route('/books/<int:book_id>')
@login_required
def detail(book_id):
    book = owned_book_or_404(book_id)
    return render_template('books/detail.html', book=book)


@bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    if request.method == 'POST':
        error = _apply_form(book)
        if error:
            flash(error, 'danger')
            db.session.rollback()
        else:
            book.touch()
            db.session.commit()
            flash('Book details saved.', 'success')
            return redirect(url_for('books.detail', book_id=book.book_id))
    return render_template('books/form.html', book=book, is_new=False)


@bp.route('/books/<int:book_id>/complete', methods=['POST'])
@login_required
def complete(book_id):
    book = owned_book_or_404(book_id)
    if book.is_completed:
        flash('This book is already marked completed.', 'info')
    else:
        book.status = STATUS_COMPLETED
        book.completed_at = datetime.utcnow()
        book.touch()
        db.session.commit()
        flash(f'"{book.title}" is marked completed and is now read-only.', 'success')
    return redirect(url_for('books.detail', book_id=book.book_id))


@bp.route('/books/<int:book_id>/copy', methods=['POST'])
@login_required
def copy(book_id):
    """Create a new editable draft from a book (the original is never modified)."""
    book = owned_book_or_404(book_id)
    new_book = book.duplicate()
    db.session.add(new_book)
    db.session.commit()
    flash(f'Created editable copy "{new_book.title}". The original was not changed.', 'success')
    return redirect(url_for('books.detail', book_id=new_book.book_id))


@bp.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
def delete(book_id):
    book = owned_book_or_404(book_id)
    title = book.title
    db.session.delete(book)
    db.session.commit()
    flash(f'Book "{title}" deleted.', 'success')
    return redirect(url_for('books.list'))


@bp.route('/books/<int:book_id>/preview')
@login_required
def preview(book_id):
    book = owned_book_or_404(book_id)
    return render_template('books/preview.html', book=book)
