import io
import re

import pytest

from blocks import parse_table
from conftest import PNG_BYTES, create_book, get_book
from models import Book, ContentBlock, MediaAsset, db

HX = {'HX-Request': 'true'}


def add_chapter(client, book_id, title='Chapter One'):
    resp = client.post(f'/books/{book_id}/chapters/new', data={'title': title})
    assert resp.status_code == 302
    return int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])


def post_block(client, chapter_id, **fields):
    return client.post(f'/chapters/{chapter_id}/blocks/new', data=fields,
                       content_type='multipart/form-data', headers=HX)


def last_block(chapter_id):
    return (ContentBlock.query.filter_by(chapter_id=chapter_id)
            .order_by(ContentBlock.block_id.desc()).first())


def png(name='pic.png'):
    return (io.BytesIO(PNG_BYTES), name)


@pytest.fixture()
def chapter(alice):
    book_id = create_book(alice, 'Blocks')
    return book_id, add_chapter(alice, book_id)


# ---- table parsing ------------------------------------------------------------

def test_parse_table_pads_ragged_rows_and_strips_pipes():
    assert parse_table('| a | b | c |\n1 | 2\n\n') == [['a', 'b', 'c'], ['1', '2', '']]


@pytest.mark.parametrize('source', ['', '   \n\n', ' | '.join('x' * 1 for _ in range(21)),
                                    '\n'.join('a' for _ in range(201)), 'a' * 501])
def test_parse_table_rejects_bad_input(source):
    with pytest.raises(ValueError):
        parse_table(source)


# ---- creating each block type -------------------------------------------------

def test_default_block_type_is_text(alice, chapter):
    _, cid = chapter
    assert post_block(alice, cid, content_text='plain **md**').status_code == 200
    block = last_block(cid)
    assert block.block_type == 'text' and block.content_data is None


def test_heading_block(alice, chapter):
    _, cid = chapter
    resp = post_block(alice, cid, block_type='heading', content_text='  Big News ', heading_level='1')
    assert resp.status_code == 200 and b'<h3 class="block-heading">Big News</h3>' in resp.data
    assert last_block(cid).content_data == {'level': 1}
    post_block(alice, cid, block_type='heading', content_text='Bad level', heading_level='9')
    assert last_block(cid).content_data == {'level': 2}   # falls back to medium


def test_list_blocks(alice, chapter):
    _, cid = chapter
    unordered = post_block(alice, cid, block_type='list', content_text='one\n\n two \nthree')
    assert b'<ul class="block-list">' in unordered.data and b'<li>two</li>' in unordered.data
    assert last_block(cid).content_text == 'one\ntwo\nthree'
    ordered = post_block(alice, cid, block_type='list', content_text='a\nb', list_ordered='1')
    assert b'<ol class="block-list">' in ordered.data


def test_table_block_with_and_without_header(alice, chapter):
    _, cid = chapter
    with_header = post_block(alice, cid, block_type='table', table_header='1',
                             content_text='Name | Year\nAda | 1843\nBob')
    html = with_header.data.decode()
    assert '<thead' in html and '<th>Name</th>' in html and '<td>Ada</td>' in html
    assert last_block(cid).content_data['rows'][2] == ['Bob', '']
    no_header = post_block(alice, cid, block_type='table', content_text='x | y')
    assert b'<thead' not in no_header.data and b'<td>x</td>' in no_header.data


def test_image_block_upload_and_caption(alice, chapter):
    _, cid = chapter
    resp = post_block(alice, cid, block_type='image', content_text='A caption', image=png())
    assert resp.status_code == 200
    block = last_block(cid)
    asset = MediaAsset.query.one()
    assert block.asset_id == asset.asset_id and block.content_text == 'A caption'
    assert f'/media/{asset.asset_id}'.encode() in resp.data
    assert b'<figcaption' in resp.data and b'A caption' in resp.data


def test_icon_block_from_library(alice, chapter):
    _, cid = chapter
    alice.post('/media/upload', data={'image': png('icon.png')}, content_type='multipart/form-data')
    asset = MediaAsset.query.one()
    resp = post_block(alice, cid, block_type='icon', asset_id=str(asset.asset_id), content_text='Home')
    assert resp.status_code == 200 and b'block-icon-img' in resp.data
    assert last_block(cid).asset_id == asset.asset_id
    assert MediaAsset.query.count() == 1     # picking from the library does not duplicate


