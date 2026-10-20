"""Editable Contents (Part A) and the version/date stamp (Part E)."""
import io
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

import pytest
from pypdf import PdfReader

from bookdoc import BookDoc
from bookfactory import add_author, make_book, make_user
from conftest import create_book, get_book
from epub import build_epub
from layout import get_settings
from models import Book, BookTocEntry, Chapter, ContentBlock, db
from render import clear_cache, get_layout
from toc import TocLine, nested_ol, stamp_text

XHTML = '{http://www.w3.org/1999/xhtml}'
NO_HYPHEN = {'hyphenate': False}
WHEN = datetime(2026, 10, 20, 9, 30)


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def add_heading(chapter, text, level=1, order=50):
    block = ContentBlock(block_type='heading', content_text=text, content_data={'level': level}, sort_order=order)
    chapter.blocks.append(block)
    db.session.flush()
    return block


def customize_book(book, *specs):
    """Give `book` an edited Contents made of the given BookTocEntry keyword dicts, in order."""
    for position, spec in enumerate(specs, start=1):
        book.toc_entries.append(BookTocEntry(sort_order=position, visible=spec.pop('visible', True),
                                             level=spec.pop('level', 0), **spec))
    db.session.flush()


def contents_page_text(result):
    reader = PdfReader(io.BytesIO(result.pdf))
    for page in reader.pages:
        text = page.extract_text() or ''
        if 'Generated' in text and 'Contents' in text:
            return text
    raise AssertionError('no Contents page with a stamp found')


# ---- the stamp ---------------------------------------------------------------------------------

def test_stamp_text_format():
    assert stamp_text('0.3', WHEN) == 'Version 0.3 \u00b7 Generated October 20, 2026'
    assert stamp_text('', datetime(2027, 1, 5)) == 'Version 0.1 \u00b7 Generated January 5, 2027'


def test_stamp_is_small_text_under_the_contents_in_every_format(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=3, settings=NO_HYPHEN)
    book.version = '2.4'
    result = get_layout(book)
    expected = f'Version 2.4 \u00b7 Generated {result.doc.generated_at:%B} {result.doc.generated_at.day}, ' \
               f'{result.doc.generated_at.year}'
    assert expected in contents_page_text(result)
    data = build_epub(book, result)
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert expected in archive.read('OEBPS/text/contents.xhtml').decode()
    assert expected in archive.read('OEBPS/nav.xhtml').decode()


def test_stamp_does_not_change_the_page_numbers(app):
    """The stamp is the same length in every layout pass, so Contents and body pages stay settled."""
    user = make_user()
    book, _ = make_book(user, chapters=3, paragraphs=6, settings=NO_HYPHEN)
    result = get_layout(book)
    assert result.passes <= 3
    for chapter in book.chapters:
        assert result.toc_pages[f'ch-{chapter.chapter_id}'] == result.pages[f'ch-{chapter.chapter_id}']


# ---- automatic and custom lines ----------------------------------------------------------------

def test_automatic_contents_is_one_line_per_chapter_plus_back_matter(app):
    user = make_user()
    book, _ = make_book(user, chapters=3, paragraphs=2, terms=[('fox', 'An animal')])
    add_author(book)
    doc = BookDoc(book, get_settings(book), generated_at=WHEN)
    assert not doc.has_custom_toc
    assert [(l.title, l.level, l.kind) for l in doc.toc_lines()] == [
        ('Chapter 1', 0, 'chapter'), ('Chapter 2', 0, 'chapter'), ('Chapter 3', 0, 'chapter'),
        ('Glossary', 0, 'section'), ('Index', 0, 'section'), ('About the Author', 0, 'section')]
    assert doc.stamp() == 'Version 0.1 \u00b7 Generated October 20, 2026'


