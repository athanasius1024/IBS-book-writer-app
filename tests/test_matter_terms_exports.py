import io
import zipfile

import pytest

from conftest import PNG_BYTES, create_book, get_book
from models import MediaAsset, db
from render import clear_cache

HX = {'HX-Request': 'true'}


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def post_page(client, book_id, page_type, **fields):
    data = {'page_type': page_type, 'body': 'Some words', 'align': 'center', 'valign': 'middle', 'size': 'medium',
            'italic': 'on'}
    data.update(fields)
    return client.post(f'/books/{book_id}/pages/new?type={page_type}', data=data)


def add_chapter_with_text(client, book_id, text, title='Chapter One'):
    resp = client.post(f'/books/{book_id}/chapters/new', data={'title': title})
    chapter_id = int(resp.headers['Location'].rsplit('/', 1)[-1])
    client.post(f'/chapters/{chapter_id}/blocks/new', data={'content_text': text}, headers=HX)
    return chapter_id


def complete(client, book_id):
    assert client.post(f'/books/{book_id}/complete').status_code == 302


# ---- Dedication and Quote pages ----------------------------------------------------------------

def test_add_dedication_and_quote_pages(alice):
    book_id = create_book(alice)
    resp = post_page(alice, book_id, 'dedication', body='For my family', align='right', valign='bottom',
                     size='large')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/books/{book_id}')
    resp = post_page(alice, book_id, 'quote', body='Nothing is softer\nthan water.',
                     attribution='Tao Teh Ching #78', italic=None)
    assert resp.status_code == 302
    pages = get_book(book_id).pages
    assert [p.page_type for p in pages] == ['dedication', 'quote']
    assert pages[0].style == {'align': 'right', 'valign': 'bottom', 'italic': True, 'size': 'large'}
    assert pages[1].attribution == 'Tao Teh Ching #78'
    assert pages[1].style['italic'] is False          # the italic box was not ticked for the quote
    page = alice.get(f'/books/{book_id}').data.decode()
    assert 'For my family' in page and 'Quote' in page and 'Front matter' in page


def test_italic_checkbox_off_is_saved_as_off(alice):
    book_id = create_book(alice)
    data = {'page_type': 'quote', 'body': 'x', 'align': 'left', 'valign': 'top', 'size': 'small'}   # no 'italic'
    alice.post(f'/books/{book_id}/pages/new?type=quote', data=data)
    assert get_book(book_id).pages[0].style == {'align': 'left', 'valign': 'top', 'italic': False, 'size': 'small'}


def test_dedication_always_sits_before_quotes_and_only_one_is_allowed(alice):
    book_id = create_book(alice)
    post_page(alice, book_id, 'quote', body='Quote one')
    post_page(alice, book_id, 'quote', body='Quote two')
    post_page(alice, book_id, 'dedication', body='Dedicated')
    assert [p.body for p in get_book(book_id).pages] == ['Dedicated', 'Quote one', 'Quote two']
    again = alice.get(f'/books/{book_id}/pages/new?type=dedication')
    assert again.status_code == 302 and '/edit' in again.headers['Location']
    assert len([p for p in get_book(book_id).pages if p.page_type == 'dedication']) == 1


def test_page_validation_and_unknown_type(alice):
    book_id = create_book(alice)
    empty = post_page(alice, book_id, 'quote', body='   ')
    assert empty.status_code == 200 and b'enter the text' in empty.data
    too_long = post_page(alice, book_id, 'quote', body='x' * 5001)
    assert b'limited to 5000' in too_long.data
    long_attr = post_page(alice, book_id, 'quote', attribution='y' * 301)
    assert b'attribution is limited' in long_attr.data
    assert get_book(book_id).pages == []
    assert alice.get(f'/books/{book_id}/pages/new?type=nonsense').status_code == 404
    # invalid style values fall back to the defaults
    post_page(alice, book_id, 'quote', body='ok', align='sideways', valign='up', size='huge')
    assert get_book(book_id).pages[0].style == {'align': 'center', 'valign': 'middle', 'italic': True,
                                                'size': 'medium'}


