"""Stored rendered books: generate, keep, replace, delete, download, view, print, zip, save to a folder."""
import hashlib
import io
import re
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from bookfactory import add_author, make_asset, make_book, make_user
from conftest import create_book, get_book, make_app
from models import MAX_RENDERS_PER_FORMAT, ContentBlock, RenderedBook, User, db
from render import clear_cache

FORMATS = ('pdf', 'epub', 'html', 'odt')


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def alice_user():
    return User.query.filter_by(username_key='alice').first()


def small_book(alice, chapters=2):
    """A real book owned by alice, built through the web forms and filled with a few paragraphs."""
    book_id = create_book(alice)
    for number in range(1, chapters + 1):
        alice.post(f'/books/{book_id}/chapters/new', data={'title': f'Chapter {number}'})
    for chapter in get_book(book_id).chapters:
        alice.post(f'/chapters/{chapter.chapter_id}/blocks/new',
                   data={'block_type': 'text', 'content_text': f'Text of {chapter.title}. ' * 10})
    return book_id


def generate(alice, book_id, *formats, all_formats=False):
    data = {'all': '1'} if all_formats else {'formats': list(formats)}
    return alice.post(f'/books/{book_id}/renders/generate', data=data, follow_redirects=True)


def rows(book_id):
    return RenderedBook.query.filter_by(book_id=book_id).order_by(RenderedBook.render_id).all()


def path_of(app, render):
    return Path(app.config['UPLOAD_DIR']) / render.file_path


# ---- generating ----------------------------------------------------------------------------------------

def test_generate_all_four_formats(alice, app):
    book_id = small_book(alice)
    resp = generate(alice, book_id, all_formats=True)
    assert b'Generated PDF, EPUB, HTML, ODT' in resp.data
    found = {r.format: r for r in rows(book_id)}
    assert set(found) == set(FORMATS)
    for fmt, render in found.items():
        path = path_of(app, render)
        data = path.read_bytes()
        assert path.is_file() and render.file_size == len(data) and render.sha256 == hashlib.sha256(data).hexdigest()
        assert render.user_id == alice_user().user_id and render.book_version == '0.1'
        assert re.fullmatch(rf'renders/{render.user_id}/[0-9a-f]{{32}}\.{fmt}', render.file_path)   # generated name only
        assert render.file_name.endswith(f'.{fmt}') and '/' not in render.file_name
    assert found['pdf'].page_count == len(PdfReader(str(path_of(app, found['pdf']))).pages)
    assert path_of(app, found['pdf']).read_bytes().startswith(b'%PDF')
    assert zipfile.ZipFile(path_of(app, found['epub'])).read('mimetype') == b'application/epub+zip'
    assert path_of(app, found['html']).read_bytes().startswith(b'<!DOCTYPE html>')
    assert zipfile.ZipFile(path_of(app, found['odt'])).read('mimetype') == b'application/vnd.oasis.opendocument.text'
    assert all(r.page_count is None for r in found.values() if r.format != 'pdf')


def test_generate_chosen_formats_only_and_report_nothing_chosen(alice):
    book_id = small_book(alice)
    generate(alice, book_id, 'html', 'odt')
    assert sorted(r.format for r in rows(book_id)) == ['html', 'odt']
    nothing = alice.post(f'/books/{book_id}/renders/generate', data={}, follow_redirects=True)
    assert b'Choose at least one format' in nothing.data and len(rows(book_id)) == 2
    bogus = alice.post(f'/books/{book_id}/renders/generate', data={'formats': ['exe', '../x']}, follow_redirects=True)
    assert b'Choose at least one format' in bogus.data and len(rows(book_id)) == 2


def test_formats_generated_together_share_the_same_stamp_and_date(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, all_formats=True)
    found = {r.format: r for r in rows(book_id)}
    assert len({r.generated_at for r in found.values()}) == 1                    # one moment for the whole batch
    pdf_text = ' '.join(p.extract_text() or '' for p in PdfReader(str(path_of(app, found['pdf']))).pages)
    stamps = set(re.findall(r'Version 0\.1 \u00b7 Generated [A-Z][a-z]+ \d{1,2}, \d{4}', pdf_text))
    assert len(stamps) == 1
    stamp = stamps.pop()
    assert stamp in zipfile.ZipFile(path_of(app, found['epub'])).read('OEBPS/text/contents.xhtml').decode()
    assert stamp in path_of(app, found['html']).read_text(encoding='utf-8')
    assert stamp in zipfile.ZipFile(path_of(app, found['odt'])).read('content.xml').decode()