def test_custom_lines_follow_labels_levels_order_visibility_and_parts(app):
    user = make_user()
    book, _ = make_book(user, chapters=3, paragraphs=2)
    add_author(book)
    c1, c2, c3 = book.chapters
    heading = add_heading(c1, 'Origins')
    customize_book(
        book,
        {'kind': 'part', 'label': 'Part One'},
        {'kind': 'chapter', 'chapter': c1, 'label': 'The Beginning'},
        {'kind': 'heading', 'block': heading, 'level': 1},
        {'kind': 'chapter', 'chapter': c2, 'visible': False},
        {'kind': 'part', 'label': 'Part Two'},
        {'kind': 'chapter', 'chapter': c3, 'level': 2},
        {'kind': 'section', 'section_key': 'glossary'},          # the book has no glossary: skipped
        {'kind': 'section', 'section_key': 'about'})
    doc = BookDoc(book, get_settings(book), generated_at=WHEN)
    assert doc.has_custom_toc
    assert [(l.title, l.level, l.kind, l.anchor) for l in doc.toc_lines()] == [
        ('Part One', 0, 'part', None),
        ('The Beginning', 0, 'chapter', f'ch-{c1.chapter_id}'),
        ('Origins', 1, 'heading', f'b{heading.block_id}'),
        ('Part Two', 0, 'part', None),
        ('Chapter 3', 2, 'chapter', f'ch-{c3.chapter_id}'),
        ('About the Author', 0, 'section', 'sec-about')]
    assert [a for a, _ in doc.toc_entries()] == [f'ch-{c1.chapter_id}', f'b{heading.block_id}',
                                                 f'ch-{c3.chapter_id}', 'sec-about']


def test_entry_for_a_removed_target_is_skipped(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=1)
    c1, c2 = book.chapters
    customize_book(book, {'kind': 'chapter', 'chapter': c1}, {'kind': 'chapter', 'chapter': c2})
    book.toc_entries[1].chapter = None; book.toc_entries[1].chapter_id = 999999    # dangling
    doc = BookDoc(book, get_settings(book), generated_at=WHEN)
    assert [l.title for l in doc.toc_lines()] == ['Chapter 1']


def test_nested_navigation_groups_lines_under_parts_and_parents():
    lines = [TocLine(None, 'Part One', 0, 'part'), TocLine('a', 'A', 0, 'chapter'), TocLine('a1', 'A one', 1, 'heading'),
             TocLine('a11', 'A one one', 2, 'heading'), TocLine('b', 'B', 0, 'chapter'),
             TocLine(None, 'Empty part', 0, 'part'),
             TocLine(None, 'Part Two', 0, 'part'), TocLine('c', 'C', 0, 'chapter'), TocLine('gone', 'Gone', 0, 'chapter')]
    html = nested_ol(lines, lambda anchor: None if anchor == 'gone' else f'x.xhtml#{anchor}')
    root = ET.fromstring(f'<root xmlns="{XHTML[1:-1]}">{html}</root>'.replace('<root', '<root', 1))
    top = root.find(f'{XHTML}ol')
    items = top.findall(f'{XHTML}li')
    assert [i.find(f'{XHTML}span').text for i in items] == ['Part One', 'Part Two']      # empty part dropped
    first_children = items[0].find(f'{XHTML}ol').findall(f'{XHTML}li')
    assert [li.find(f'{XHTML}a').text for li in first_children] == ['A', 'B']
    nested = first_children[0].find(f'{XHTML}ol').findall(f'{XHTML}li')
    assert nested[0].find(f'{XHTML}a').text == 'A one'
    assert nested[0].find(f'{XHTML}ol').find(f'{XHTML}li').find(f'{XHTML}a').text == 'A one one'
    assert 'Gone' not in html and nested_ol([TocLine(None, 'Lonely', 0, 'part')], lambda a: a) == ''


# ---- rendered: PDF and EPUB --------------------------------------------------------------------

@pytest.fixture()
def custom_book(app):
    user = make_user()
    book, _ = make_book(user, chapters=3, paragraphs=6, settings=NO_HYPHEN)
    add_author(book)
    c1, c2, c3 = book.chapters
    heading = add_heading(c2, 'Origins', order=3)
    customize_book(
        book,
        {'kind': 'part', 'label': 'Part One'},
        {'kind': 'chapter', 'chapter': c1, 'label': 'The Beginning'},
        {'kind': 'chapter', 'chapter': c2, 'visible': False},
        {'kind': 'heading', 'block': heading, 'level': 1},
        {'kind': 'part', 'label': 'Part Two'},
        {'kind': 'chapter', 'chapter': c3},
        {'kind': 'section', 'section_key': 'about'})
    return book, heading


