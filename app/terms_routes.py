"""Manage a book's glossary/index terms."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from access import ensure_editable, owned_book_or_404, owned_term_or_404
from bookdoc import usage_counts
from models import BookTerm, db

bp = Blueprint('terms', __name__)

MAX_TERM = 200
MAX_DEFINITION = 2000
MAX_VARIANTS = 20


def _apply_term_form(term, book):
    text = ' '.join((request.form.get('term') or '').split())
    if not text:
        return 'A term is required.'
    if len(text) > MAX_TERM:
        return f'A term is limited to {MAX_TERM} characters.'
    if any(t.term.lower() == text.lower() and t.term_id != term.term_id for t in book.terms):
        return f'"{text}" is already in this book\'s terms.'
    definition = (request.form.get('definition') or '').strip()
    if len(definition) > MAX_DEFINITION:
        return f'A definition is limited to {MAX_DEFINITION} characters.'
    variants = [' '.join(v.split()) for v in (request.form.get('variants') or '').splitlines() if v.strip()]
    if len(variants) > MAX_VARIANTS or any(len(v) > MAX_TERM for v in variants):
        return f'Use at most {MAX_VARIANTS} variants of up to {MAX_TERM} characters each.'

    term.term = text
    term.definition = definition or None
    term.variants = '\n'.join(variants) or None
    term.match_plural = 'match_plural' in request.form
    term.match_case = 'match_case' in request.form
    term.in_index = 'in_index' in request.form
    term.in_glossary = 'in_glossary' in request.form
    return None


@bp.route('/books/<int:book_id>/terms')
@login_required
def term_list(book_id):
    book = owned_book_or_404(book_id)
    counts = usage_counts(book)
    terms = sorted(book.terms, key=lambda t: t.term.lower())
    return render_template('terms/list.html', book=book, terms=terms, counts=counts)


@bp.route('/books/<int:book_id>/terms/new', methods=['GET', 'POST'])
@login_required
def term_new(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    term = BookTerm(term='', match_plural=True, match_case=False, in_index=True, in_glossary=True)
    if request.method == 'POST':
        error = _apply_term_form(term, book)
        if error:
            flash(error, 'danger')
        else:
            book.terms.append(term)
            book.touch()
            db.session.commit()
            flash(f'Term "{term.term}" added.', 'success')
            return redirect(url_for('terms.term_list', book_id=book.book_id))
    return render_template('terms/form.html', book=book, term=term, is_new=True)


@bp.route('/terms/<int:term_id>/edit', methods=['GET', 'POST'])
@login_required
def term_edit(term_id):
    term = owned_term_or_404(term_id)
    book = term.book
    ensure_editable(book)
    if request.method == 'POST':
        error = _apply_term_form(term, book)
        if error:
            flash(error, 'danger')
            db.session.rollback()
            term = owned_term_or_404(term_id)
        else:
            book.touch()
            db.session.commit()
            flash('Term saved.', 'success')
            return redirect(url_for('terms.term_list', book_id=book.book_id))
    return render_template('terms/form.html', book=book, term=term, is_new=False)


@bp.route('/terms/<int:term_id>/delete', methods=['POST'])
@login_required
def term_delete(term_id):
    term = owned_term_or_404(term_id)
    book = term.book
    ensure_editable(book)
    name = term.term
    db.session.delete(term)
    book.touch()
    db.session.commit()
    flash(f'Term "{name}" deleted.', 'success')
    return redirect(url_for('terms.term_list', book_id=book.book_id))