def test_the_stamp_shows_the_books_current_version(alice, app):
    book_id = small_book(alice)
    alice.post(f'/books/{book_id}/edit', data={'title': 'Versioned', 'version': '3.2'})
    generate(alice, book_id, 'html')
    render = rows(book_id)[0]
    assert render.book_version == '3.2' and render.file_name == 'Versioned_v3.2.html'
    assert 'Version 3.2 \u00b7 Generated' in path_of(app, render).read_text(encoding='utf-8')


def test_a_completed_book_can_still_be_stored_and_stays_unchanged(alice, app):
    book_id = small_book(alice)
    alice.post(f'/books/{book_id}/complete')
    edited = get_book(book_id).modified_at
    generate(alice, book_id, 'pdf')
    assert len(rows(book_id)) == 1 and get_book(book_id).modified_at == edited and get_book(book_id).is_completed


# ---- out of date, replace, delete ----------------------------------------------------------------------

def test_a_copy_is_current_until_the_book_is_edited(alice):
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    render = rows(book_id)[0]
    assert render.is_outdated is False and b'Current' in alice.get(f'/books/{book_id}/renders').data
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'A late chapter'})
    assert rows(book_id)[0].is_outdated is True
    page = alice.get(f'/books/{book_id}/renders').data
    assert b'Out of date' in page and b'Current' not in page


def test_replace_builds_a_fresh_copy_in_the_same_slot_and_removes_the_old_file(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    render = rows(book_id)[0]
    old_path, old_id, old_when = path_of(app, render), render.render_id, render.generated_at
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'Added later'})
    alice.post(f'/books/{book_id}/edit', data={'title': 'Renamed', 'version': '0.2'})
    time.sleep(0.01)
    resp = alice.post(f'/renders/{old_id}/replace', follow_redirects=True)
    assert b'replaced with a freshly generated version' in resp.data
    after = rows(book_id)
    assert len(after) == 1 and after[0].render_id == old_id                    # same row, not a second copy
    assert after[0].book_version == '0.2' and after[0].file_name == 'Renamed_v0.2.html'
    assert after[0].generated_at >= old_when and after[0].is_outdated is False
    assert not old_path.exists() and path_of(app, after[0]).is_file()          # the old file is gone, the new one there
    assert 'Added later' in path_of(app, after[0]).read_text(encoding='utf-8')


def test_delete_removes_the_row_and_the_file(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'pdf', 'epub')
    first, second = rows(book_id)
    first_path = path_of(app, first)
    alice.post(f'/renders/{first.render_id}/delete')
    assert [r.render_id for r in rows(book_id)] == [second.render_id] and not first_path.exists()
    assert path_of(app, second).is_file()


def test_deleting_the_book_deletes_its_stored_files(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, all_formats=True)
    paths = [path_of(app, r) for r in rows(book_id)]
    assert all(p.is_file() for p in paths)
    alice.post(f'/books/{book_id}/delete')
    assert RenderedBook.query.count() == 0 and not any(p.exists() for p in paths)


def test_a_missing_file_is_reported_and_replace_repairs_it(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'epub')
    render = rows(book_id)[0]
    path_of(app, render).unlink()
    assert b'File missing' in alice.get(f'/books/{book_id}/renders').data
    resp = alice.get(f'/renders/{render.render_id}/download', follow_redirects=True)
    assert b'no longer on disk' in resp.data
    alice.post(f'/renders/{render.render_id}/replace')
    assert path_of(app, rows(book_id)[0]).is_file()


