import io

import pytest
from flask import current_app
from pypdf import PdfReader
from weasyprint import CSS, HTML

from bookfactory import add_author, add_front_matter, make_asset, make_book, make_user, png_bytes
from layout import pdf_css
from models import db
from render import MediaFetcher, assemble_html, clear_cache, first_pages, get_layout

NO_HYPHEN = {'hyphenate': False}
LOOPBACK_URL = 'http://' + '.'.join(['127', '0', '0', '1']) + '/x.png'


def pdf_texts(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() or '' for page in reader.pages]


def lines(text):
    return [line.strip() for line in text.split('\n') if line.strip()]


def physical_page_of(texts, token):
    """First physical page (1-based) whose extracted text contains `token`."""
    for number, text in enumerate(texts, start=1):
        if token in text:
            return number
    raise AssertionError(f'{token} not found in the PDF')


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def rich_book(app):
    user = make_user()
    book, tokens = make_book(
        user, chapters=4, paragraphs=10, settings=NO_HYPHEN,
        terms=[('Quokka', 'A small marsupial'), ('fox', 'A clever animal')],
        inject={(1, 2): 'Quokka', (2, 5): 'Quokka', (4, 9): 'quokkas'})
    add_front_matter(book)
    add_author(book)
    return book, tokens


def test_page_numbers_agree_with_the_real_pdf(rich_book):
    """Every block's computed page equals the page its text really lands on in the PDF."""
    book, tokens = rich_book
    result = get_layout(book)
    texts = pdf_texts(result.pdf)
    assert len(texts) == result.physical_pages
    for block_id, token in tokens.items():
        real_physical = physical_page_of(texts, token)
        assert result.pages[f'b{block_id}'] + result.body_start - 1 == real_physical, token


def test_printed_footers_match_the_computed_numbers(rich_book):
    book, _ = rich_book
    result = get_layout(book)
    texts = pdf_texts(result.pdf)
    last_body = max(result.pages.values())
    for printed in range(1, last_body + 1):
        physical = printed + result.body_start - 1
        assert lines(texts[physical - 1])[-1] == str(printed), f'page {printed}'
    # first chapter is page 1; the contents page is numbered in roman numerals
    assert result.pages[result.doc.body_start_anchor] == 1
    contents = next(t for t in texts if t.lstrip().startswith('Contents'))
    assert lines(contents)[-1] == 'i'


def test_front_matter_is_not_counted_and_covers_are_included(rich_book):
    book, _ = rich_book
    result = get_layout(book)
    texts = pdf_texts(result.pdf)
    # front cover, title page, dedication, quote, contents precede page 1
    assert result.body_start == 6
    assert 'For my family' in texts[2] and 'softer than water' in texts[3]
    assert 'Tao Teh Ching #78' in texts[3]
    assert 'Contents' in texts[4]


def test_contents_lists_chapters_with_their_real_numbers(rich_book):
    book, _ = rich_book
    result = get_layout(book)
    contents = next(t for t in pdf_texts(result.pdf) if t.lstrip().startswith('Contents'))
    entries = lines(contents)
    for chapter in result.doc.chapters:
        number = result.pages[chapter['anchor']]
        assert f'{chapter["title"]} {number}' in entries
    for anchor, title in (('sec-glossary', 'Glossary'), ('sec-index', 'Index'), ('sec-about', 'About the Author')):
        assert f'{title} {result.pages[anchor]}' in entries


def test_index_and_glossary_pages_are_the_pages_the_term_really_appears_on(rich_book):
    book, tokens = rich_book
    result = get_layout(book)
    texts = pdf_texts(result.pdf)
    by_position = {(c.sort_order, b.sort_order): b.block_id for c in book.chapters for b in c.blocks}
    expected = sorted({physical_page_of(texts, tokens[by_position[key]]) - result.body_start + 1
                       for key in ((1, 2), (2, 5), (4, 9))})
    quokka = next(t for t in book.terms if t.term == 'Quokka')
    occurrences = result.doc.annotator.occurrences[quokka.term_id]
    assert len(occurrences) == 3                             # includes the plural "quokkas"
    assert sorted({result.pages[o] for o in occurrences}) == expected

    index_page = next(t for t in texts if t.lstrip().startswith('Index'))
    entry = next(line for line in lines(index_page) if line.startswith('Quokka'))
    assert entry == 'Quokka, ' + ', '.join(str(p) for p in expected)
    glossary = next(t for t in texts if t.lstrip().startswith('Glossary'))
    assert 'A small marsupial' in glossary
    label = 'Pages ' if len(expected) > 1 else 'Page '
    assert label + ', '.join(str(p) for p in expected) in glossary


