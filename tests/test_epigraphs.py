"""Chapter epigraphs (Part C)."""
import io
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pytest
from pypdf import PdfReader

from bookdoc import BookDoc
from bookfactory import make_book, make_user
from conftest import create_book, get_book
from epub import build_epub
from layout import DEFAULTS, epub_css, get_settings, pdf_css
from models import db
from render import clear_cache, get_layout

NO_HYPHEN = {'hyphenate': False}
QUOTE = 'Nothing in the world\nis softer than water.'


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def chapter_with_epigraph(alice, text=QUOTE, source='Tao Teh Ching #78'):
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter_id = get_book(book_id).chapters[0].chapter_id
    if text is not None:
        alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': text, 'epigraph_source': source})
    return book_id, chapter_id


def epigraph_of(chapter_id):
    chapter = db.session.get(__import__('models').Chapter, chapter_id)
    return chapter.epigraph_text, chapter.epigraph_source


# ---- the form ---------------------------------------------------------------------------------

def test_set_change_and_remove_an_epigraph(alice):
    book_id, chapter_id = chapter_with_epigraph(alice)
    assert epigraph_of(chapter_id) == (QUOTE, 'Tao Teh Ching #78')
    alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'A new thought', 'epigraph_source': ''})
    assert epigraph_of(chapter_id) == ('A new thought', None)                  # a blank source is stored as none
    removed = alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': '  \n ', 'epigraph_source': 'Orphan'},
                         follow_redirects=True)
    assert epigraph_of(chapter_id) == (None, None) and b'Epigraph removed' in removed.data   # a source alone means nothing


def test_the_text_is_trimmed_and_line_breaks_are_kept(alice):
    _, chapter_id = chapter_with_epigraph(alice, text='\r\nLine one\r\nLine two\r\n\r\n', source='  Someone  ')
    assert epigraph_of(chapter_id) == ('Line one\nLine two', 'Someone')


def test_limits_are_enforced_and_nothing_is_saved(alice):
    _, chapter_id = chapter_with_epigraph(alice)
    long_text = alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'x' * 2001}, follow_redirects=True)
    assert b'limited to 2000 characters' in long_text.data
    long_source = alice.post(f'/chapters/{chapter_id}/epigraph',
                             data={'epigraph_text': 'ok', 'epigraph_source': 'y' * 301}, follow_redirects=True)
    assert b'limited to 300 characters' in long_source.data
    assert epigraph_of(chapter_id) == (QUOTE, 'Tao Teh Ching #78')              # unchanged
    alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'x' * 2000})
    assert len(epigraph_of(chapter_id)[0]) == 2000                            # exactly at the limit is fine


def test_the_chapter_page_shows_the_form_filled_in(alice):
    _, chapter_id = chapter_with_epigraph(alice)
    page = alice.get(f'/chapters/{chapter_id}').data.decode()
    assert 'name="epigraph_text"' in page and 'softer than water.' in page and 'Tao Teh Ching #78' in page


def test_editing_an_epigraph_refreshes_the_book_edit_time(alice):
    book_id, chapter_id = chapter_with_epigraph(alice, text=None)
    before = get_book(book_id).modified_at
    alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'Hello'})
    assert get_book(book_id).modified_at > before


def test_other_users_and_visitors_cannot_touch_an_epigraph(alice, bob, client):
    book_id, chapter_id = chapter_with_epigraph(alice)
    assert bob.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'hijack'}).status_code == 404
    assert client.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'hijack'}).status_code == 302
    assert epigraph_of(chapter_id) == (QUOTE, 'Tao Teh Ching #78')


def test_a_completed_book_keeps_its_epigraph_read_only(alice):
    book_id, chapter_id = chapter_with_epigraph(alice)
    alice.post(f'/books/{book_id}/complete')
    resp = alice.post(f'/chapters/{chapter_id}/epigraph', data={'epigraph_text': 'changed'})
    assert resp.status_code == 302 and '/chapters/' not in resp.headers['Location']
    assert epigraph_of(chapter_id) == (QUOTE, 'Tao Teh Ching #78')
    page = alice.get(f'/chapters/{chapter_id}').data.decode()
    assert 'softer than water' in page and 'name="epigraph_text"' not in page     # shown, but no form


