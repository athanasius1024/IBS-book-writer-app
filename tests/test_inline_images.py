"""Pictures placed inside chapter text, with cropping and resizing (Part B)."""
import io
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from bookdoc import BookDoc, text_html
from bookfactory import make_asset, make_book, make_user
from conftest import create_book, get_book
from epub import build_epub
from imagespec import format_crop, parse_align, parse_crop, parse_width
from imaging import (derive, finalize_inline_images, inline_usage_counts, read_image, remove_derivative_files,
                     resolve_export)
from layout import get_settings
from markup import render_markdown
from models import Chapter, ContentBlock, MediaAsset, MediaDerivative, User, db
from render import MediaFetcher, clear_cache, get_layout

NO_HYPHEN = {'hyphenate': False}


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def picture(width=100, height=80, fmt='PNG'):
    """Left half red, right half blue, so a crop can be told apart by its colours."""
    image = Image.new('RGB', (width, height), (255, 0, 0))
    image.paste((0, 0, 255), (width // 2, 0, width, height))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def stored_size(app, derivative):
    return Image.open(Path(app.config['UPLOAD_DIR']) / derivative.file_path).size


def text_book(user, body, **kwargs):
    book, _ = make_book(user, chapters=1, paragraphs=1, settings=NO_HYPHEN, **kwargs)
    chapter = book.chapters[0]
    chapter.blocks[0].content_text = body
    db.session.flush()
    return book, chapter.blocks[0]


# ---- the reference syntax --------------------------------------------------------------------

def test_parse_crop_accepts_good_values_and_rejects_bad_ones():
    assert parse_crop('0.1,0.2,0.5,0.5') == (1000, 2000, 5000, 5000)
    assert parse_crop(' 0 , 0 , 0.5 , 1 ') == (0, 0, 5000, 10000)
    assert parse_crop('0.5,0.5,0.9,0.9') == (5000, 5000, 5000, 5000)      # spills over: trimmed to the edge
    for bad in (None, '', 'abc', '0,0,1,1', '1.5,0,1,1', '-0.1,0,0.5,0.5', '0.1,0.1,0.001,0.5', '0.1,0.2,0.5',
                '0.1,0.2,0.5,0.5,0.1', '0.999,0,0.5,0.5', '0,0,0.5,NaN', '0,0,1e-1,0.5'):
        assert parse_crop(bad) is None, bad


def test_format_crop_round_trips():
    for spec in ((1000, 2000, 5000, 5000), (0, 0, 5000, 10000), (3333, 1250, 6667, 8750)):
        assert parse_crop(format_crop(spec)) == spec
    assert format_crop((1000, 2000, 5000, 5000)) == '0.1,0.2,0.5,0.5'


def test_parse_width_and_align():
    assert [parse_width(v) for v in ('10', '60', '100', ' 75 ')] == [10, 60, 100, 75]
    assert [parse_width(v) for v in (None, '', '9', '101', '5x', '-5', '1000', '6.5')] == [None] * 8
    assert parse_align('img-left') == 'left' and parse_align('foo img-right') == 'right'
    assert parse_align('img-bogus') == 'center' and parse_align(None) == 'center'


# ---- the sanitiser -----------------------------------------------------------------------------

def test_images_are_only_kept_when_asked_for_and_only_from_the_library():
    plain = str(render_markdown('![x](image:5)\n\n<img src="ibs-media://5">'))
    assert '<img' not in plain                                            # default: still stripped
    html = str(render_markdown('![A cat](image:12 "The caption"){: data-crop="0.1,0.2,0.5,0.5" data-w="60" .img-left}',
                               images=True))
    assert 'src="ibs-media://12"' in html and 'alt="A cat"' in html and 'title="The caption"' in html
    assert 'data-crop="0.1,0.2,0.5,0.5"' in html and 'data-w="60"' in html and 'class="img-left"' in html


@pytest.mark.parametrize('markdown', [
    '![x](http://example.com/a.png)',
    '![x](https://example.com/a.png)',
    '![x](/media/5)',
    '![x](file:///etc/passwd)',
    '![x](javascript:alert(1))',
    '![x](data:image/png;base64,AAAA)',
    '![x](ibs-media://abc)',
    '![x](image:abc)',
    '<img src="http://evil.example/x.png">',
    '<img src="x" onerror="alert(1)">',
    '<img src="ibs-media://5" onerror="alert(1)">',
    '<img src="ibs-media://5/../../etc">',
])
def test_pictures_from_anywhere_else_never_survive(markdown):
    html = str(render_markdown(markdown, images=True))
    assert 'onerror' not in html and 'http://' not in html and 'https://' not in html
    assert 'javascript' not in html and 'data:' not in html
    # whatever is left either has no src at all, or a media-library src
    for tag in re.findall(r'<img[^>]*>', html):
        assert re.search(r'src="ibs-media://\d+"', tag) or 'src=' not in tag, tag


def test_bad_crop_width_and_class_values_are_dropped_not_trusted():
    html = str(render_markdown('![x](image:5){: data-crop="9,9,9,9" data-w="500" .btn .img-left onclick="x()" style="a:b"}',
                               images=True))
    assert 'data-crop' not in html and 'data-w' not in html and 'onclick' not in html and 'style' not in html
    assert 'class=' not in html                                           # one bad class voids the attribute


def test_links_cannot_point_into_the_media_library():
    html = str(render_markdown('[click](ibs-media://5) and [fine](https://example.com)', images=True))
    assert 'ibs-media' not in html and 'href="https://example.com"' in html


def test_scripts_and_event_handlers_are_stripped_with_images_on():
    html = str(render_markdown('<script>alert(1)</script><p onclick="x()">hi</p>', images=True))
    assert '<script' not in html and 'onclick' not in html and 'hi' in html


# ---- derivatives (the cropped / resized copies) ----------------------------------------------

def test_crop_makes_a_copy_of_exactly_that_part(app):
    user = make_user()
    asset = make_asset(app, user, 'p.png', picture(100, 80))
    left_half = derive(asset, parse_crop('0,0,0.5,1'))
    assert stored_size(app, left_half) == (50, 80) and left_half.mime_type == 'image/png'
    pixels = Image.open(Path(app.config['UPLOAD_DIR']) / left_half.file_path).convert('RGB')
    assert pixels.getpixel((10, 10)) == (255, 0, 0) and pixels.getpixel((49, 79)) == (255, 0, 0)   # all red
    right_half = derive(asset, parse_crop('0.5,0,0.5,1'))
    pixels = Image.open(Path(app.config['UPLOAD_DIR']) / right_half.file_path).convert('RGB')
    assert pixels.getpixel((10, 10)) == (0, 0, 255)
    assert left_half.derivative_id != right_half.derivative_id
    # the original was not touched
    assert Image.open(Path(app.config['UPLOAD_DIR']) / asset.file_path).size == (100, 80)


def test_the_same_crop_is_made_once_and_reused(app):
    user = make_user()
    asset = make_asset(app, user, 'p.png', picture())
    first = derive(asset, parse_crop('0.1,0.1,0.5,0.5'))
    again = derive(asset, parse_crop('0.1,0.1,0.5,0.5'))
    assert first.derivative_id == again.derivative_id
    assert MediaDerivative.query.filter_by(asset_id=asset.asset_id).count() == 1


def test_an_uncropped_small_picture_is_used_as_it_is(app):
    user = make_user()
    asset = make_asset(app, user, 'p.png', picture())
    assert derive(asset, None) is None
    assert resolve_export(asset.asset_id, None, user.user_id) == f'ibs-media://{asset.asset_id}'


def test_a_very_large_picture_is_downsized_but_never_upscaled(app):
    user = make_user()
    big = make_asset(app, user, 'big.png', picture(3000, 1500))
    small_copy = derive(big, None)
    assert small_copy is not None and stored_size(app, small_copy) == (2000, 1000)
    cropped = derive(big, parse_crop('0,0,0.25,0.5'))                     # 750 x 750 px region
    assert stored_size(app, cropped) == (750, 750)                        # smaller than the limit: not enlarged
    tiny = make_asset(app, user, 'tiny.png', picture(20, 10))
    assert stored_size(app, derive(tiny, parse_crop('0,0,0.5,0.5'))) == (10, 5)


def test_jpeg_stays_jpeg_and_gif_becomes_png(app):
    user = make_user()
    jpeg = make_asset(app, user, 'p.jpg', picture(100, 80, 'JPEG'))
    jpeg.mime_type = 'image/jpeg'
    gif = make_asset(app, user, 'p.gif', picture(100, 80, 'GIF'))
    gif.mime_type = 'image/gif'
    assert derive(jpeg, parse_crop('0,0,0.5,0.5')).mime_type == 'image/jpeg'
    assert derive(gif, parse_crop('0,0,0.5,0.5')).mime_type == 'image/png'


def test_crop_follows_the_exif_orientation_the_author_sees(app):
    """A phone photo stored sideways (EXIF 6) is cropped as it is displayed, not as it is stored."""
    user = make_user()
    image = Image.new('RGB', (100, 40), (255, 0, 0))                      # stored 100 x 40 ...
    exif = Image.Exif()
    exif[0x0112] = 6                                                      # ... displayed rotated: 40 x 100
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', exif=exif)
    asset = make_asset(app, user, 'rot.jpg', buffer.getvalue())
    asset.mime_type = 'image/jpeg'
    cropped = derive(asset, parse_crop('0,0,1,0.5'))
    assert stored_size(app, cropped) == (40, 50)                          # half of the 100 px displayed height


def test_unreadable_missing_or_oversized_pictures_give_no_derivative(app):
    user = make_user()
    broken = make_asset(app, user, 'broken.png', b'this is not a picture')
    assert derive(broken, parse_crop('0,0,0.5,0.5')) is None
    gone = make_asset(app, user, 'gone.png', picture())
    (Path(app.config['UPLOAD_DIR']) / gone.file_path).unlink()
    assert derive(gone, parse_crop('0,0,0.5,0.5')) is None
    escaped = make_asset(app, user, 'x.png', picture())
    escaped.file_path = '../../etc/passwd'
    assert derive(escaped, parse_crop('0,0,0.5,0.5')) is None


def test_other_users_pictures_cannot_be_derived_or_read(app):
    owner, other = make_user('owner'), make_user('other')
    asset = make_asset(app, owner, 'mine.png', picture())
    assert resolve_export(asset.asset_id, parse_crop('0,0,0.5,0.5'), other.user_id) is None
    derivative = derive(asset, parse_crop('0,0,0.5,0.5'))
    assert read_image(f'ibs-derived://{derivative.derivative_id}', other.user_id) is None
    assert read_image(f'ibs-media://{asset.asset_id}', other.user_id) is None
    data, mime = read_image(f'ibs-derived://{derivative.derivative_id}', owner.user_id)
    assert mime == 'image/png' and data[:4] == b'\x89PNG'
    assert read_image('http://example.com/x.png', owner.user_id) is None
    assert read_image('ibs-derived://nope', owner.user_id) is None


def test_removing_an_asset_removes_its_cached_copies(app):
    user = make_user()
    asset = make_asset(app, user, 'p.png', picture())
    derivative = derive(asset, parse_crop('0,0,0.5,0.5'))
    path = Path(app.config['UPLOAD_DIR']) / derivative.file_path
    assert path.is_file()
    remove_derivative_files(asset)
    db.session.delete(asset)
    db.session.commit()
    assert not path.exists() and MediaDerivative.query.count() == 0


# ---- finishing the HTML ----------------------------------------------------------------------------

def finish(markdown, resolver=lambda asset_id, crop: f'ibs-media://{asset_id}'):
    return finalize_inline_images(str(render_markdown(markdown, images=True)), resolver)


def test_a_picture_on_its_own_line_becomes_a_figure_with_a_caption():
    html = finish('![Sunset over water](image:7 "A <b>quiet</b> evening"){: data-w="60" .img-right}')
    assert html.startswith('<figure class="inline-figure img-right" style="width: 60%">')
    assert '<img src="ibs-media://7" alt="Sunset over water"/>' in html
    assert '<figcaption>A &lt;b&gt;quiet&lt;/b&gt; evening</figcaption>' in html       # caption text is escaped
    assert '<p>' not in html                                              # no <figure> inside a <p>


def test_a_picture_inside_a_sentence_stays_inline():
    html = finish('Look at ![the dot](image:3){: data-w="20"} here.')
    assert html == '<p>Look at <img class="inline-img" src="ibs-media://3" alt="the dot" style="width: 20%"/> here.</p>'


def test_a_figure_without_a_caption_has_no_figcaption_and_the_alt_defaults_to_the_caption():
    assert '<figcaption' not in finish('![Just a description](image:7)')
    html = finish('![](image:7 "Only a caption")')
    assert 'alt="Only a caption"' in html and '<figcaption>Only a caption</figcaption>' in html


def test_unavailable_pictures_leave_a_note_not_a_broken_image():
    html = finish('![x](image:99)', resolver=lambda asset_id, crop: None)
    assert '[image no longer available]' in html and '<img' not in html
    assert '[image no longer available]' in finish('a ![x](image:99) b', resolver=lambda a, c: None)


def test_the_resolver_receives_the_parsed_crop():
    seen = []
    finish('![x](image:7){: data-crop="0.25,0.25,0.5,0.5"}', resolver=lambda a, c: seen.append((a, c)) or 'x://y')
    assert seen == [(7, (2500, 2500, 5000, 5000))]


def test_text_html_points_cropped_pictures_at_a_derivative_of_the_owners_own_file(app):
    user, other = make_user('me'), make_user('them')
    mine = make_asset(app, user, 'mine.png', picture())
    theirs = make_asset(app, other, 'theirs.png', picture())
    book, block = text_book(user, f'![a](image:{mine.asset_id}){{: data-crop="0,0,0.5,1"}}\n\n'
                                  f'![b](image:{mine.asset_id})\n\n![c](image:{theirs.asset_id})')
    html = text_html(block.content_text, user.user_id)
    assert re.search(r'src="ibs-derived://\d+" alt="a"', html)            # cropped: a derivative
    assert f'src="ibs-media://{mine.asset_id}" alt="b"' in html            # uncropped and small: the original
    assert f'image:{theirs.asset_id}' not in html and 'theirs' not in html
    assert html.count('[image no longer available]') == 1                  # someone else's picture: refused


# ---- exports --------------------------------------------------------------------------------------------------

@pytest.fixture()
def book_with_picture(app):
    user = make_user()
    asset = make_asset(app, user, 'two.png', picture(100, 80))
    body = (f'Before the picture. {"Words " * 20}\n\n'
            f'![Both halves](image:{asset.asset_id} "The left half only"){{: data-crop="0,0,0.5,1" data-w="50"}}\n\n'
            f'After the picture.')
    book, block = text_book(user, body)
    return book, asset, user


def test_pdf_embeds_the_cropped_picture_and_shows_the_caption(book_with_picture):
    book, asset, _ = book_with_picture
    result = get_layout(book)
    reader = PdfReader(io.BytesIO(result.pdf))
    # WeasyPrint shares one resource table between pages, so every page lists the same picture: count it once.
    found = list({image.name: image for page in reader.pages for image in page.images}.values())
    assert len(found) == 1
    picture_in_pdf = found[0].image.convert('RGB')
    assert picture_in_pdf.size == (50, 80)                                # the crop, not the whole 100 x 80
    assert picture_in_pdf.getpixel((25, 40)) == (255, 0, 0)               # only the red half
    text = ' '.join((page.extract_text() or '') for page in reader.pages)
    assert 'The left half only' in text


def test_epub_packages_the_cropped_copy_and_passes_validation(book_with_picture, tmp_path):
    book, asset, _ = book_with_picture
    data = build_epub(book, get_layout(book))
    archive = zipfile.ZipFile(io.BytesIO(data))
    crops = [n for n in archive.namelist() if n.startswith('OEBPS/images/crop-')]
    assert len(crops) == 1 and not any(n == f'OEBPS/images/img-{asset.asset_id}.png' for n in archive.namelist())
    assert Image.open(io.BytesIO(archive.read(crops[0]))).size == (50, 80)
    chapter = archive.read('OEBPS/text/chapter-001.xhtml').decode()
    assert 'ibs-derived' not in chapter and 'ibs-media' not in chapter
    assert re.search(r'<img src="\.\./images/crop-\d+\.png" alt="Both halves"/>', chapter)
    assert 'style="width: 50%"' in chapter and '<figcaption>The left half only</figcaption>' in chapter
    package = ET.fromstring(archive.read('OEBPS/content.opf'))
    hrefs = [i.get('href') for i in package.find('{http://www.idpf.org/2007/opf}manifest')]
    assert crops[0].replace('OEBPS/', '') in hrefs
    if shutil.which('java'):
        from epubcheck import EpubCheck
        path = tmp_path / 'inline.epub'
        path.write_bytes(data)
        result = EpubCheck(str(path))
        problems = [m for m in result.messages if m.level in ('ERROR', 'WARNING', 'FATAL')]
        assert not problems, '\n'.join(f'{m.level} {m.id} {m.location}: {m.message}' for m in problems)


def test_the_pdf_fetcher_serves_only_the_owners_derivatives(app):
    owner, other = make_user('owner'), make_user('other')
    asset = make_asset(app, owner, 'p.png', picture())
    derivative = derive(asset, parse_crop('0,0,0.5,0.5'))
    mine = MediaFetcher(owner.user_id, app.config['UPLOAD_DIR'])
    response = mine.fetch(f'ibs-derived://{derivative.derivative_id}')
    assert response.headers['Content-Type'] == 'image/png'
    theirs = MediaFetcher(other.user_id, app.config['UPLOAD_DIR'])
    for bad in (f'ibs-derived://{derivative.derivative_id}', 'ibs-derived://x', 'ibs-derived://9999'):
        with pytest.raises(ValueError):
            theirs.fetch(bad)


def test_glossary_matching_leaves_alt_text_alone(app):
    user = make_user()
    asset = make_asset(app, user, 'q.png', picture())
    book, block = text_book(user, f'The Quokka sat.\n\n![A Quokka at rest](image:{asset.asset_id} "Our Quokka")',
                            terms=[('Quokka', 'A small marsupial')])
    doc = BookDoc(book, get_settings(book))
    html = doc.chapters[0]['html']
    assert 'alt="A Quokka at rest"' in html and '<span class="occ"' in html
    ET.fromstring(f'<div>{html}</div>')                                   # still well-formed (no markup inside an attribute)
    assert re.search(r'<figcaption>Our <(a|span)[^>]*>Quokka</(a|span)></figcaption>', html)


# ---- routes ---------------------------------------------------------------------------------------------------------

def alice_user():
    return User.query.filter_by(username_key='alice').first()


def test_crop_route_serves_the_cropped_copy_to_its_owner_only(alice, bob, app):
    asset = make_asset(app, alice_user(), 'p.png', picture(100, 80))
    resp = alice.get(f'/media/{asset.asset_id}/crop?c=0,0,0.5,1')
    assert resp.status_code == 200 and resp.mimetype == 'image/png'
    assert Image.open(io.BytesIO(resp.data)).size == (50, 80)
    assert bob.get(f'/media/{asset.asset_id}/crop?c=0,0,0.5,1').status_code == 404
    again = alice.get(f'/media/{asset.asset_id}/crop?c=0,0,0.5,1')
    assert again.data == resp.data and MediaDerivative.query.count() == 1


def test_crop_route_without_a_usable_crop_shows_the_original(alice, app):
    asset = make_asset(app, alice_user(), 'p.png', picture(100, 80))
    for query in ('', '?c=garbage', '?c=0,0,1,1', '?c=5,5,5,5'):
        resp = alice.get(f'/media/{asset.asset_id}/crop{query}')
        assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/media/{asset.asset_id}'), query
    assert alice.get('/media/99999/crop?c=0,0,0.5,0.5').status_code == 404


def test_library_json_lists_only_my_pictures(alice, bob, app):
    mine = make_asset(app, alice_user(), 'mine.png', picture())
    bob_user = User.query.filter_by(username_key='bob').first()
    make_asset(app, bob_user, 'bobs.png', picture())
    data = alice.get('/media/library.json').get_json()
    assert [a['id'] for a in data['assets']] == [mine.asset_id]
    assert data['assets'][0]['url'] == f'/media/{mine.asset_id}' and data['assets'][0]['name'] == 'mine.png'


def test_library_json_requires_login(client):
    assert client.get('/media/library.json').status_code == 302
    assert client.post('/media/upload.json').status_code == 302


def test_upload_json_stores_pictures_and_reports_problems(alice, app):
    good = (io.BytesIO(picture()), 'new.png')
    bad = (io.BytesIO(b'GIF89a-not-really-a-png'), 'fake.png')
    resp = alice.post('/media/upload.json', data={'image': [good, bad]}, content_type='multipart/form-data')
    body = resp.get_json()
    assert resp.status_code == 200 and len(body['assets']) == 1 and len(body['errors']) == 1
    assert 'fake.png' in body['errors'][0]
    assert MediaAsset.query.filter_by(user_id=alice_user().user_id, asset_name='new.png').count() == 1
    empty = alice.post('/media/upload.json', data={}, content_type='multipart/form-data')
    assert empty.status_code == 400 and empty.get_json()['errors']


def test_chapter_page_has_the_insert_image_dialog_unless_the_book_is_completed(alice, app):
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter_id = get_book(book_id).chapters[0].chapter_id
    page = alice.get(f'/chapters/{chapter_id}').data.decode()
    assert 'data-insert-image' in page and 'id="imageModal"' in page and 'js/images.js' in page
    alice.post(f'/books/{book_id}/complete')
    locked = alice.get(f'/chapters/{chapter_id}').data.decode()
    assert 'id="imageModal"' not in locked and 'js/images.js' not in locked


def add_text_block(client, chapter_id, text):
    resp = client.post(f'/chapters/{chapter_id}/blocks/new', data={'block_type': 'text', 'content_text': text})
    assert resp.status_code == 200
    return resp


def test_the_web_page_shows_pictures_through_owner_scoped_urls(alice, app):
    asset = make_asset(app, alice_user(), 'p.png', picture(100, 80))
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter_id = get_book(book_id).chapters[0].chapter_id
    resp = add_text_block(alice, chapter_id,
                          f'![Whole](image:{asset.asset_id} "Plain"){{: .img-left}}\n\n'
                          f'![Part](image:{asset.asset_id}){{: data-crop="0,0,0.5,1" data-w="40"}}')
    html = resp.data.decode()
    assert f'src="/media/{asset.asset_id}"' in html
    assert f'src="/media/{asset.asset_id}/crop?c=0,0,0.5,1"' in html
    assert 'class="inline-figure img-left"' in html and 'style="width: 40%"' in html and '<figcaption>Plain</figcaption>' in html
    assert 'ibs-media' not in html


def test_a_picture_used_in_text_cannot_be_deleted_until_it_is_removed(alice, app):
    asset = make_asset(app, alice_user(), 'p.png', picture())
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter = get_book(book_id).chapters[0]
    add_text_block(alice, chapter.chapter_id, f'Words ![x](image:{asset.asset_id}) more')
    library = alice.get('/media').data.decode()
    assert 'Used: 0 covers, 1 block' in library and 'In use' in library
    refused = alice.post(f'/media/{asset.asset_id}/delete', follow_redirects=True)
    assert b'still used in 1 place' in refused.data
    assert db.session.get(MediaAsset, asset.asset_id) is not None
    assert inline_usage_counts(alice_user().user_id)[asset.asset_id] == 1
    block = get_book(book_id).chapters[0].blocks[0]
    alice.post(f'/blocks/{block.block_id}/delete')
    assert inline_usage_counts(alice_user().user_id)[asset.asset_id] == 0
    done = alice.post(f'/media/{asset.asset_id}/delete', follow_redirects=True)
    assert b'Deleted' in done.data and db.session.get(MediaAsset, asset.asset_id) is None


def test_deleting_a_picture_also_removes_its_cached_copies_from_disk(alice, app):
    asset = make_asset(app, alice_user(), 'p.png', picture())
    derivative = derive(asset, parse_crop('0,0,0.5,0.5'))
    path = Path(app.config['UPLOAD_DIR']) / derivative.file_path
    assert path.is_file()
    alice.post(f'/media/{asset.asset_id}/delete')
    assert not path.exists() and MediaDerivative.query.count() == 0


def test_an_inline_reference_to_another_users_picture_is_never_shown_or_counted(alice, bob, app):
    theirs = make_asset(app, alice_user(), 'alice.png', picture())
    book_id = create_book(bob)
    bob.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    chapter_id = get_book(book_id).chapters[0].chapter_id
    resp = add_text_block(bob, chapter_id, f'![sneaky](image:{theirs.asset_id})')
    assert bob.get(f'/media/{theirs.asset_id}').status_code == 404       # the web URL itself is refused
    assert inline_usage_counts(alice_user().user_id)[theirs.asset_id] == 0   # and it does not lock alice's picture


def test_editable_copy_keeps_inline_references_and_they_still_protect_the_picture(alice, app):
    asset = make_asset(app, alice_user(), 'p.png', picture())
    book_id = create_book(alice)
    alice.post(f'/books/{book_id}/chapters/new', data={'title': 'One'})
    add_text_block(alice, get_book(book_id).chapters[0].chapter_id, f'![x](image:{asset.asset_id}){{: data-w="30"}}')
    resp = alice.post(f'/books/{book_id}/copy')
    copy_id = int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])
    copied = get_book(copy_id).chapters[0].blocks[0].content_text
    assert f'image:{asset.asset_id}' in copied and 'data-w="30"' in copied
    assert inline_usage_counts(alice_user().user_id)[asset.asset_id] == 2