def test_ten_copies_per_format_is_the_limit_but_replace_still_works(alice, app):
    book_id = small_book(alice)
    for _ in range(MAX_RENDERS_PER_FORMAT):
        generate(alice, book_id, 'html')
    assert len(rows(book_id)) == MAX_RENDERS_PER_FORMAT
    over = generate(alice, book_id, 'html')
    assert b'already keep 10 HTML copies' in over.data and len(rows(book_id)) == MAX_RENDERS_PER_FORMAT
    other = generate(alice, book_id, 'odt')                                      # another format is not affected
    assert b'Generated ODT' in other.data and len(rows(book_id)) == MAX_RENDERS_PER_FORMAT + 1
    page = alice.get(f'/books/{book_id}/renders').data.decode()
    assert re.search(r'id="gen-html"[^>]*disabled', page)
    alice.post(f'/renders/{rows(book_id)[0].render_id}/replace')
    assert len(rows(book_id)) == MAX_RENDERS_PER_FORMAT + 1


# ---- download, view, print -------------------------------------------------------------------------------

def test_download_sends_the_file_as_an_attachment_with_the_right_type(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, all_formats=True)
    expected = {'pdf': 'application/pdf', 'epub': 'application/epub+zip', 'html': 'text/html',
                'odt': 'application/vnd.oasis.opendocument.text'}
    for render in rows(book_id):
        resp = alice.get(f'/renders/{render.render_id}/download')
        assert resp.status_code == 200 and resp.mimetype == expected[render.format]
        assert resp.headers['Content-Disposition'].startswith('attachment') and render.file_name in resp.headers['Content-Disposition']
        assert resp.data == path_of(app, render).read_bytes()


def test_view_shows_pdf_inline_and_locks_html_down(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'pdf', 'html', 'epub')
    by = {r.format: r for r in rows(book_id)}
    pdf = alice.get(f'/renders/{by["pdf"].render_id}/view')
    assert pdf.mimetype == 'application/pdf' and pdf.headers['Content-Disposition'].startswith('inline')
    html = alice.get(f'/renders/{by["html"].render_id}/view')
    csp = html.headers['Content-Security-Policy']
    assert html.mimetype == 'text/html' and "default-src 'none'" in csp and csp.rstrip().endswith('sandbox')
    assert 'script-src' not in csp and b'<script' not in html.data               # no script can run in a plain view
    assert alice.get(f'/renders/{by["epub"].render_id}/view').status_code == 404  # only PDF and HTML are viewable


def test_print_opens_the_print_dialog_for_pdf_and_html_only(alice):
    book_id = small_book(alice)
    generate(alice, book_id, all_formats=True)
    by = {r.format: r for r in rows(book_id)}
    page = alice.get(f'/renders/{by["pdf"].render_id}/print')
    text = page.data.decode()
    assert page.status_code == 200 and f'/renders/{by["pdf"].render_id}/view' in text and '.print()' in text
    redirect = alice.get(f'/renders/{by["html"].render_id}/print')
    assert redirect.status_code == 302 and redirect.headers['Location'].endswith(f'/renders/{by["html"].render_id}/view?print=1')
    for fmt in ('epub', 'odt'):
        assert alice.get(f'/renders/{by[fmt].render_id}/print').status_code == 404


def test_html_print_view_allows_only_its_own_nonce_script(alice):
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    render = rows(book_id)[0]
    resp = alice.get(f'/renders/{render.render_id}/view?print=1')
    csp, body = resp.headers['Content-Security-Policy'], resp.data.decode()
    nonce = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
    assert 'allow-scripts' in csp and 'allow-modals' in csp and 'allow-same-origin' not in csp   # opaque origin
    assert body.count('<script') == 1 and f'nonce="{nonce}"' in body and 'window.print()' in body
    again = alice.get(f'/renders/{render.render_id}/view?print=1').headers['Content-Security-Policy']
    assert again != csp                                                        # a new nonce every time


def test_a_script_hidden_in_a_stored_html_file_could_not_run(alice, app):
    """Even if a stored file somehow held a script, the page's policy blocks it (and it has no way in anyway)."""
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    render = rows(book_id)[0]
    path = path_of(app, render)
    path.write_text(path.read_text(encoding='utf-8').replace('</body>', '<script>steal()</script></body>'), encoding='utf-8')
    plain = alice.get(f'/renders/{render.render_id}/view')
    assert 'script-src' not in plain.headers['Content-Security-Policy']        # nothing is allowed to run
    printing = alice.get(f'/renders/{render.render_id}/view?print=1')
    nonce = re.search(r"nonce-([^']+)'", printing.headers['Content-Security-Policy']).group(1)
    scripts = re.findall(r'<script[^>]*>', printing.data.decode())
    assert len(scripts) == 2 and sum(f'nonce="{nonce}"' in s for s in scripts) == 1   # the planted one has no nonce