def test_pdf_contents_shows_edits_and_real_page_numbers(custom_book):
    book, heading = custom_book
    result = get_layout(book)
    text = contents_page_text(result)
    assert 'Part One' in text and 'Part Two' in text and 'The Beginning' in text and 'Origins' in text
    assert 'Chapter 2' not in text                         # hidden line
    anchor = f'b{heading.block_id}'
    assert result.toc_pages[anchor] == result.pages[anchor]
    assert re.search(rf'Origins\s*{result.toc_pages[anchor]}\b', text)
    # a part divider carries no page number and no link target
    assert re.search(r'Part One\s*\n', text) or text.rstrip().find('Part One') >= 0
    assert not re.search(r'Part (One|Two)\s*\d', text)


def test_epub_navigation_nests_parts_and_headings_and_omits_hidden_lines(custom_book):
    book, heading = custom_book
    data = build_epub(book, get_layout(book))
    nav = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read('OEBPS/nav.xhtml'))
    toc = next(n for n in nav.iter(f'{XHTML}nav') if n.get('{http://www.idpf.org/2007/ops}type') == 'toc')
    spans = [s.text for s in toc.iter(f'{XHTML}span')]
    assert spans == ['Part One', 'Part Two']
    anchors = {a.text: a.get('href') for a in toc.iter(f'{XHTML}a')}
    assert set(anchors) == {'The Beginning', 'Origins', 'Chapter 3', 'About the Author'}
    assert anchors['Origins'].endswith(f'#b{heading.block_id}')
    assert 'chapter-002.xhtml' in anchors['Origins']       # the heading lives in the (hidden) chapter 2 file
    first_part = toc.find(f'{XHTML}ol').findall(f'{XHTML}li')[0]
    assert [a.text for a in first_part.iter(f'{XHTML}a')] == ['The Beginning', 'Origins']


@pytest.mark.skipif(shutil.which('java') is None, reason='EPUBCheck needs Java')
def test_epubcheck_accepts_a_customized_contents(custom_book, tmp_path):
    from epubcheck import EpubCheck
    book, _ = custom_book
    path = tmp_path / 'custom.epub'
    path.write_bytes(build_epub(book, get_layout(book)))
    result = EpubCheck(str(path))
    problems = [m for m in result.messages if m.level in ('ERROR', 'WARNING', 'FATAL')]
    assert not problems, '\n'.join(f'{m.level} {m.id} {m.location}: {m.message}' for m in problems)


def test_book_without_custom_rows_renders_exactly_as_the_automatic_contents(app):
    user = make_user()
    book, _ = make_book(user, chapters=3, paragraphs=4, settings=NO_HYPHEN)
    auto = get_layout(book)
    titles = [line.title for line in auto.doc.toc_lines()]
    assert titles == ['Chapter 1', 'Chapter 2', 'Chapter 3']
    for chapter in book.chapters:
        assert f'ch-{chapter.chapter_id}' in auto.toc_pages


def test_contents_switched_off_leaves_no_contents_page_or_stamp(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=2,
                        settings={'include_contents': False, 'include_covers': False, 'include_title_page': False})
    result = get_layout(book)
    texts = [(p.extract_text() or '') for p in PdfReader(io.BytesIO(result.pdf)).pages]
    assert not any('Generated' in t for t in texts)
    assert 'contents.xhtml' not in ' '.join(zipfile.ZipFile(io.BytesIO(build_epub(book, result))).namelist())


# ---- the editor (routes) -----------------------------------------------------------------------

def build_with_routes(client, chapters=('One', 'Two', 'Three'), headings=True):
    book_id = create_book(client)
    for title in chapters:
        client.post(f'/books/{book_id}/chapters/new', data={'title': title})
    book = get_book(book_id)
    if headings:
        for chapter in book.chapters:
            resp = client.post(f'/chapters/{chapter.chapter_id}/blocks/new',
                               data={'block_type': 'heading', 'content_text': f'{chapter.title} heading', 'heading_level': '1'})
            assert resp.status_code == 200
            client.post(f'/chapters/{chapter.chapter_id}/blocks/new',
                        data={'block_type': 'heading', 'content_text': f'{chapter.title} small', 'heading_level': '3'})
    return book_id