@pytest.mark.parametrize('fields,fragment', [
    ({'block_type': 'nonsense', 'content_text': 'x'}, b'Unknown block type'),
    ({'block_type': 'text', 'content_text': '   '}, b'enter some text'),
    ({'block_type': 'heading', 'content_text': ''}, b'heading text'),
    ({'block_type': 'list', 'content_text': '\n\n'}, b'at least one list item'),
    ({'block_type': 'table', 'content_text': ''}, b'at least one table row'),
    ({'block_type': 'image', 'content_text': 'cap'}, b'Choose an image'),
    ({'block_type': 'image', 'asset_id': '99999'}, b'not found in your library'),
])
def test_validation_errors_are_plain_400s(alice, chapter, fields, fragment):
    _, cid = chapter
    resp = post_block(alice, cid, **fields)
    assert resp.status_code == 400 and fragment in resp.data
    assert not resp.data.lstrip().startswith(b'<')       # short plain text, not an HTML error page
    assert ContentBlock.query.count() == 0


def test_bad_image_upload_rejected(alice, chapter):
    _, cid = chapter
    resp = post_block(alice, cid, block_type='image', image=(io.BytesIO(b'not an image'), 'x.png'))
    assert resp.status_code == 400 and b'valid image' in resp.data
    assert MediaAsset.query.count() == 0 and ContentBlock.query.count() == 0


def test_cannot_use_another_users_library_image(alice, bob, chapter):
    _, cid = chapter
    bob.post('/media/upload', data={'image': png('bobs.png')}, content_type='multipart/form-data')
    bobs_asset = MediaAsset.query.filter_by(asset_name='bobs.png').one()
    resp = post_block(alice, cid, block_type='image', asset_id=str(bobs_asset.asset_id))
    assert resp.status_code == 400 and b'not found in your library' in resp.data
    assert ContentBlock.query.count() == 0


# ---- escaping -----------------------------------------------------------------

def test_user_text_is_escaped_in_every_block_type(alice, chapter):
    book_id, cid = chapter
    evil = '<script>alert(1)</script>'
    post_block(alice, cid, block_type='heading', content_text=evil)
    post_block(alice, cid, block_type='list', content_text=evil)
    post_block(alice, cid, block_type='table', content_text=f'{evil} | <b>x</b>')
    post_block(alice, cid, block_type='image', content_text=evil, image=png())
    for html in (alice.get(f'/chapters/{cid}').data.decode(),
                 alice.get(f'/books/{book_id}/preview').data.decode()):
        assert '<script>alert(1)' not in html
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert '<b>x</b>' not in html


# ---- editing --------------------------------------------------------------------

def test_edit_each_block_type(alice, chapter):
    _, cid = chapter
    post_block(alice, cid, block_type='heading', content_text='Old', heading_level='2')
    heading = last_block(cid)
    resp = alice.post(f'/blocks/{heading.block_id}/save', data={'content_text': 'New', 'heading_level': '3'},
                      headers=HX)
    assert resp.status_code == 200
    assert (heading.content_text, heading.content_data) == ('New', {'level': 3})

    post_block(alice, cid, block_type='table', content_text='a | b', table_header='1')
    table = last_block(cid)
    alice.post(f'/blocks/{table.block_id}/save', data={'content_text': 'x | y\n1 | 2'}, headers=HX)
    assert table.content_data == {'header': False, 'rows': [['x', 'y'], ['1', '2']]}   # box unchecked -> off

    # the edit form is rendered for the block's own type and pre-filled
    form = alice.get(f'/blocks/{table.block_id}/edit', headers=HX).data.decode()
    assert 'x | y' in form and 'name="table_header"' in form and 'name="heading_level"' not in form


def test_edit_cannot_change_block_type(alice, chapter):
    _, cid = chapter
    post_block(alice, cid, block_type='heading', content_text='H')
    block = last_block(cid)
    alice.post(f'/blocks/{block.block_id}/save', data={'block_type': 'table', 'content_text': 'H2'}, headers=HX)
    assert block.block_type == 'heading' and block.content_text == 'H2'


def test_edit_image_keeps_replaces_and_validates(alice, chapter):
    _, cid = chapter
    post_block(alice, cid, block_type='image', content_text='cap', image=png('first.png'))
    block = last_block(cid)
    first_id = block.asset_id

    keep = alice.post(f'/blocks/{block.block_id}/save', data={'content_text': 'new caption'},
                      content_type='multipart/form-data', headers=HX)
    assert keep.status_code == 200 and block.asset_id == first_id and block.content_text == 'new caption'

    alice.post(f'/blocks/{block.block_id}/save', data={'content_text': 'x', 'image': png('second.png')},
               content_type='multipart/form-data', headers=HX)
    assert block.asset_id != first_id and MediaAsset.query.count() == 2

    bad = alice.post(f'/blocks/{block.block_id}/save', data={'asset_id': '424242'},
                     content_type='multipart/form-data', headers=HX)
    assert bad.status_code == 400


# ---- completed-book lock for the new types -------------------------------------------