def test_layout_reaches_a_fixed_point(rich_book):
    """Re-rendering with the final numbers yields exactly the same numbers (nothing shifts)."""
    book, _ = rich_book
    result = get_layout(book)
    assert result.passes <= 3
    fetcher = MediaFetcher(book.user_id, current_app.config['UPLOAD_DIR'])
    html = assemble_html(result.doc, result.pages, result.toc_pages)
    again = HTML(string=html, base_url='ibs://book/', url_fetcher=fetcher).render(
        stylesheets=[CSS(string=pdf_css(result.doc.settings, book.title), url_fetcher=fetcher)])
    first = first_pages(again)
    start = first[result.doc.body_start_anchor]
    assert {a: n - start + 1 for a, n in first.items() if n >= start} == result.pages


def test_two_columns_and_other_trim_sizes_still_paginate_correctly(app):
    user = make_user()
    book, tokens = make_book(user, chapters=3, paragraphs=10, terms=[('fox', 'An animal')],
                             settings={'hyphenate': False, 'columns': 2, 'trim': 'a5', 'font_size': 10.0,
                                       'page_numbers': 'center'})
    result = get_layout(book)
    texts = pdf_texts(result.pdf)
    for block_id, token in tokens.items():
        assert result.pages[f'b{block_id}'] + result.body_start - 1 == physical_page_of(texts, token)
    # A5 page size (148 x 210 mm)
    box = PdfReader(io.BytesIO(result.pdf)).pages[0].mediabox
    assert round(float(box.width) / 72 * 25.4) == 148 and round(float(box.height) / 72 * 25.4) == 210


def test_more_pages_with_a_bigger_font(app):
    user = make_user()
    small, _ = make_book(user, title='S', chapters=2, paragraphs=10, settings={'font_size': 9.0})
    big, _ = make_book(user, title='B', chapters=2, paragraphs=10, settings={'font_size': 15.0})
    assert get_layout(big).physical_pages > get_layout(small).physical_pages


def test_options_can_remove_covers_title_and_contents(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=4,
                        settings={'include_covers': False, 'include_title_page': False,
                                  'include_contents': False})
    result = get_layout(book)
    assert result.body_start == 1
    assert 'Chapter 1' in pdf_texts(result.pdf)[0]


def test_book_without_chapters_still_renders(app):
    user = make_user()
    book, _ = make_book(user, chapters=0, terms=[('x', 'y')])
    add_author(book)
    result = get_layout(book)
    assert result.pdf.startswith(b'%PDF') and result.doc.body_start_anchor is None


def test_layout_is_cached_until_the_book_changes(app):
    from datetime import datetime, timedelta
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2)
    first = get_layout(book)
    assert get_layout(book) is first
    book.modified_at = datetime.utcnow() + timedelta(seconds=5)
    assert get_layout(book) is not first


def test_author_photo_is_embedded(app):
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2)
    add_author(book, photo=make_asset(app, user))
    result = get_layout(book)
    last_page = PdfReader(io.BytesIO(result.pdf)).pages[-1]
    assert len(last_page.images) == 1


def test_media_fetcher_only_serves_the_owners_media(app):
    owner, other = make_user('owner'), make_user('other')
    asset = make_asset(app, owner, 'mine.png')
    theirs = make_asset(app, other, 'theirs.png')
    fetcher = MediaFetcher(owner.user_id, app.config['UPLOAD_DIR'])
    response = fetcher.fetch(f'ibs-media://{asset.asset_id}')
    assert response.headers['Content-Type'] == 'image/png'
    assert response.read() == png_bytes()
    for url in (f'ibs-media://{theirs.asset_id}', 'ibs-media://999999', 'ibs-media://abc',
                'http://example.com/x.png', LOOPBACK_URL, 'file:///etc/passwd', 'ftp://x/y',
                '/etc/passwd', 'data:text/plain,hi'):
        with pytest.raises(ValueError):
            fetcher.fetch(url)


def test_media_fetcher_refuses_paths_that_escape_the_upload_folder(app):
    owner = make_user('owner')
    asset = make_asset(app, owner, 'ok.png')
    asset.file_path = '../../../../etc/hostname'
    db.session.flush()
    with pytest.raises(ValueError):
        MediaFetcher(owner.user_id, app.config['UPLOAD_DIR']).fetch(f'ibs-media://{asset.asset_id}')