def test_page_edit_move_delete(alice):
    book_id = create_book(alice)
    post_page(alice, book_id, 'quote', body='First')
    post_page(alice, book_id, 'quote', body='Second')
    first, second = get_book(book_id).pages
    assert alice.get(f'/pages/{first.page_id}/edit').status_code == 200
    alice.post(f'/pages/{first.page_id}/edit', data={'body': 'First edited', 'attribution': 'Src', 'align': 'left',
                                                      'valign': 'top', 'size': 'small'})
    assert get_book(book_id).pages[0].body == 'First edited'
    alice.post(f'/pages/{second.page_id}/move', data={'direction': 'up'})
    assert [p.body for p in get_book(book_id).pages] == ['Second', 'First edited']
    assert alice.post(f'/pages/{first.page_id}/move', data={'direction': 'sideways'}).status_code == 400
    alice.post(f'/pages/{first.page_id}/delete')
    assert [p.body for p in get_book(book_id).pages] == ['Second']


def test_pages_are_private_and_locked_when_completed(alice, bob):
    book_id = create_book(alice)
    post_page(alice, book_id, 'quote', body='Mine')
    page = get_book(book_id).pages[0]
    for method, path in (('get', f'/pages/{page.page_id}/edit'), ('post', f'/pages/{page.page_id}/edit'),
                         ('post', f'/pages/{page.page_id}/delete'), ('post', f'/pages/{page.page_id}/move'),
                         ('get', f'/books/{book_id}/pages/new?type=quote'), ('post', f'/books/{book_id}/pages/new')):
        assert getattr(bob, method)(path, data={'direction': 'up', 'body': 'x'}).status_code == 404, path
    complete(alice, book_id)
    for method, path in (('get', f'/pages/{page.page_id}/edit'), ('post', f'/pages/{page.page_id}/delete'),
                         ('post', f'/pages/{page.page_id}/move'), ('get', f'/books/{book_id}/pages/new?type=quote')):
        resp = getattr(alice, method)(path, data={'direction': 'up'})
        assert resp.status_code == 302 and f'/books/{book_id}' in resp.headers['Location'], path
    assert alice.post(f'/pages/{page.page_id}/edit', data={'body': 'hacked'}).status_code == 302
    assert get_book(book_id).pages[0].body == 'Mine'


# ---- Authors ---------------------------------------------------------------------------------------

def add_author(client, book_id, **fields):
    data = {'name': 'Ann Author', 'role': 'Author', 'bio': 'Ann writes **books**.'}
    data.update(fields)
    return client.post(f'/books/{book_id}/authors/new', data=data, content_type='multipart/form-data')


def test_add_author_with_uploaded_photo(alice):
    book_id = create_book(alice)
    resp = add_author(alice, book_id, photo=(io.BytesIO(PNG_BYTES), 'me.png'))
    assert resp.status_code == 302
    author = get_book(book_id).authors[0]
    assert (author.name, author.role, author.bio) == ('Ann Author', 'Author', 'Ann writes **books**.')
    asset = db.session.get(MediaAsset, author.photo_asset_id)
    assert asset.asset_name == 'me.png'
    page = alice.get(f'/books/{book_id}/authors').data.decode()
    assert 'Ann Author' in page and '<strong>books</strong>' in page and f'/media/{asset.asset_id}' in page


def test_author_photo_from_library_remove_and_replace(alice):
    book_id = create_book(alice)
    alice.post('/media/upload', data={'image': (io.BytesIO(PNG_BYTES), 'lib.png')}, content_type='multipart/form-data')
    asset = MediaAsset.query.one()
    add_author(alice, book_id, photo_asset_id=str(asset.asset_id))
    author = get_book(book_id).authors[0]
    assert author.photo_asset_id == asset.asset_id and MediaAsset.query.count() == 1
    alice.post(f'/authors/{author.author_id}/edit', data={'name': 'Ann Author', 'remove_photo': '1'},
               content_type='multipart/form-data')
    assert get_book(book_id).authors[0].photo_asset_id is None
    alice.post(f'/authors/{author.author_id}/edit', data={'name': 'Ann Author',
                                                           'photo': (io.BytesIO(PNG_BYTES), 'new.png')},
               content_type='multipart/form-data')
    assert get_book(book_id).authors[0].photo.asset_name == 'new.png'


