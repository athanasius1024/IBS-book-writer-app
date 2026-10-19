#!/usr/bin/env python3
"""Upgrade the imported "Terran Society" book to the Dedication, Quote, Glossary/Index and Authors features.

What it does (all in ONE transaction - everything or nothing):
  * splits the text that the import put on the Inside Front Cover: the dedication line becomes a
    Dedication page, the Tao Teh Ching verse (with its attribution) becomes a Quote page, and the
    Inside Front Cover is cleared
  * turns the 74-row Glossary table chapter into glossary/index terms and removes that chapter
    (the Glossary is now generated, with page numbers and links)
  * adds the author entry, taking the bio from the original database (read-only)
  * proves nothing was lost (letters and digits of the old text equal the new text), then builds the
    PDF layout and the EPUB once to show the book still renders

Usage (the password comes from the environment so it never appears in a file):
    TERRAN_DB_PASSWORD=... .venv/bin/python scripts/upgrade_terran_book.py --dry-run   # change nothing
    TERRAN_DB_PASSWORD=... .venv/bin/python scripts/upgrade_terran_book.py             # do it
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))


class UpgradeError(Exception):
    """The book is not in the expected shape; nothing was changed."""


def alnum(text):
    return re.sub(r'[\W_]+', '', text or '', flags=re.UNICODE).lower()


def split_inside_front(text):
    """(dedication, verse, attribution) from the text the import placed on the Inside Front Cover."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', (text or '').replace('\r\n', '\n')) if p.strip()]
    if len(paragraphs) < 3:
        raise UpgradeError('The Inside Front Cover does not look like the imported dedication and verse.')
    match = re.fullmatch(r'\*(.+)\*', paragraphs[-1], re.S)
    if not match:
        raise UpgradeError('The Inside Front Cover has no italic attribution line at the end.')
    attribution = re.sub(r'\s+-\s+', ', ', match.group(1).strip())
    dedication = paragraphs[0]
    verse = re.sub(r' {2,}\n', '\n', '\n\n'.join(paragraphs[1:-1])).strip()   # line breaks are kept by the page itself
    if not dedication or not verse:
        raise UpgradeError('Could not separate the dedication from the verse.')
    return dedication, verse, attribution


def find_glossary_table(book):
    """(chapter, [(term, definition)]) for the imported Glossary chapter."""
    chapter = next((c for c in book.chapters if c.title.strip().lower() == 'glossary'), None)
    if chapter is None:
        raise UpgradeError('There is no "Glossary" chapter to convert.')
    tables = [b for b in chapter.blocks if b.block_type == 'table']
    if len(chapter.blocks) != 1 or len(tables) != 1:
        raise UpgradeError('The Glossary chapter is not a single table; refusing to convert it.')
    data = tables[0].content_data or {}
    rows = data.get('rows') or []
    if not data.get('header') or not rows or [c.strip().lower() for c in rows[0][:2]] != ['term', 'definition']:
        raise UpgradeError('The Glossary table does not have a "Term | Definition" header.')
    pairs = [(r[0].strip(), (r[1] if len(r) > 1 else '').strip()) for r in rows[1:] if r and r[0].strip()]
    if not pairs:
        raise UpgradeError('The Glossary table has no terms.')
    return chapter, pairs


def upgrade_book(book, author_name, author_bio):
    """Apply the upgrade to `book` in the current session (the caller commits). Returns a summary dict."""
    from models import BookAuthor, BookPage, BookTerm

    if book.pages or book.authors or book.terms:
        raise UpgradeError('This book already has front matter pages, authors or terms: already upgraded?')
    cover = book.cover('inside_front')
    original = cover.content_text if cover else ''
    dedication, verse, attribution = split_inside_front(original)
    chapter, pairs = find_glossary_table(book)

    book.pages.append(BookPage(page_type='dedication', body=dedication, sort_order=1,
                               style={'align': 'center', 'valign': 'middle', 'italic': True, 'size': 'medium'}))
    book.pages.append(BookPage(page_type='quote', body=verse, attribution=attribution, sort_order=2,
                               style={'align': 'center', 'valign': 'middle', 'italic': True, 'size': 'medium'}))
    cover.content_text = ''

    for term, definition in pairs:
        book.terms.append(BookTerm(term=term, definition=definition or None, match_plural=True, match_case=False,
                                   in_index=True, in_glossary=True))
    book.chapters.remove(chapter)                       # delete-orphan removes its table block too
    for number, remaining in enumerate(book.chapters, start=1):
        remaining.sort_order = number

    book.authors.append(BookAuthor(name=author_name, role='Author', bio=author_bio or None, sort_order=1))
    book.touch()

    # Nothing may be lost: every letter and digit of the old cover text is on the new pages.
    if alnum(dedication + verse + attribution) != alnum(original):
        raise UpgradeError('VERIFY FAILED: the split pages do not contain exactly the old cover text.')
    if [(t.term, t.definition or '') for t in book.terms] != pairs:
        raise UpgradeError('VERIFY FAILED: the terms do not match the old Glossary table.')
    return {'dedication': dedication, 'verse_lines': verse.count('\n') + 1, 'attribution': attribution,
            'terms': len(pairs), 'chapters_left': len(book.chapters)}