# ---- selecting several ------------------------------------------------------------------------------------

def test_download_selected_as_one_zip(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'pdf', 'html', 'html')                               # two HTML copies of the same version
    chosen = rows(book_id)
    resp = alice.post(f'/books/{book_id}/renders/selected', data={'action': 'zip', 'ids': [r.render_id for r in chosen]})
    assert resp.status_code == 200 and resp.mimetype == 'application/zip'
    assert resp.headers['Content-Disposition'].startswith('attachment') and '.zip' in resp.headers['Content-Disposition']
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    names = archive.namelist()
    assert len(names) == 3 and len(set(names)) == 3                               # same-named copies do not clobber each other
    for render in chosen:
        assert any(archive.read(n) == path_of(app, render).read_bytes() for n in names)


def test_delete_selected_removes_rows_and_files(alice, app):
    book_id = small_book(alice)
    generate(alice, book_id, all_formats=True)
    found = rows(book_id)
    doomed, kept = found[:3], found[3]
    paths = [path_of(app, r) for r in doomed]
    resp = alice.post(f'/books/{book_id}/renders/selected', data={'action': 'delete', 'ids': [r.render_id for r in doomed]},
                      follow_redirects=True)
    assert b'Deleted 3 stored copies' in resp.data
    assert [r.render_id for r in rows(book_id)] == [kept.render_id] and not any(p.exists() for p in paths)


def test_selection_errors_are_gentle(alice):
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    none = alice.post(f'/books/{book_id}/renders/selected', data={'action': 'zip'}, follow_redirects=True)
    assert b'Tick at least one stored copy' in none.data
    junk = alice.post(f'/books/{book_id}/renders/selected', data={'action': 'zip', 'ids': ['abc', '-1', '99999']},
                      follow_redirects=True)
    assert b'Tick at least one stored copy' in junk.data
    assert alice.post(f'/books/{book_id}/renders/selected',
                      data={'action': 'format-disk', 'ids': [rows(book_id)[0].render_id]}).status_code == 400


# ---- ownership --------------------------------------------------------------------------------------------

def test_other_users_get_404_everywhere_and_cannot_change_anything(alice, bob, app):
    book_id = small_book(alice)
    generate(alice, book_id, 'pdf', 'html')
    render = rows(book_id)[0]
    assert bob.get(f'/books/{book_id}/renders').status_code == 404
    assert bob.post(f'/books/{book_id}/renders/generate', data={'all': '1'}).status_code == 404
    for method, path in [('get', f'/renders/{render.render_id}/download'), ('get', f'/renders/{render.render_id}/view'),
                         ('get', f'/renders/{render.render_id}/print'), ('post', f'/renders/{render.render_id}/replace'),
                         ('post', f'/renders/{render.render_id}/delete'), ('post', f'/renders/{render.render_id}/save-to-folder')]:
        assert getattr(bob, method)(path).status_code == 404, path
    assert bob.post(f'/books/{book_id}/renders/selected', data={'action': 'delete', 'ids': [render.render_id]}).status_code == 404
    assert len(rows(book_id)) == 2 and path_of(app, render).is_file()


def test_ids_from_another_book_in_a_selection_are_ignored(alice, app):
    first, second = small_book(alice), small_book(alice)
    generate(alice, first, 'html')
    generate(alice, second, 'html')
    foreign = rows(second)[0]
    resp = alice.post(f'/books/{first}/renders/selected', data={'action': 'delete', 'ids': [foreign.render_id]},
                      follow_redirects=True)
    assert b'Tick at least one stored copy' in resp.data and len(rows(second)) == 1 and path_of(app, foreign).is_file()


def test_visitors_are_sent_to_the_login_page(client):
    for path in ('/books/1/renders', '/renders/1/download', '/renders/1/view', '/renders/1/print'):
        assert client.get(path).status_code == 302
    assert client.post('/books/1/renders/generate', data={'all': '1'}).status_code == 302