def test_author_validation(alice, bob):
    book_id = create_book(alice)
    assert b'needs a name' in add_author(alice, book_id, name='  ').data
    assert b'limited to 10000' in add_author(alice, book_id, bio='b' * 10001).data
    bad = add_author(alice, book_id, photo=(io.BytesIO(b'not an image'), 'x.png'))
    assert b'valid image' in bad.data
    bob.post('/media/upload', data={'image': (io.BytesIO(PNG_BYTES), 'bobs.png')}, content_type='multipart/form-data')
    bobs_asset = MediaAsset.query.filter_by(asset_name='bobs.png').one()
    stolen = add_author(alice, book_id, photo_asset_id=str(bobs_asset.asset_id))
    assert b'not found in your library' in stolen.data
    assert get_book(book_id).authors == []


def test_form_keeps_what_was_typed_after_an_error(alice):
    book_id = create_book(alice)
    resp = add_author(alice, book_id, name='Typed Name', bio='b' * 10001)
    assert b'value="Typed Name"' in resp.data


def test_authors_move_and_delete(alice):
    book_id = create_book(alice)
    add_author(alice, book_id, name='First')
    add_author(alice, book_id, name='Second')
    first, second = get_book(book_id).authors
    alice.post(f'/authors/{second.author_id}/move', data={'direction': 'up'})
    assert [a.name for a in get_book(book_id).authors] == ['Second', 'First']
    alice.post(f'/authors/{first.author_id}/delete')
    assert [a.name for a in get_book(book_id).authors] == ['Second']


def test_bio_belongs_to_the_book_so_a_copy_can_change_without_touching_the_original(alice):
    book_id = create_book(alice)
    add_author(alice, book_id, name='Ann', bio='Bio as of the first edition.')
    complete(alice, book_id)
    copy_id = int(alice.post(f'/books/{book_id}/copy').headers['Location'].rsplit('/', 1)[-1])
    copied = get_book(copy_id).authors[0]
    assert copied.bio == 'Bio as of the first edition.'
    alice.post(f'/authors/{copied.author_id}/edit', data={'name': 'Ann', 'bio': 'Bio for the second edition.'},
               content_type='multipart/form-data')
    assert get_book(copy_id).authors[0].bio == 'Bio for the second edition.'
    assert get_book(book_id).authors[0].bio == 'Bio as of the first edition.'


def test_prefill_author_from_another_book_copies_the_text(alice, bob):
    first = create_book(alice, 'Older Book')
    add_author(alice, first, name='Ann', role='Author', bio='Original bio.')
    second = create_book(alice, 'Newer Book')
    source = get_book(first).authors[0]
    form = alice.get(f'/books/{second}/authors/new?from={source.author_id}')
    assert form.status_code == 200 and b'Original bio.' in form.data and b'Ann' in form.data
    add_author(alice, second, name='Ann', role='Author', bio='Updated bio.')
    assert get_book(first).authors[0].bio == 'Original bio.'
    assert get_book(second).authors[0].bio == 'Updated bio.'
    # another user cannot start from someone else's author
    bobs_book = create_book(bob, 'Bobs')
    assert bob.get(f'/books/{bobs_book}/authors/new?from={source.author_id}').status_code == 404


def test_authors_are_private_and_locked_when_completed(alice, bob):
    book_id = create_book(alice)
    add_author(alice, book_id)
    author = get_book(book_id).authors[0]
    assert bob.get(f'/books/{book_id}/authors').status_code == 404
    for method, path in (('get', f'/authors/{author.author_id}/edit'), ('post', f'/authors/{author.author_id}/edit'),
                         ('post', f'/authors/{author.author_id}/delete'), ('post', f'/authors/{author.author_id}/move'),
                         ('get', f'/books/{book_id}/authors/new'), ('post', f'/books/{book_id}/authors/new')):
        assert getattr(bob, method)(path, data={'direction': 'up', 'name': 'x'}).status_code == 404, path
    complete(alice, book_id)
    for method, path in (('get', f'/authors/{author.author_id}/edit'), ('post', f'/authors/{author.author_id}/delete'),
                         ('post', f'/authors/{author.author_id}/move'), ('get', f'/books/{book_id}/authors/new')):
        resp = getattr(alice, method)(path, data={'direction': 'up'})
        assert resp.status_code == 302, path
    assert alice.get(f'/books/{book_id}/authors').status_code == 200          # viewing is still allowed
    assert len(get_book(book_id).authors) == 1


# ---- Terms ----------------------------------------------------------------------------------------------