def rows(book_id):
    return [(e.kind, e.label, e.level, e.visible, e.sort_order) for e in get_book(book_id).toc_entries]


def test_editor_page_shows_automatic_list_and_customize_button(alice):
    book_id = build_with_routes(alice, headings=False)
    page = alice.get(f'/books/{book_id}/contents')
    assert page.status_code == 200 and b'Automatic Contents' in page.data and b'Customize contents' in page.data
    assert b'Version 0.1' in page.data                       # the stamp is described on the page


def test_customize_copies_the_automatic_list(alice):
    book_id = build_with_routes(alice, headings=False)
    resp = alice.post(f'/books/{book_id}/contents/customize', data={}, follow_redirects=True)
    assert b'Your Contents' in resp.data
    assert [(k, s) for k, _, _, _, s in rows(book_id)] == [('chapter', 1), ('chapter', 2), ('chapter', 3)]
    again = alice.post(f'/books/{book_id}/contents/customize', data={}, follow_redirects=True)
    assert b'already customized' in again.data and len(rows(book_id)) == 3


def test_customize_with_headings_lists_large_and_medium_only(alice):
    book_id = build_with_routes(alice)
    alice.post(f'/books/{book_id}/contents/customize', data={'with_headings': '1'})
    kinds = [(k, l) for k, _, l, _, _ in rows(book_id)]
    assert kinds == [('chapter', 0), ('heading', 1)] * 3          # the small (level 3) headings are not listed
    labels = [e.block.content_text for e in get_book(book_id).toc_entries if e.kind == 'heading']
    assert labels == ['One heading', 'Two heading', 'Three heading']