def test_completed_book_rejects_new_block_types(alice, chapter):
    book_id, cid = chapter
    post_block(alice, cid, block_type='heading', content_text='Keep me')
    alice.post(f'/books/{book_id}/complete')
    for fields in ({'block_type': 'table', 'content_text': 'a | b'},
                   {'block_type': 'image', 'image': png()},
                   {'block_type': 'list', 'content_text': 'x'}):
        resp = post_block(alice, cid, **fields)
        assert resp.status_code == 409, fields
    assert ContentBlock.query.count() == 1 and MediaAsset.query.count() == 0
    # completed pages hide the add-content form and the block controls
    page = alice.get(f'/chapters/{cid}').data.decode()
    assert 'Add content' not in page and 'btn-delete-block' not in page


# ---- undo support --------------------------------------------------------------------

def test_restore_payload_and_position_insert(alice, chapter):
    _, cid = chapter
    for text in ('one', 'two', 'three'):
        post_block(alice, cid, block_type='heading', content_text=text)
    blocks = ContentBlock.query.filter_by(chapter_id=cid).order_by(ContentBlock.sort_order).all()
    middle = blocks[1]

    page = alice.get(f'/chapters/{cid}').data.decode()
    payloads = re.findall(r"data-restore='([^']+)'", page)
    assert len(payloads) == 3
    import html, json
    data = json.loads(html.unescape(payloads[1]))
    assert data['url'] == f'/chapters/{cid}/blocks/new'
    assert data['fields']['block_type'] == 'heading' and data['fields']['content_text'] == 'two'
    assert data['fields']['position'] == 2

    assert alice.delete(f'/blocks/{middle.block_id}/delete', headers=HX).status_code == 200
    restore = {k: v for k, v in data['fields'].items() if v not in ('', None)}
    assert post_block(alice, cid, **restore).status_code == 200
    ordered = (ContentBlock.query.filter_by(chapter_id=cid).order_by(ContentBlock.sort_order).all())
    assert [b.content_text for b in ordered] == ['one', 'two', 'three']
    assert [b.sort_order for b in ordered] == [1, 2, 3]


def test_restore_of_an_image_block_reuses_the_asset(alice, chapter):
    _, cid = chapter
    post_block(alice, cid, block_type='image', content_text='cap', image=png())
    block = last_block(cid)
    asset_id, block_id = block.asset_id, block.block_id
    alice.delete(f'/blocks/{block_id}/delete', headers=HX)
    resp = post_block(alice, cid, block_type='image', content_text='cap', asset_id=str(asset_id), position='1')
    assert resp.status_code == 200 and last_block(cid).asset_id == asset_id
    assert MediaAsset.query.count() == 1


# ---- copy-to-edit keeps the new fields ---------------------------------------------------

def test_copy_preserves_block_types_data_and_assets(alice, chapter):
    book_id, cid = chapter
    post_block(alice, cid, block_type='table', content_text='a | b\n1 | 2', table_header='1')
    post_block(alice, cid, block_type='image', content_text='cap', image=png())
    alice.post(f'/books/{book_id}/complete')
    copy_id = int(alice.post(f'/books/{book_id}/copy').headers['Location'].rsplit('/', 1)[-1])
    originals = get_book(book_id).chapters[0].blocks
    copies = get_book(copy_id).chapters[0].blocks
    assert [(b.block_type, b.content_text, b.content_data, b.asset_id) for b in copies] == \
           [(b.block_type, b.content_text, b.content_data, b.asset_id) for b in originals]
    assert MediaAsset.query.count() == 1


def test_word_counts(alice, chapter):
    book_id, cid = chapter
    post_block(alice, cid, block_type='text', content_text='one two three')
    post_block(alice, cid, block_type='heading', content_text='Four five')
    post_block(alice, cid, block_type='list', content_text='six\nseven eight')
    post_block(alice, cid, block_type='table', content_text='nine | ten\neleven | twelve')
    post_block(alice, cid, block_type='image', content_text='not counted', image=png())
    book = get_book(book_id)
    assert book.word_count == 12 and book.block_count == 5


# ---- media library -----------------------------------------------------------------------

def test_library_upload_list_and_delete_unused(alice, app):
    resp = alice.post('/media/upload', data={'image': [png('a.png'), png('b.png')]},
                      content_type='multipart/form-data', follow_redirects=True)
    assert b'Uploaded 2 images' in resp.data
    page = alice.get('/media').data.decode()
    assert 'a.png' in page and 'b.png' in page and page.count('Unused') == 2

    asset = MediaAsset.query.filter_by(asset_name='a.png').one()
    path = app.config['UPLOAD_DIR'] / asset.file_path
    assert path.exists()
    assert alice.post(f'/media/{asset.asset_id}/delete').status_code == 302
    assert db.session.get(MediaAsset, asset.asset_id) is None and not path.exists()