def add_term(client, book_id, term='Quokka', **fields):
    data = {'term': term, 'definition': 'A small marsupial', 'match_plural': 'on', 'in_index': 'on',
            'in_glossary': 'on'}
    data.update(fields)
    return client.post(f'/books/{book_id}/terms/new', data=data)


def test_add_edit_delete_term(alice):
    book_id = create_book(alice)
    assert add_term(alice, book_id, variants='quokka\nQuokka Island').status_code == 302
    term = get_book(book_id).terms[0]
    assert (term.term, term.definition, term.variant_list) == ('Quokka', 'A small marsupial', ['quokka', 'Quokka Island'])
    assert term.match_plural and term.in_index and term.in_glossary and not term.match_case
    alice.post(f'/terms/{term.term_id}/edit', data={'term': 'Quokkas', 'definition': '', 'match_case': 'on'})
    term = get_book(book_id).terms[0]
    assert term.term == 'Quokkas' and term.definition is None and term.match_case
    assert not term.match_plural and not term.in_index and not term.in_glossary     # unchecked boxes are off
    assert not term.has_entry
    alice.post(f'/terms/{term.term_id}/delete')
    assert get_book(book_id).terms == []


def test_term_validation(alice):
    book_id = create_book(alice)
    assert b'term is required' in add_term(alice, book_id, term='   ').data
    assert b'limited to 200' in add_term(alice, book_id, term='x' * 201).data
    assert b'limited to 2000' in add_term(alice, book_id, definition='d' * 2001).data
    assert b'at most 20 variants' in add_term(alice, book_id, variants='\n'.join(f'v{i}' for i in range(21))).data
    add_term(alice, book_id, term='Region')
    duplicate = add_term(alice, book_id, term='  region ')
    assert b'already in this book' in duplicate.data
    assert len(get_book(book_id).terms) == 1
    add_term(alice, book_id, term='Other')
    other = [t for t in get_book(book_id).terms if t.term == 'Other'][0]
    clash = alice.post(f'/terms/{other.term_id}/edit', data={'term': 'REGION'})
    assert b'already in this book' in clash.data


def test_terms_screen_shows_how_often_each_term_is_used(alice):
    book_id = create_book(alice)
    add_chapter_with_text(alice, book_id, 'The quokka met another quokka. Quokkas are small. Nothing about the other.')
    add_term(alice, book_id, term='Quokka')
    add_term(alice, book_id, term='Walrus', definition='A big animal')
    page = alice.get(f'/books/{book_id}/terms').data.decode()
    assert '<span class="badge bg-primary">3</span>' in page      # quokka, quokka, Quokkas (plural)
    assert 'unused' in page and 'Walrus' in page
    assert '2 terms.' in page


def test_terms_are_private_and_locked_when_completed(alice, bob):
    book_id = create_book(alice)
    add_term(alice, book_id)
    term = get_book(book_id).terms[0]
    assert bob.get(f'/books/{book_id}/terms').status_code == 404
    for method, path in (('get', f'/terms/{term.term_id}/edit'), ('post', f'/terms/{term.term_id}/edit'),
                         ('post', f'/terms/{term.term_id}/delete'), ('get', f'/books/{book_id}/terms/new'),
                         ('post', f'/books/{book_id}/terms/new')):
        assert getattr(bob, method)(path, data={'term': 'x'}).status_code == 404, path
    complete(alice, book_id)
    for method, path in (('get', f'/terms/{term.term_id}/edit'), ('post', f'/terms/{term.term_id}/delete'),
                         ('get', f'/books/{book_id}/terms/new')):
        assert getattr(alice, method)(path).status_code == 302, path
    assert alice.post(f'/books/{book_id}/terms/new', data={'term': 'late'}).status_code == 302
    assert alice.get(f'/books/{book_id}/terms').status_code == 200
    assert [t.term for t in get_book(book_id).terms] == ['Quokka']


