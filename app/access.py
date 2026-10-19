"""Per-user ownership checks and the completed-book edit lock.

Every route that touches a book, cover, chapter, content block or media asset
goes through these helpers, so a user can only ever reach their own data.
Missing *and* foreign records both produce a 404 (never 403) so IDs of other
users' records are not revealed.
"""
from functools import wraps

from flask import abort, flash, make_response, redirect, request, url_for
from flask_login import current_user

from models import Book, BookAuthor, BookPage, BookTerm, Chapter, ContentBlock, MediaAsset

COMPLETED_MESSAGE = ('This book is completed and read-only. '
                     'Create an editable copy to make changes.')


def bad_request(message):
    """Abort with a 400 whose body is a short plain-text message (shown by the HTMX error handler)."""
    abort(make_response(message, 400))


def owned_book_or_404(book_id):
    book = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if book is None:
        abort(404)
    return book


def owned_chapter_or_404(chapter_id):
    chapter = (Chapter.query.join(Book, Chapter.book_id == Book.book_id)
               .filter(Chapter.chapter_id == chapter_id, Book.user_id == current_user.user_id)
               .first())
    if chapter is None:
        abort(404)
    return chapter


def owned_block_or_404(block_id):
    block = (ContentBlock.query
             .join(Chapter, ContentBlock.chapter_id == Chapter.chapter_id)
             .join(Book, Chapter.book_id == Book.book_id)
             .filter(ContentBlock.block_id == block_id, Book.user_id == current_user.user_id)
             .first())
    if block is None:
        abort(404)
    return block


def _owned_child_or_404(model, key, value):
    row = (model.query.join(Book, model.book_id == Book.book_id)
           .filter(key == value, Book.user_id == current_user.user_id).first())
    if row is None:
        abort(404)
    return row


def owned_page_or_404(page_id):
    return _owned_child_or_404(BookPage, BookPage.page_id, page_id)


def owned_author_or_404(author_id):
    return _owned_child_or_404(BookAuthor, BookAuthor.author_id, author_id)


def owned_term_or_404(term_id):
    return _owned_child_or_404(BookTerm, BookTerm.term_id, term_id)


def owned_asset_or_404(asset_id):
    asset = MediaAsset.query.filter_by(asset_id=asset_id, user_id=current_user.user_id).first()
    if asset is None:
        abort(404)
    return asset


def ensure_editable(book):
    """Abort the request if the book is completed (server-side edit lock)."""
    if not book.is_completed:
        return
    if request.headers.get('HX-Request'):
        abort(make_response(COMPLETED_MESSAGE, 409))
    flash(COMPLETED_MESSAGE, 'warning')
    abort(redirect(url_for('books.detail', book_id=book.book_id)))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not (current_user.is_authenticated and current_user.is_admin):
            abort(404)
        return view(*args, **kwargs)
    return wrapped