def test_library_upload_errors(alice):
    none = alice.post('/media/upload', data={}, content_type='multipart/form-data', follow_redirects=True)
    assert b'Choose at least one image' in none.data
    mixed = alice.post('/media/upload', data={'image': [png('ok.png'), (io.BytesIO(b'zzz'), 'bad.png')]},
                       content_type='multipart/form-data', follow_redirects=True)
    assert b'Uploaded 1 image' in mixed.data and b'bad.png' in mixed.data
    assert MediaAsset.query.count() == 1


def test_library_blocks_deleting_used_images(alice, chapter):
    book_id, cid = chapter
    post_block(alice, cid, block_type='image', image=png('used-in-block.png'))
    alice.post(f'/books/{book_id}/cover/front', data={'image': png('used-on-cover.png')},
               content_type='multipart/form-data')
    for asset in MediaAsset.query.all():
        resp = alice.post(f'/media/{asset.asset_id}/delete', follow_redirects=True)
        assert b'still used' in resp.data
        assert db.session.get(MediaAsset, asset.asset_id) is not None
    page = alice.get('/media').data.decode()
    assert '1 cover' in page and '1 block' in page


def test_library_is_private(alice, bob):
    alice.post('/media/upload', data={'image': png('alices.png')}, content_type='multipart/form-data')
    asset = MediaAsset.query.one()
    assert 'alices.png' not in bob.get('/media').data.decode()
    assert bob.post(f'/media/{asset.asset_id}/delete').status_code == 404
    assert db.session.get(MediaAsset, asset.asset_id) is not None
    assert alice.get('/media').status_code == 200


def test_library_requires_login(client):
    for method, path in (('get', '/media'), ('post', '/media/upload'), ('post', '/media/1/delete')):
        resp = getattr(client, method)(path)
        assert resp.status_code == 302 and '/login' in resp.headers['Location']


# ---- dashboard --------------------------------------------------------------------------------

def stat_cards(html):
    return [int(n) for n in re.findall(r'<h2 class="card-text">(\d+)</h2>', html)]


def test_dashboard_empty_state(alice):
    html = alice.get('/').data.decode()
    assert stat_cards(html) == [0, 0, 0, 0, 0, 0]
    assert 'Create your first book' in html and 'No book yet' in html


def test_dashboard_statistics(alice):
    draft = create_book(alice, 'Draft Book')
    done = create_book(alice, 'Done Book')
    cid = add_chapter(alice, draft)
    add_chapter(alice, draft, 'Two')
    post_block(alice, cid, block_type='text', content_text='alpha beta gamma')
    post_block(alice, cid, block_type='image', image=png())
    alice.post(f'/books/{done}/complete')

    html = alice.get('/').data.decode()
    # books, drafts, completed, chapters, blocks, images
    assert stat_cards(html) == [2, 1, 1, 2, 2, 1]
    assert 'Recently Modified Books' in html and 'Draft Book' in html and 'Done Book' in html
    assert 'Book Status' in html and 'Quick Actions' in html
    assert 'Continue Latest Draft' in html


def test_dashboard_latest_book_status_shows_words(alice):
    book_id = create_book(alice, 'Wordy')
    cid = add_chapter(alice, book_id)
    post_block(alice, cid, block_type='text', content_text='one two three four five')
    html = alice.get('/').data.decode()
    assert '<strong>Words:</strong> 5' in html and '<strong>Content blocks:</strong> 1' in html
    assert 'Continue Editing' in html


def test_dashboard_only_counts_own_data(alice, bob):
    create_book(alice, 'Alice Book')
    book = create_book(bob, 'Bob Book')
    cid = add_chapter(bob, book)
    post_block(bob, cid, block_type='text', content_text='hello')
    alice_html = alice.get('/').data.decode()
    assert stat_cards(alice_html) == [1, 1, 0, 0, 0, 0]
    assert 'Bob Book' not in alice_html
    assert stat_cards(bob.get('/').data.decode()) == [1, 1, 0, 1, 1, 0]


def test_dashboard_admin_shortcut_only_for_admin(alice, bob):
    assert 'Database Settings' in alice.get('/').data.decode()
    assert 'Database Settings' not in bob.get('/').data.decode()


def test_my_books_page_lists_books(alice):
    ids = [create_book(alice, f'Shelf {i}') for i in range(3)]
    html = alice.get('/books').data.decode()
    assert all(f'Shelf {i}' in html for i in range(3))
    assert all(f'/books/{i}' in html for i in ids)
    assert alice.post(f'/books/{ids[0]}/delete').headers['Location'].endswith('/books')


def test_nav_has_dashboard_books_and_media(alice):
    html = alice.get('/books').data.decode()
    for label in ('Dashboard', 'My Books', 'New Book', 'Media Library'):
        assert label in html