def test_rename_hide_show_indent_outdent_and_limits(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    first = get_book(book_id).toc_entries[0].entry_id

    def act(**form):
        return alice.post(f'/contents/{first}/update', data=form)

    assert act(action='save', label='  The first one  ').status_code == 302
    assert rows(book_id)[0][1] == 'The first one'
    act(action='save', label='')                                            # blank label = use the chapter title
    assert rows(book_id)[0][1] is None
    act(action='hide'); assert rows(book_id)[0][3] is False
    act(action='show'); assert rows(book_id)[0][3] is True
    for _ in range(5):
        act(action='indent')
    assert rows(book_id)[0][2] == 2                                          # never deeper than level 2
    for _ in range(5):
        act(action='outdent')
    assert rows(book_id)[0][2] == 0
    assert act(action='nonsense').status_code == 400
    too_long = act(action='save', label='x' * 301)
    assert too_long.status_code == 302 and rows(book_id)[0][1] is None       # rejected, unchanged


def test_move_up_and_down_keep_a_clean_order(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    ids = [e.entry_id for e in get_book(book_id).toc_entries]
    alice.post(f'/contents/{ids[2]}/update', data={'action': 'up'})
    alice.post(f'/contents/{ids[0]}/update', data={'action': 'up'})          # already first: no change
    alice.post(f'/contents/{ids[2]}/update', data={'action': 'down'})        # already last after the move? it moved up
    order = [e.entry_id for e in get_book(book_id).toc_entries]
    assert sorted(order) == sorted(ids) and [e.sort_order for e in get_book(book_id).toc_entries] == [1, 2, 3]
    assert order == [ids[0], ids[1], ids[2]]                                 # up then down returns to the start


def test_delete_an_entry_renumbers_and_the_chapter_is_listed_as_missing(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    second = get_book(book_id).toc_entries[1]
    alice.post(f'/contents/{second.entry_id}/update', data={'action': 'delete'})
    assert [s for *_, s in rows(book_id)] == [1, 2]
    page = alice.get(f'/books/{book_id}/contents')
    assert b'1 chapter not in this Contents' in page.data and b'Add missing chapters' in page.data


def test_add_part_divider_before_an_entry_and_validation(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    third = get_book(book_id).toc_entries[2]
    alice.post(f'/books/{book_id}/contents/add-part', data={'label': 'Part Two', 'before': third.entry_id})
    assert [(k, l) for k, l, *_ in rows(book_id)] == [('chapter', None), ('chapter', None), ('part', 'Part Two'),
                                                       ('chapter', None)]
    alice.post(f'/books/{book_id}/contents/add-part', data={'label': 'End part'})
    assert rows(book_id)[-1][:2] == ('part', 'End part')
    blank = alice.post(f'/books/{book_id}/contents/add-part', data={'label': '  '}, follow_redirects=True)
    assert b'Enter the text of the part divider' in blank.data and len(rows(book_id)) == 5
    assert alice.post(f'/books/{book_id}/contents/add-part',
                      data={'label': 'x', 'before': 999999}).status_code == 404


def test_add_headings_go_after_their_chapter_and_foreign_blocks_are_ignored(alice, bob):
    book_id = build_with_routes(alice)
    other_id = build_with_routes(bob, chapters=('Bob',))
    alice.post(f'/books/{book_id}/contents/customize', data={})
    book = get_book(book_id)
    heading = next(b for c in book.chapters for b in c.blocks if b.content_text == 'Two heading')
    foreign = next(b for c in get_book(other_id).chapters for b in c.blocks if b.block_type == 'heading')
    alice.post(f'/books/{book_id}/contents/add-headings', data={'block_ids': [heading.block_id, foreign.block_id]})
    entries = get_book(book_id).toc_entries
    kinds = [(e.kind, e.chapter.title if e.kind == 'chapter' else None) for e in entries]
    assert kinds == [('chapter', 'One'), ('chapter', 'Two'), ('heading', None), ('chapter', 'Three')]
    assert entries[2].block_id == heading.block_id and len(entries) == 4      # the foreign block was not added
    none = alice.post(f'/books/{book_id}/contents/add-headings', data={'block_ids': []}, follow_redirects=True)
    assert b'Choose at least one heading' in none.data


def test_add_missing_chapters_goes_after_the_chapter_before_it(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'Four'})
    page = alice.get(f'/books/{book_id}/contents')
    assert b'1 chapter not in this Contents' in page.data
    alice.post(f'/books/{book_id}/contents/add-missing', data={})
    titles = [e.chapter.title for e in get_book(book_id).toc_entries]
    assert titles == ['One', 'Two', 'Three', 'Four']
    again = alice.post(f'/books/{book_id}/contents/add-missing', data={}, follow_redirects=True)
    assert b'Every chapter is already listed' in again.data


def test_add_section_once_and_reject_unknown(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    alice.post(f'/books/{book_id}/contents/add-section', data={'section_key': 'index'})
    alice.post(f'/books/{book_id}/contents/add-section', data={'section_key': 'index'})
    assert [e.section_key for e in get_book(book_id).toc_entries if e.kind == 'section'] == ['index']
    assert alice.post(f'/books/{book_id}/contents/add-section', data={'section_key': 'zzz'}).status_code == 400


def test_reset_returns_to_the_automatic_contents(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    assert rows(book_id)
    alice.post(f'/books/{book_id}/contents/reset', data={})
    assert rows(book_id) == []
    assert not BookDoc(get_book(book_id), get_settings(get_book(book_id))).has_custom_toc


def test_every_edit_refreshes_the_book_edit_time(alice):
    book_id = build_with_routes(alice, headings=False)
    before = get_book(book_id).modified_at
    alice.post(f'/books/{book_id}/contents/customize', data={})
    assert get_book(book_id).modified_at > before


# ---- ownership, read-only, cascades, copying ----------------------------------------------------

def test_other_users_get_404_everywhere(alice, bob):
    book_id = build_with_routes(alice, headings=True)
    alice.post(f'/books/{book_id}/contents/customize', data={'with_headings': '1'})
    entry_id = get_book(book_id).toc_entries[0].entry_id
    assert bob.get(f'/books/{book_id}/contents').status_code == 404
    for path, data in [(f'/books/{book_id}/contents/customize', {}), (f'/books/{book_id}/contents/reset', {}),
                       (f'/books/{book_id}/contents/add-part', {'label': 'x'}),
                       (f'/books/{book_id}/contents/add-headings', {'block_ids': [1]}),
                       (f'/books/{book_id}/contents/add-missing', {}),
                       (f'/books/{book_id}/contents/add-section', {'section_key': 'index'}),
                       (f'/contents/{entry_id}/update', {'action': 'delete'})]:
        assert bob.post(path, data=data).status_code == 404, path
    assert len(rows(book_id)) == 6


def test_anonymous_users_are_sent_to_login(client):
    assert client.get('/books/1/contents').status_code == 302
    assert client.post('/contents/1/update', data={'action': 'hide'}).status_code == 302


def test_completed_book_contents_is_read_only(alice):
    book_id = build_with_routes(alice, headings=False)
    alice.post(f'/books/{book_id}/contents/customize', data={})
    alice.post(f'/books/{book_id}/complete')
    entry_id = get_book(book_id).toc_entries[0].entry_id
    assert alice.get(f'/books/{book_id}/contents').status_code == 200          # reading is allowed
    for path, data in [(f'/books/{book_id}/contents/reset', {}), (f'/books/{book_id}/contents/add-part', {'label': 'x'}),
                       (f'/books/{book_id}/contents/add-missing', {}),
                       (f'/contents/{entry_id}/update', {'action': 'delete'})]:
        resp = alice.post(path, data=data)
        assert resp.status_code == 302 and '/contents' not in resp.headers['Location'], path
    assert len(rows(book_id)) == 3


def test_deleting_a_chapter_or_heading_removes_its_contents_lines(alice):
    book_id = build_with_routes(alice)
    alice.post(f'/books/{book_id}/contents/customize', data={'with_headings': '1'})
    book = get_book(book_id)
    chapter = book.chapters[0]
    heading = book.chapters[1].blocks[0]
    alice.post(f'/blocks/{heading.block_id}/delete')
    remaining = get_book(book_id).toc_entries
    assert len(remaining) == 5 and all(e.block_id != heading.block_id for e in remaining)
    alice.post(f'/chapters/{chapter.chapter_id}/delete')
    remaining = get_book(book_id).toc_entries
    assert len(remaining) == 3                                        # chapter one and its heading are gone
    assert all(e.chapter_id != chapter.chapter_id for e in remaining)
    assert BookTocEntry.query.filter(BookTocEntry.book_id == book_id).count() == 3


def test_deleting_a_book_removes_its_contents_rows(alice):
    book_id = build_with_routes(alice)
    alice.post(f'/books/{book_id}/contents/customize', data={'with_headings': '1'})
    assert BookTocEntry.query.count() > 0
    alice.post(f'/books/{book_id}/delete')
    assert BookTocEntry.query.count() == 0


def test_editable_copy_keeps_the_contents_pointing_at_its_own_chapters(alice):
    book_id = build_with_routes(alice)
    alice.post(f'/books/{book_id}/contents/customize', data={'with_headings': '1'})
    first = get_book(book_id).toc_entries[0]
    alice.post(f'/contents/{first.entry_id}/update', data={'action': 'save', 'label': 'Renamed'})
    alice.post(f'/books/{book_id}/contents/add-part', data={'label': 'Part Z'})
    resp = alice.post(f'/books/{book_id}/copy')
    copy_id = int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])
    original, copy = get_book(book_id), get_book(copy_id)
    assert len(copy.toc_entries) == len(original.toc_entries) == 7
    own_chapters = {c.chapter_id for c in copy.chapters}
    own_blocks = {b.block_id for c in copy.chapters for b in c.blocks}
    for entry in copy.toc_entries:
        if entry.kind == 'chapter':
            assert entry.chapter_id in own_chapters
        if entry.kind == 'heading':
            assert entry.block_id in own_blocks
    assert [(e.kind, e.label, e.level) for e in copy.toc_entries] == \
           [(e.kind, e.label, e.level) for e in original.toc_entries]
    assert {e.chapter_id for e in original.toc_entries if e.chapter_id}.isdisjoint(own_chapters)
    doc = BookDoc(copy, get_settings(copy), generated_at=WHEN)
    assert doc.toc_lines()[0].title == 'Renamed' and any(l.kind == 'part' for l in doc.toc_lines())
