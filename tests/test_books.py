import io

import pytest

from conftest import PNG_BYTES, create_book, get_book, has_mode
from models import COVER_PANEL_KEYS, Book, ContentBlock, MediaAsset, db

HX = {'HX-Request': 'true'}


def add_chapter(client, book_id, title='Chapter One'):
    resp = client.post(f'/books/{book_id}/chapters/new', data={'title': title})
    assert resp.status_code == 302
    return int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])


def add_block(client, chapter_id, text='Hello **world**'):
    resp = client.post(f'/chapters/{chapter_id}/blocks/new', data={'content_text': text}, headers=HX)
    assert resp.status_code == 200
    return ContentBlock.query.filter_by(chapter_id=chapter_id).order_by(ContentBlock.block_id.desc()).first().block_id


# ---- creating books / multiple books per user ------------------------------

def test_new_book_creates_five_cover_panels(alice):
    book_id = create_book(alice, 'First')
    book = get_book(book_id)
    assert sorted(c.panel for c in book.covers) == sorted(COVER_PANEL_KEYS)
    assert book.status == 'draft'
    assert 'First' in book.cover('spine').content_text
    assert 'First' in book.cover('front').content_text


def test_user_can_have_many_books(alice):
    ids = [create_book(alice, f'Book {i}') for i in range(3)]
    assert len(set(ids)) == 3
    page = alice.get('/').data.decode()
    for i in range(3):
        assert f'Book {i}' in page


def test_title_required(alice):
    resp = alice.post('/books/new', data={'title': '   '})
    assert resp.status_code == 200
    assert b'title is required' in resp.data
    assert Book.query.count() == 0


def test_edit_book_details(alice):
    book_id = create_book(alice, 'Old')
    resp = alice.post(f'/books/{book_id}/edit', data={
        'title': 'New title', 'subtitle': 'Sub', 'author_name': 'Me', 'copyright_year': '2024', 'version': '1.0'})
    assert resp.status_code == 302
    book = get_book(book_id)
    assert (book.title, book.subtitle, book.copyright_year, book.version) == ('New title', 'Sub', 2024, '1.0')


def test_edit_rejects_bad_year_and_keeps_input(alice):
    book_id = create_book(alice, 'Old')
    resp = alice.post(f'/books/{book_id}/edit', data={'title': 'Changed', 'copyright_year': 'abc'})
    assert resp.status_code == 200
    assert b'valid year' in resp.data
    assert b'value="Changed"' in resp.data  # user input is preserved in the form
    assert get_book(book_id).title == 'Old'


def test_delete_book(alice):
    book_id = create_book(alice)
    assert alice.post(f'/books/{book_id}/delete').status_code == 302
    assert get_book(book_id) is None


# ---- ownership isolation ----------------------------------------------------

def test_other_users_cannot_access_a_book(alice, bob):
    book_id = create_book(alice, 'Secret')
    chapter_id = add_chapter(alice, book_id)
    block_id = add_block(alice, chapter_id)

    gets = [f'/books/{book_id}', f'/books/{book_id}/edit', f'/books/{book_id}/cover',
            f'/books/{book_id}/cover/layout', f'/books/{book_id}/preview',
            f'/chapters/{chapter_id}', f'/blocks/{block_id}', f'/blocks/{block_id}/edit']
    for path in gets:
        assert bob.get(path).status_code == 404, path

    posts = [(f'/books/{book_id}/edit', {'title': 'pwn'}),
             (f'/books/{book_id}/complete', {}),
             (f'/books/{book_id}/copy', {}),
             (f'/books/{book_id}/delete', {}),
             (f'/books/{book_id}/cover/front', {'content_text': 'pwn'}),
             (f'/books/{book_id}/chapters/new', {'title': 'pwn'}),
             (f'/chapters/{chapter_id}/rename', {'title': 'pwn'}),
             (f'/chapters/{chapter_id}/move', {'direction': 'up'}),
             (f'/chapters/{chapter_id}/delete', {}),
             (f'/chapters/{chapter_id}/blocks/new', {'content_text': 'pwn'}),
             (f'/blocks/{block_id}/save', {'content_text': 'pwn'}),
             (f'/blocks/{block_id}/move', {'direction': 'up'}),
             (f'/blocks/{block_id}/delete', {})]
    for path, data in posts:
        assert bob.post(path, data=data, headers=HX).status_code == 404, path
    assert bob.delete(f'/blocks/{block_id}/delete', headers=HX).status_code == 404

    book = get_book(book_id)
    assert book.title == 'Secret' and book.status == 'draft'
    assert [c.title for c in book.chapters] == ['Chapter One']
    assert db.session.get(ContentBlock, block_id).content_text == 'Hello **world**'
    assert Book.query.count() == 1
    assert 'Secret' not in bob.get('/').data.decode()