def read_author_bio(name):
    """Author bio from the original database (read-only session)."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get('TERRAN_DB_HOST', 'localhost'), port=os.environ.get('TERRAN_DB_PORT', '5432'),
        dbname=os.environ.get('TERRAN_DB_NAME', 'db_terran_society'), user=os.environ.get('TERRAN_DB_USER', 'rock'),
        password=os.environ.get('TERRAN_DB_PASSWORD', ''), options='-c default_transaction_read_only=on')
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT author_bio FROM scm_terran_society.book_author WHERE author_name = %s LIMIT 1', (name,))
            row = cur.fetchone()
    finally:
        conn.close()
    return (row[0] or '').strip() if row else ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--username', default='APA')
    parser.add_argument('--title', default='Terran Society')
    parser.add_argument('--author', default='Angelo Patrick Arteman')
    parser.add_argument('--author-bio', default=None, help='use this bio instead of reading it from the old database')
    parser.add_argument('--dry-run', action='store_true', help='do everything, then roll back')
    parser.add_argument('--no-build-check', action='store_true', help='skip the PDF/EPUB build check')
    args = parser.parse_args()

    bio = args.author_bio if args.author_bio is not None else read_author_bio(args.author)

    from ibsbook import create_app
    from models import Book, User, db

    app = create_app()
    with app.app_context():
        url = db.engine.url
        print(f'target database: {url.drivername}://{url.host}/{url.database}')
        if url.drivername.split('+')[0] != 'postgresql' or url.database != 'db_ibs_bookwriter':
            sys.exit('Refusing to run: target is not the db_ibs_bookwriter PostgreSQL database.')
        user = User.query.filter_by(username_key=args.username.strip().lower()).first()
        if user is None:
            sys.exit(f'No user named "{args.username}".')
        books = Book.query.filter_by(user_id=user.user_id, title=args.title).all()
        if len(books) != 1:
            sys.exit(f'Expected exactly one book titled "{args.title}" for {args.username}, found {len(books)}.')
        book = books[0]

        try:
            summary = upgrade_book(book, args.author, bio)
            db.session.flush()
        except UpgradeError as error:
            db.session.rollback()
            sys.exit(f'{error}\nNothing was changed.')

        print(f'book #{book.book_id} "{book.title}": dedication {summary["dedication"]!r}')
        print(f'quote page: {summary["verse_lines"]} lines, attribution {summary["attribution"]!r}')
        print(f'terms created from the glossary table: {summary["terms"]}; chapters now: {summary["chapters_left"]}')
        print(f'author: {args.author} (bio {"set" if bio else "empty"})')
        print('text check OK: the old cover text equals the new Dedication + Quote pages')

        if not args.no_build_check:
            from epub import build_epub
            from render import get_layout
            result = get_layout(book)
            epub = build_epub(book, result)
            doc = result.doc
            used = sum(1 for t in book.terms if doc.annotator.occurrences.get(t.term_id))
            print(f'build check OK: PDF {result.physical_pages} pages ({len(result.pdf):,} bytes, {result.passes} layout passes), '
                  f'body pages 1-{max(result.pages.values())}, EPUB {len(epub):,} bytes')
            print(f'glossary entries: {len(doc.glossary_terms())}; index terms with uses: {used} of {len(book.terms)}')

        if args.dry_run:
            db.session.rollback()
            print('DRY RUN: rolled back, nothing was written.')
        else:
            db.session.commit()
            print('COMMITTED.')


if __name__ == '__main__':
    main()