def test_a_users_stored_pictures_never_reach_someone_elses_book(alice, bob, app):
    """The pictures inside a stored copy come only from the book owner's own files."""
    theirs = make_asset(app, alice_user(), 'alice.png')
    book_id = create_book(bob)
    bob.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter_id = get_book(book_id).chapters[0].chapter_id
    bob.post(f'/chapters/{chapter_id}/blocks/new', data={'block_type': 'text', 'content_text': f'![x](image:{theirs.asset_id})'})
    generate(bob, book_id, 'html')
    assert 'data:image' not in path_of(app, rows(book_id)[0]).read_text(encoding='utf-8')


# ---- the export folder -----------------------------------------------------------------------------------------

@pytest.fixture()
def export_app(tmp_path):
    return make_app(tmp_path, EXPORT_DIR=str(tmp_path / 'exports'))


def test_the_save_to_folder_buttons_appear_only_when_a_folder_is_configured(alice):
    book_id = small_book(alice)
    generate(alice, book_id, 'html')
    page = alice.get(f'/books/{book_id}/renders').data.decode()
    assert 'save-to-folder' not in page and 'export folder' not in page
    render = rows(book_id)[0]
    assert alice.post(f'/renders/{render.render_id}/save-to-folder').status_code == 404
    assert alice.post(f'/books/{book_id}/renders/selected',
                      data={'action': 'save-to-folder', 'ids': [render.render_id]}).status_code == 404


def test_save_to_folder_copies_the_file_and_never_overwrites(app, tmp_path):
    app.config['EXPORT_DIR'] = str(tmp_path / 'exports')
    from conftest import register
    client = app.test_client()
    assert register(client, 'alice').status_code == 200
    book_id = small_book(client)
    generate(client, book_id, 'html')
    render = rows(book_id)[0]
    page = client.get(f'/books/{book_id}/renders').data.decode()
    assert 'save-to-folder' in page and str(tmp_path / 'exports') in page
    first = client.post(f'/renders/{render.render_id}/save-to-folder', follow_redirects=True)
    assert b'Saved a copy to' in first.data
    folder = tmp_path / 'exports'
    assert [p.name for p in folder.iterdir()] == [render.file_name]
    assert (folder / render.file_name).read_bytes() == path_of(app, render).read_bytes()
    client.post(f'/renders/{render.render_id}/save-to-folder')
    client.post(f'/books/{book_id}/renders/selected', data={'action': 'save-to-folder', 'ids': [render.render_id]})
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 3 and render.file_name in names and all(n.endswith('.html') for n in names)   # -2, -3 added


def test_a_hostile_title_cannot_escape_the_export_folder(app, tmp_path):
    app.config['EXPORT_DIR'] = str(tmp_path / 'exports')
    from conftest import register
    client = app.test_client()
    register(client, 'alice')
    book_id = create_book(client, title='../../../etc/passwd')
    generate(client, book_id, 'html')
    render = rows(book_id)[0]
    assert '/' not in render.file_name and '..' not in render.file_name.replace('.html', '')
    client.post(f'/renders/{render.render_id}/save-to-folder')
    inside = list((tmp_path / 'exports').iterdir())
    assert len(inside) == 1 and inside[0].parent == tmp_path / 'exports'
    assert not (tmp_path / 'etc').exists()


# ---- the page --------------------------------------------------------------------------------------------------

def test_the_page_lists_copies_with_their_details_and_the_book_page_links_to_it(alice):
    book_id = small_book(alice)
    assert b'No stored copies yet' in alice.get(f'/books/{book_id}/renders').data
    generate(alice, book_id, 'pdf', 'odt')
    page = alice.get(f'/books/{book_id}/renders').data.decode()
    assert 'PDF' in page and 'ODT' in page and 'Download as one zip' in page and 'Generate all four' in page
    assert re.search(r'\d+ pp', page)                                              # the PDF page count
    assert 'Print' in page or 'bi-printer' in page
    detail = alice.get(f'/books/{book_id}').data.decode()
    assert f'/books/{book_id}/renders' in detail and 'Stored books' in detail
