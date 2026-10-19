"""Helpers that build books straight in the test database (faster than driving the web forms)."""
import io

from models import (Book, BookAuthor, BookPage, BookTerm, Chapter, ContentBlock, MediaAsset, User, db)

FILLER = ('The quick brown fox jumps over the lazy dog while the committee deliberates at length about '
          'procedure, precedent and the many small rules that keep a large society running smoothly. ')


def make_user(username='writer', password='correct-horse-battery'):
    user = User(username=username, username_key=username.lower())
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def png_bytes(width=40, height=30, color='red'):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), color).save(buffer, 'PNG')
    return buffer.getvalue()


def make_asset(app, user, name='photo.png', data=None):
    """Store a real PNG for `user` and return its MediaAsset."""
    from pathlib import Path
    data = data or png_bytes()
    folder = Path(app.config['UPLOAD_DIR']) / str(user.user_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f'{name}'
    (folder / stored).write_bytes(data)
    asset = MediaAsset(user_id=user.user_id, asset_name=name, file_path=f'{user.user_id}/{stored}',
                       file_size=len(data), mime_type='image/png')
    db.session.add(asset)
    db.session.flush()
    return asset


def paragraph(token, sentences=5, extra=''):
    return f'{token} {extra} ' + FILLER * sentences


def make_book(user, title='Test Book', chapters=4, paragraphs=8, terms=(), settings=None, token_prefix='ZQ',
              inject=None):
    """A book with `chapters` chapters of `paragraphs` long text blocks, each starting with a unique token.

    Returns (book, tokens) where tokens maps block_id -> unique token text.
    """
    book = Book(owner=user, title=title, subtitle='A Subtitle', author_name='Ann Author',
                copyright_holder='Ann Author', copyright_year=2026)
    db.session.add(book)
    book.init_covers()
    tokens = {}
    for c in range(1, chapters + 1):
        chapter = Chapter(title=f'Chapter {c}', sort_order=c)
        book.chapters.append(chapter)
        for p in range(1, paragraphs + 1):
            token = f'{token_prefix}C{c}P{p}X'
            extra = (inject or {}).get((c, p), '')
            block = ContentBlock(block_type='text', content_text=paragraph(token, extra=extra), sort_order=p)
            chapter.blocks.append(block)
    for term, definition in terms:
        book.terms.append(BookTerm(term=term, definition=definition))
    if settings:
        from models import BookLayout
        book.layout = BookLayout(settings=settings)
    db.session.flush()
    for chapter in book.chapters:
        for block in chapter.blocks:
            tokens[block.block_id] = block.content_text.split()[0]
    return book, tokens


def add_front_matter(book):
    book.pages.append(BookPage(page_type='dedication', body='For my family', sort_order=1,
                               style={'align': 'center', 'valign': 'middle', 'italic': True, 'size': 'medium'}))
    book.pages.append(BookPage(page_type='quote', body='Nothing in the world\nis softer than water.', sort_order=2,
                               attribution='Tao Teh Ching #78, translated by John C. H. Wu'))
    db.session.flush()


def add_author(book, name='Ann Author', bio='Ann writes books.', role='Author', photo=None):
    author = BookAuthor(name=name, role=role, bio=bio, sort_order=len(book.authors) + 1,
                        photo_asset_id=photo.asset_id if photo else None)
    book.authors.append(author)
    db.session.flush()
    return author