def test_other_users_cannot_fetch_media(alice, bob):
    book_id = create_book(alice)
    resp = alice.post(f'/books/{book_id}/cover/front', data={
        'content_text': 'hi', 'image': (io.BytesIO(PNG_BYTES), 'pic.png')},
        content_type='multipart/form-data')
    assert resp.status_code == 302
    asset = MediaAsset.query.one()
    assert alice.get(f'/media/{asset.asset_id}').status_code == 200
    assert bob.get(f'/media/{asset.asset_id}').status_code == 404


# ---- covers ------------------------------------------------------------------

def test_save_cover_panel(alice):
    book_id = create_book(alice)
    resp = alice.post(f'/books/{book_id}/cover/back', data={
        'content_text': '## Praise', 'background_color': '#112233', 'text_color': '#ffeedd'})
    assert resp.status_code == 302
    cover = get_book(book_id).cover('back')
    assert (cover.content_text, cover.background_color, cover.text_color) == ('## Praise', '#112233', '#ffeedd')


def test_save_cover_panel_htmx_returns_partial(alice):
    book_id = create_book(alice)
    resp = alice.post(f'/books/{book_id}/cover/inside_front', data={'content_text': 'Dedication'}, headers=HX)
    assert resp.status_code == 200
    assert b'cover-panel-inside_front' in resp.data and b'Saved' in resp.data
    assert b'<html' not in resp.data


def test_cover_rejects_bad_color_and_unknown_panel(alice):
    book_id = create_book(alice)
    resp = alice.post(f'/books/{book_id}/cover/front',
                      data={'content_text': 'x', 'background_color': 'red; background:url(x)'}, headers=HX)
    assert b'#rrggbb' in resp.data
    assert get_book(book_id).cover('front').background_color == '#ffffff'
    assert alice.post(f'/books/{book_id}/cover/nope', data={}).status_code == 404


def test_cover_image_upload_validation_and_removal(alice, app):
    book_id = create_book(alice)
    bad_ext = alice.post(f'/books/{book_id}/cover/front', data={
        'image': (io.BytesIO(b'<svg onload=alert(1)>'), 'x.svg')}, content_type='multipart/form-data', headers=HX)
    assert b'PNG, JPG, GIF or WEBP' in bad_ext.data
    fake_png = alice.post(f'/books/{book_id}/cover/front', data={
        'image': (io.BytesIO(b'not really a png'), 'x.png')}, content_type='multipart/form-data', headers=HX)
    assert b'valid image' in fake_png.data
    assert MediaAsset.query.count() == 0

    ok = alice.post(f'/books/{book_id}/cover/front', data={
        'image': (io.BytesIO(PNG_BYTES), '../../evil name.png')}, content_type='multipart/form-data', headers=HX)
    assert ok.status_code == 200
    asset = MediaAsset.query.one()
    assert get_book(book_id).cover('front').asset_id == asset.asset_id
    assert '..' not in asset.file_path and asset.file_path.endswith('.png')
    assert (app.config['UPLOAD_DIR'] / asset.file_path).exists()
    served = alice.get(f'/media/{asset.asset_id}')
    assert served.data == PNG_BYTES and served.mimetype == 'image/png'

    alice.post(f'/books/{book_id}/cover/front', data={'remove_image': '1'}, headers=HX)
    assert get_book(book_id).cover('front').asset_id is None


def test_cover_layout_and_editor_render(alice):
    book_id = create_book(alice, 'Layout Test')
    page = alice.get(f'/books/{book_id}/cover').data.decode()
    for label in ('Front Cover', 'Spine (Binding)', 'Back Cover', 'Inside Front Cover', 'Inside Back Cover'):
        assert label in page
    flat = alice.get(f'/books/{book_id}/cover/layout')
    assert flat.status_code == 200 and b'cover-wrap-spine' in flat.data


# ---- chapters & content ------------------------------------------------------