def test_the_book_preview_shows_epigraphs(alice):
    book_id, _ = chapter_with_epigraph(alice)
    page = alice.get(f'/books/{book_id}/preview').data.decode()
    assert 'epigraph-preview' in page and 'softer than water.' in page and 'Tao Teh Ching #78' in page


def test_an_editable_copy_keeps_the_epigraphs(alice):
    book_id, _ = chapter_with_epigraph(alice)
    resp = alice.post(f'/books/{book_id}/copy')
    copy_id = int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])
    chapter = get_book(copy_id).chapters[0]
    assert (chapter.epigraph_text, chapter.epigraph_source) == (QUOTE, 'Tao Teh Ching #78')


# ---- rendering --------------------------------------------------------------------------------

@pytest.fixture()
def epigraph_book(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=3, settings=NO_HYPHEN,
                        terms=[('Quokka', 'A small marsupial')])
    book.chapters[0].epigraph_text = 'The Quokka is\nsmiling & <b>happy</b>.<script>steal()</script>'
    book.chapters[0].epigraph_source = 'An <i>old</i> friend'
    db.session.flush()
    return book


def test_the_epigraph_sits_between_the_title_and_the_text_in_the_chapter_settings_style(epigraph_book):
    doc = BookDoc(epigraph_book, get_settings(epigraph_book))
    first, second = doc.chapters
    assert re.search(r'</h1><blockquote class="epigraph ep-right ep-small ep-italic" epub:type="epigraph">'
                     r'<div class="epigraph-text">.*?</div><p class="epigraph-source">\u2014 .*?</p></blockquote>'
                     r'<div class="chapter-body">', first['html'], re.S)
    assert 'epigraph' not in second['html']                                   # chapters without one are unchanged


def test_text_is_escaped_and_the_authors_line_breaks_are_kept(epigraph_book):
    html = BookDoc(epigraph_book, get_settings(epigraph_book)).chapters[0]['html']
    assert '<br' in html.split('epigraph-text')[1].split('</div>')[0]          # the line break survives
    assert '&lt;i&gt;old&lt;/i&gt;' in html                                    # the source is plain text
    quote = html.split('</h1>')[1].split('chapter-body')[0]
    assert '<script' not in html                                               # scripts in the quote are stripped
    assert '<b>happy</b>' in quote                                             # plain bold/italic formatting is allowed
    assert 'An &lt;i&gt;old&lt;/i&gt; friend' in html


def test_quoted_words_never_become_glossary_links_or_index_entries(epigraph_book):
    doc = BookDoc(epigraph_book, get_settings(epigraph_book))
    epigraph = doc.chapters[0]['html'].split('<div class="chapter-body">')[0]
    assert 'Quokka' in epigraph and '<a ' not in epigraph and 'class="occ"' not in epigraph and 'class="gl"' not in epigraph
    assert not doc.annotator.occurrences                                       # the filler text never mentions it
    assert not doc.has_index()                                                 # so the Index does not list it


def test_the_title_is_unharmed_even_when_it_contains_a_glossary_term(app):
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=1, settings=NO_HYPHEN, terms=[('Quokka', 'A small marsupial')])
    book.chapters[0].title = 'The Quokka'
    book.chapters[0].epigraph_text = 'A quote'
    db.session.flush()
    html = BookDoc(book, get_settings(book)).chapters[0]['html']
    assert re.match(r'<h1 class="chapter-title"[^>]*>The <span class="occ"[^>]*>Quokka</span></h1><blockquote', html)