def test_copy_carries_pages_terms_and_layout(alice):
    book_id = create_book(alice)
    post_page(alice, book_id, 'quote', body='A verse', attribution='Someone', align='left')
    add_term(alice, book_id, term='Quokka', variants='quokka')
    alice.post(f'/books/{book_id}/layout', data={'trim': '6x9', 'font_size': '12', 'columns': '2', 'font': 'sans',
                                                  'align': 'left', 'para_style': 'space', 'page_numbers': 'center',
                                                  'front_numbering': 'none', 'running_head': 'title',
                                                  'link_mode': 'all', 'language': 'en', 'hyphenate': 'on'})
    complete(alice, book_id)
    copy_id = int(alice.post(f'/books/{book_id}/copy').headers['Location'].rsplit('/', 1)[-1])
    copy = get_book(copy_id)
    assert [(p.body, p.attribution, p.style['align']) for p in copy.pages] == [('A verse', 'Someone', 'left')]
    assert [(t.term, t.variant_list) for t in copy.terms] == [('Quokka', ['quokka'])]
    assert copy.layout.settings['trim'] == '6x9' and copy.layout.settings['columns'] == 2
    assert copy.layout.layout_id != get_book(book_id).layout.layout_id


# ---- Layout screen ------------------------------------------------------------------------------------------

LAYOUT_FORM = {'trim': '5x8', 'width_mm': '139.7', 'height_mm': '215.9', 'margin_top': '20', 'margin_bottom': '22',
               'margin_inside': '22', 'margin_outside': '16', 'columns': '2', 'column_gap': '6', 'font': 'sans',
               'font_size': '10.5', 'line_height': '1.5', 'align': 'left', 'para_style': 'space',
               'page_numbers': 'center', 'front_numbering': 'none', 'running_head': 'chapter', 'link_mode': 'all',
               'language': 'en-GB', 'hyphenate': 'on', 'include_covers': 'on', 'include_contents': 'on'}


def test_layout_screen_shows_defaults_and_saves_settings(alice):
    book_id = create_book(alice)
    page = alice.get(f'/books/{book_id}/layout').data.decode()
    assert 'Page view' in page and 'preview.pdf' in page and 'value="11"' in page
    assert alice.post(f'/books/{book_id}/layout', data=LAYOUT_FORM).status_code == 302
    saved = get_book(book_id).layout.settings
    assert saved['trim'] == '5x8' and saved['columns'] == 2 and saved['font'] == 'sans'
    assert saved['font_size'] == 10.5 and saved['language'] == 'en-GB' and saved['link_mode'] == 'all'
    assert saved['hyphenate'] is True and saved['include_title_page'] is False      # unchecked box = off
    assert alice.get(f'/books/{book_id}/layout').status_code == 200


def test_layout_validation_rejects_bad_values_and_saves_nothing(alice):
    book_id = create_book(alice)
    for override, fragment in (({'font_size': '99'}, b'between 7 and 18'), ({'margin_top': 'abc'}, b'must be a number'),
                               ({'margin_inside': '55', 'margin_outside': '55'}, b'less than 50 mm of text width'),
                               ({'trim': 'custom', 'height_mm': '150', 'margin_top': '40', 'margin_bottom': '40'},
                                b'less than 80 mm of text height'),
                               ({'trim': 'tabloid'}, b'Invalid value for trim'),
                               ({'language': 'not a code!'}, b'Language must be a code')):
        data = dict(LAYOUT_FORM, **override)
        resp = alice.post(f'/books/{book_id}/layout', data=data)
        assert resp.status_code == 200 and fragment in resp.data, override
        assert get_book(book_id).layout is None


def test_layout_reset_and_privacy_and_lock(alice, bob):
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/layout', data=LAYOUT_FORM)
    assert get_book(book_id).layout is not None
    alice.post(f'/books/{book_id}/layout', data={'reset': '1'})
    assert get_book(book_id).layout is None
    for path in (f'/books/{book_id}/layout', f'/books/{book_id}/layout/preview.pdf',
                 f'/books/{book_id}/export/pdf', f'/books/{book_id}/export/epub'):
        assert bob.get(path).status_code == 404, path
    assert bob.post(f'/books/{book_id}/layout', data=LAYOUT_FORM).status_code == 404
    complete(alice, book_id)
    assert alice.post(f'/books/{book_id}/layout', data=LAYOUT_FORM).status_code == 302
    assert get_book(book_id).layout is None                                       # locked: nothing saved
    assert alice.get(f'/books/{book_id}/layout').status_code == 200


# ---- Page view and downloads -------------------------------------------------------------------------------------