def test_chapter_and_block_lifecycle(alice):
    book_id = create_book(alice)
    c1 = add_chapter(alice, book_id, 'One')
    c2 = add_chapter(alice, book_id, 'Two')
    assert [c.title for c in get_book(book_id).chapters] == ['One', 'Two']

    alice.post(f'/chapters/{c2}/move', data={'direction': 'up'})
    assert [c.title for c in get_book(book_id).chapters] == ['Two', 'One']

    alice.post(f'/chapters/{c1}/rename', data={'title': 'Uno'})
    assert any(c.title == 'Uno' for c in get_book(book_id).chapters)

    b1 = add_block(alice, c1, 'first')
    b2 = add_block(alice, c1, 'second')
    alice.post(f'/blocks/{b2}/move', data={'direction': 'up'})
    assert [b.content_text for b in db.session.get(Book, book_id).chapters[1].blocks] == ['second', 'first']

    edit = alice.post(f'/blocks/{b1}/save', data={'content_text': 'edited'}, headers=HX)
    assert edit.status_code == 200 and b'edited' in edit.data
    assert db.session.get(ContentBlock, b1).content_text == 'edited'

    assert alice.delete(f'/blocks/{b2}/delete', headers=HX).status_code == 200
    assert db.session.get(ContentBlock, b2) is None

    alice.post(f'/chapters/{c1}/delete')
    assert db.session.get(ContentBlock, b1) is None  # cascades
    assert [c.title for c in get_book(book_id).chapters] == ['Two']


def test_empty_block_rejected(alice):
    book_id = create_book(alice)
    cid = add_chapter(alice, book_id)
    assert alice.post(f'/chapters/{cid}/blocks/new', data={'content_text': '  '}, headers=HX).status_code == 400


def test_preview_sanitises_markdown(alice):
    book_id = create_book(alice, 'Preview Me')
    cid = add_chapter(alice, book_id, 'Ch')
    add_block(alice, cid, '**bold** <script>alert(1)</script> <img src=x onerror=alert(2)> [x](javascript:alert(3))')
    page = alice.get(f'/books/{book_id}/preview').data.decode()
    assert '<strong>bold</strong>' in page
    assert '<script>alert' not in page
    assert 'onerror' not in page
    assert 'javascript:' not in page


def test_titles_are_escaped(alice):
    book_id = create_book(alice, '<script>alert(1)</script>')
    assert '<script>alert(1)</script>' not in alice.get('/').data.decode()
    assert '<script>alert(1)</script>' not in alice.get(f'/books/{book_id}').data.decode()


# ---- completion workflow ------------------------------------------------------

def complete(client, book_id):
    resp = client.post(f'/books/{book_id}/complete')
    assert resp.status_code == 302


def test_mark_completed(alice):
    book_id = create_book(alice)
    complete(alice, book_id)
    book = get_book(book_id)
    assert book.status == 'completed' and book.completed_at is not None
    page = alice.get(f'/books/{book_id}').data.decode()
    assert 'Create Editable Copy' in page
    assert 'Open a copy to edit?' in page            # warning dialog is present
    assert 'Mark as Completed' not in page.split('<div class="modal')[0]  # no complete button for completed books


def test_completed_book_is_read_only_on_the_server(alice):
    book_id = create_book(alice, 'Locked')
    cid = add_chapter(alice, book_id, 'Ch')
    bid = add_block(alice, cid, 'original')
    complete(alice, book_id)

    # Regular form posts are bounced back to the book page and change nothing.
    for path, data in [(f'/books/{book_id}/edit', {'title': 'changed'}),
                       (f'/books/{book_id}/cover/front', {'content_text': 'changed'}),
                       (f'/books/{book_id}/chapters/new', {'title': 'changed'}),
                       (f'/chapters/{cid}/rename', {'title': 'changed'}),
                       (f'/chapters/{cid}/move', {'direction': 'up'}),
                       (f'/chapters/{cid}/delete', {}),
                       (f'/chapters/{cid}/blocks/new', {'content_text': 'changed'}),
                       (f'/blocks/{bid}/save', {'content_text': 'changed'}),
                       (f'/blocks/{bid}/move', {'direction': 'up'}),
                       (f'/blocks/{bid}/delete', {})]:
        resp = alice.post(path, data=data)
        assert resp.status_code == 302 and f'/books/{book_id}' in resp.headers['Location'], path

    # HTMX requests get a 409 with a readable message.
    for path, data in [(f'/books/{book_id}/cover/front', {'content_text': 'changed'}),
                       (f'/blocks/{bid}/save', {'content_text': 'changed'}),
                       (f'/chapters/{cid}/blocks/new', {'content_text': 'changed'})]:
        resp = alice.post(path, data=data, headers=HX)
        assert resp.status_code == 409 and b'read-only' in resp.data, path
    assert alice.delete(f'/blocks/{bid}/delete', headers=HX).status_code == 409
    assert alice.get(f'/books/{book_id}/edit').status_code == 302
    assert alice.get(f'/blocks/{bid}/edit', headers=HX).status_code == 409

    book = get_book(book_id)
    assert book.title == 'Locked'
    assert book.cover('front').content_text != 'changed'
    assert [c.title for c in book.chapters] == ['Ch']
    assert db.session.get(ContentBlock, bid).content_text == 'original'