def test_pdf_shows_the_epigraph_right_after_the_chapter_title(epigraph_book):
    result = get_layout(epigraph_book)
    texts = [(p.extract_text() or '') for p in PdfReader(io.BytesIO(result.pdf)).pages]
    page = next(t for t in texts if 'Chapter 1' in t and 'smiling' in t)
    assert page.index('Chapter 1') < page.index('smiling') < page.index('friend') < page.index('ZQC1P1X')
    assert '\u2014 An' in page                                                 # the source follows an em dash
    assert 'smiling' in page.split('\n')[2] or 'smiling' in page.split('\n')[1]  # kept on its own line, as typed


def test_layout_settings_choose_the_style_for_every_chapter(app):
    user = make_user()
    book, _ = make_book(user, chapters=2, paragraphs=1, terms=[], settings={
        'epigraph_align': 'center', 'epigraph_size': 'large', 'epigraph_italic': False, 'hyphenate': False})
    for chapter in book.chapters:
        chapter.epigraph_text = 'A quote'
    db.session.flush()
    for chapter in BookDoc(book, get_settings(book)).chapters:
        assert 'class="epigraph ep-center ep-large"' in chapter['html'] and 'ep-italic' not in chapter['html']


def test_defaults_and_stylesheets():
    assert (DEFAULTS['epigraph_align'], DEFAULTS['epigraph_size'], DEFAULTS['epigraph_italic']) == ('right', 'small', True)
    for css in (pdf_css(DEFAULTS), epub_css(DEFAULTS)):
        assert 'blockquote.epigraph.ep-right' in css and '.epigraph-source' in css


def test_layout_form_round_trips_the_epigraph_style_and_rejects_bad_values(alice):
    book_id = create_book(alice)
    page = alice.get(f'/books/{book_id}/layout').data.decode()
    assert 'name="epigraph_align"' in page and 'name="epigraph_size"' in page and 'name="epigraph_italic"' in page
    keep = {'include_title_page': 'on', 'include_contents': 'on', 'include_covers': 'on', 'chapter_new_page': 'on',
            'hyphenate': 'on'}
    alice.post(f'/books/{book_id}/layout', data={**keep, 'epigraph_align': 'left', 'epigraph_size': 'medium'})
    settings = get_settings(get_book(book_id))
    assert (settings['epigraph_align'], settings['epigraph_size'], settings['epigraph_italic']) == ('left', 'medium', False)
    alice.post(f'/books/{book_id}/layout', data={**keep, 'epigraph_italic': 'on', 'epigraph_align': 'right'})
    assert get_settings(get_book(book_id))['epigraph_italic'] is True
    bad = alice.post(f'/books/{book_id}/layout', data={**keep, 'epigraph_align': 'diagonal'}, follow_redirects=True)
    assert b'Invalid value for epigraph align' in bad.data
    assert get_settings(get_book(book_id))['epigraph_align'] == 'right'        # the bad value was not saved


def test_unknown_stored_style_values_fall_back_to_the_defaults(app):
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=1, settings={'epigraph_align': 'sideways', 'epigraph_size': 99})
    settings = get_settings(book)
    assert settings['epigraph_align'] == 'right' and settings['epigraph_size'] == 'small'


def test_epub_marks_the_epigraph_and_passes_validation(epigraph_book, tmp_path):
    data = build_epub(epigraph_book, get_layout(epigraph_book))
    archive = zipfile.ZipFile(io.BytesIO(data))
    chapter = archive.read('OEBPS/text/chapter-001.xhtml').decode()
    assert 'epub:type="epigraph"' in chapter and 'class="epigraph ep-right ep-small ep-italic"' in chapter
    ET.fromstring(archive.read('OEBPS/text/chapter-001.xhtml'))
    assert 'blockquote.epigraph' in archive.read('OEBPS/styles/book.css').decode()
    if shutil.which('java'):
        from epubcheck import EpubCheck
        path = tmp_path / 'epigraph.epub'
        path.write_bytes(data)
        result = EpubCheck(str(path))
        problems = [m for m in result.messages if m.level in ('ERROR', 'WARNING', 'FATAL')]
        assert not problems, '\n'.join(f'{m.level} {m.id} {m.location}: {m.message}' for m in problems)