@pytest.fixture()
def finished_book(alice):
    book_id = create_book(alice, 'Download Me')
    add_chapter_with_text(alice, book_id, 'A quokka walks. The quokka rests.')
    post_page(alice, book_id, 'dedication', body='For everyone')
    post_page(alice, book_id, 'quote', body='A line\nof verse', attribution='A Poet')
    add_author(alice, book_id, name='Ann Author', photo=(io.BytesIO(PNG_BYTES), 'ann.png'))
    add_term(alice, book_id, term='Quokka')
    return book_id


def test_page_view_and_pdf_download(alice, finished_book):
    view = alice.get(f'/books/{finished_book}/layout/preview.pdf')
    assert view.status_code == 200 and view.mimetype == 'application/pdf' and view.data.startswith(b'%PDF')
    assert 'attachment' not in view.headers.get('Content-Disposition', '')
    download = alice.get(f'/books/{finished_book}/export/pdf')
    assert download.status_code == 200 and download.mimetype == 'application/pdf'
    assert 'attachment' in download.headers['Content-Disposition'] and 'Download_Me.pdf' in download.headers['Content-Disposition']


def test_epub_download_contains_everything(alice, finished_book):
    resp = alice.get(f'/books/{finished_book}/export/epub')
    assert resp.status_code == 200 and resp.mimetype == 'application/epub+zip'
    assert 'attachment' in resp.headers['Content-Disposition'] and 'Download_Me.epub' in resp.headers['Content-Disposition']
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    assert archive.infolist()[0].filename == 'mimetype'
    text = {n: archive.read(n).decode() for n in archive.namelist() if n.endswith('.xhtml')}
    joined = ' '.join(text.values())
    for expected in ('For everyone', 'A Poet', 'Ann Author', 'epub:type="glossary"', 'epub:type="index"', 'Quokka'):
        assert expected in joined, expected
    assert any(n.endswith('.png') for n in archive.namelist())


def test_exports_work_for_completed_books_and_require_login(alice, finished_book, client):
    complete(alice, finished_book)
    assert alice.get(f'/books/{finished_book}/export/epub').status_code == 200
    assert alice.get(f'/books/{finished_book}/export/pdf').status_code == 200
    for path in (f'/books/{finished_book}/export/epub', f'/books/{finished_book}/export/pdf',
                 f'/books/{finished_book}/layout/preview.pdf', f'/books/{finished_book}/layout'):
        resp = client.get(path)
        assert resp.status_code == 302 and '/login' in resp.headers['Location'], path


def test_a_failing_render_is_reported_kindly_instead_of_a_server_error(alice, finished_book, monkeypatch):
    import exports

    def boom(book):
        raise RuntimeError('layout engine exploded')
    monkeypatch.setattr(exports, 'get_layout', boom)
    for path in (f'/books/{finished_book}/export/epub', f'/books/{finished_book}/export/pdf'):
        resp = alice.get(path, follow_redirects=True)
        assert resp.status_code == 200 and b'could not be built' in resp.data and b'exploded' not in resp.data
    pdf = alice.get(f'/books/{finished_book}/layout/preview.pdf')
    assert pdf.status_code == 302


def test_download_names_are_safe(alice):
    book_id = create_book(alice, '../../etc/passwd "quoted" title')
    resp = alice.get(f'/books/{book_id}/export/epub')
    disposition = resp.headers['Content-Disposition']
    assert '..' not in disposition and '/' not in disposition.split('filename=')[1] and '"quoted"' not in disposition
    unicode_title = create_book(alice, '\u4e66')
    assert alice.get(f'/books/{unicode_title}/export/epub').headers['Content-Disposition'].count('book.epub') == 1


def test_book_page_has_the_new_cards_and_export_buttons(alice, finished_book):
    page = alice.get(f'/books/{finished_book}').data.decode()
    for label in ('Front matter', 'Authors', 'Glossary &amp; Index', 'Layout &amp; Export', 'Download EPUB',
                  'Download PDF', 'Ann Author', '1</strong> term'):
        assert label in page, label
    assert '2 term' not in page


def test_html_preview_includes_the_new_sections(alice, finished_book):
    page = alice.get(f'/books/{finished_book}/preview').data.decode()
    assert 'For everyone' in page and 'A Poet' in page and 'About the Author' in page and 'Ann Author' in page
    assert 'A line<br>' in page            # single line breaks in a quote are kept