def test_completed_book_can_still_be_viewed_and_deleted(alice):
    book_id = create_book(alice)
    complete(alice, book_id)
    for path in (f'/books/{book_id}', f'/books/{book_id}/cover', f'/books/{book_id}/preview',
                 f'/books/{book_id}/cover/layout'):
        assert alice.get(path).status_code == 200, path
    # editor shows disabled fields and no save button
    cover_page = alice.get(f'/books/{book_id}/cover').data.decode()
    assert 'read-only' in cover_page and 'Save Front Cover' not in cover_page
    assert alice.post(f'/books/{book_id}/delete').status_code == 302
    assert get_book(book_id) is None


def test_complete_is_idempotent(alice):
    book_id = create_book(alice)
    complete(alice, book_id)
    first = get_book(book_id).completed_at
    complete(alice, book_id)
    assert get_book(book_id).completed_at == first


def test_copy_creates_independent_editable_draft(alice):
    book_id = create_book(alice, 'Original', subtitle='Sub')
    cid = add_chapter(alice, book_id, 'Ch1')
    add_block(alice, cid, 'alpha')
    add_block(alice, cid, 'beta')
    alice.post(f'/books/{book_id}/cover/back', data={
        'content_text': 'blurb', 'background_color': '#abcdef'}, headers=HX)
    complete(alice, book_id)

    resp = alice.post(f'/books/{book_id}/copy')
    assert resp.status_code == 302
    copy_id = int(resp.headers['Location'].rsplit('/', 1)[-1])
    assert copy_id != book_id

    original, copy = get_book(book_id), get_book(copy_id)
    assert original.status == 'completed'
    assert copy.status == 'draft' and copy.completed_at is None
    assert copy.derived_from_book_id == book_id
    assert copy.title == 'Original (copy)' and copy.subtitle == 'Sub'
    assert copy.user_id == original.user_id
    assert sorted(c.panel for c in copy.covers) == sorted(COVER_PANEL_KEYS)
    assert copy.cover('back').content_text == 'blurb' and copy.cover('back').background_color == '#abcdef'
    assert [c.title for c in copy.chapters] == ['Ch1']
    assert [b.content_text for b in copy.chapters[0].blocks] == ['alpha', 'beta']
    # deep copy: different rows
    assert copy.chapters[0].chapter_id != original.chapters[0].chapter_id
    assert {b.block_id for b in copy.chapters[0].blocks}.isdisjoint({b.block_id for b in original.chapters[0].blocks})

    # the copy is editable and editing it leaves the original alone
    assert alice.post(f'/books/{copy_id}/edit', data={'title': 'Second Edition'}).status_code == 302
    new_block = copy.chapters[0].blocks[0].block_id
    assert alice.post(f'/blocks/{new_block}/save', data={'content_text': 'changed'}, headers=HX).status_code == 200
    assert get_book(copy_id).title == 'Second Edition'
    assert get_book(book_id).title == 'Original'
    assert [b.content_text for b in get_book(book_id).chapters[0].blocks] == ['alpha', 'beta']
    assert get_book(book_id).status == 'completed'
    assert 'Created as a copy of' in alice.get(f'/books/{copy_id}').data.decode()


# ---- admin-only settings ------------------------------------------------------

def test_database_settings_admin_only(alice, bob):
    assert alice.get('/settings/database').status_code == 200   # first user is admin
    assert bob.get('/settings/database').status_code == 404
    assert bob.post('/settings/database/test', json={'database': 'x', 'user': 'y'}).status_code == 404
    assert b'Database' not in bob.get('/').data.split(b'navbar-nav ms-auto')[1].split(b'navbar-text')[0]


def test_database_settings_does_not_echo_password(alice, app, tmp_path, monkeypatch):
    import config
    import settings_routes
    cfg = tmp_path / 'db_config.json'
    monkeypatch.setattr(config, 'DB_CONFIG_FILE', cfg)
    alice.post('/settings/database', data={'host': 'h', 'port': '5432', 'database': 'd',
                                           'user': 'u', 'password': 's3cret-value'})
    assert cfg.exists() and has_mode(cfg, 0o600)
    page = alice.get('/settings/database').data.decode()
    assert 's3cret-value' not in page
    # blank password on re-save keeps the stored one
    alice.post('/settings/database', data={'host': 'h2', 'port': '5432', 'database': 'd', 'user': 'u', 'password': ''})
    import json
    assert json.loads(cfg.read_text())['password'] == 's3cret-value'
