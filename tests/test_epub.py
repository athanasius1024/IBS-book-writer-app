import io
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from posixpath import dirname, join, normpath

import pytest

from bookfactory import add_author, add_front_matter, make_asset, make_book, make_user, png_bytes
from epub import build_epub
from models import ContentBlock, db
from render import clear_cache, get_layout

XHTML = '{http://www.w3.org/1999/xhtml}'
OPF = '{http://www.idpf.org/2007/opf}'
NO_HYPHEN = {'hyphenate': False}


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def epub_book(app):
    """A book that exercises everything: cover image, front matter, authors with photo, image block, terms."""
    user = make_user()
    book, tokens = make_book(
        user, chapters=3, paragraphs=8, settings=NO_HYPHEN,
        terms=[('Quokka', 'A small marsupial'), ('fox', 'A clever animal'), ('Committee', 'A group')],
        inject={(1, 2): 'Quokka', (2, 5): 'Quokka', (3, 1): 'quokkas and the Committee'})
    add_front_matter(book)
    photo = make_asset(app, user, 'author.png')
    add_author(book, photo=photo)
    cover_asset = make_asset(app, user, 'cover.png')
    book.cover('front').asset_id = cover_asset.asset_id
    chapter = book.chapters[0]
    chapter.blocks.append(ContentBlock(block_type='image', content_text='A red square', asset_id=photo.asset_id,
                                       sort_order=99))
    chapter.blocks.append(ContentBlock(block_type='table', content_text='a | b',
                                       content_data={'header': True, 'rows': [['Term', 'Meaning'], ['x', 'y']]},
                                       sort_order=100))
    chapter.blocks.append(ContentBlock(block_type='heading', content_text='A <b>heading</b> & more',
                                       content_data={'level': 1}, sort_order=101))
    db.session.flush()
    return book


@pytest.fixture()
def epub_bytes(epub_book):
    return build_epub(epub_book, get_layout(epub_book))


def names(data):
    return zipfile.ZipFile(io.BytesIO(data)).namelist()


def read(data, name):
    return zipfile.ZipFile(io.BytesIO(data)).read(name)


def test_package_structure(epub_bytes):
    archive = zipfile.ZipFile(io.BytesIO(epub_bytes))
    first = archive.infolist()[0]
    assert first.filename == 'mimetype' and first.compress_type == zipfile.ZIP_STORED
    assert archive.read('mimetype') == b'application/epub+zip'
    assert 'META-INF/container.xml' in names(epub_bytes)
    assert b'OEBPS/content.opf' in read(epub_bytes, 'META-INF/container.xml')
    assert archive.testzip() is None


def test_every_xml_file_is_well_formed(epub_bytes):
    for name in names(epub_bytes):
        if name.endswith(('.xhtml', '.opf', '.xml')):
            ET.fromstring(read(epub_bytes, name))


def test_manifest_spine_and_files_agree(epub_bytes):
    package = ET.fromstring(read(epub_bytes, 'OEBPS/content.opf'))
    manifest = {i.get('id'): i for i in package.find(f'{OPF}manifest')}
    ids = [i.get('id') for i in package.find(f'{OPF}manifest')]
    assert len(ids) == len(set(ids))
    for item in manifest.values():
        assert f'OEBPS/{item.get("href")}' in names(epub_bytes), item.get('href')
    for ref in package.find(f'{OPF}spine'):
        assert ref.get('idref') in manifest
    assert sum(1 for i in manifest.values() if i.get('properties') == 'nav') == 1
    assert [r.get('idref') for r in package.find(f'{OPF}spine')][-1] == 'nav'
    # every packaged file other than metadata is declared in the manifest
    declared = {f'OEBPS/{i.get("href")}' for i in manifest.values()}
    for name in names(epub_bytes):
        if name.startswith('OEBPS/') and name != 'OEBPS/content.opf':
            assert name in declared, name


def test_package_metadata(epub_bytes, epub_book):
    package = ET.fromstring(read(epub_bytes, 'OEBPS/content.opf')).find(f'{OPF}metadata')
    text = ET.tostring(package, encoding='unicode')
    assert 'urn:uuid:' in text and '>Test Book<' in text and '>A Subtitle<' in text
    assert '>Ann Author<' in text and '>en<' in text and 'dcterms:modified' in text
    assert re.search(r'dcterms:modified">\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ<', text)
    # identifier is stable between builds of the same book
    again = build_epub(epub_book, get_layout(epub_book))
    assert b'urn:uuid:' in read(again, 'OEBPS/content.opf')
    assert re.search(rb'urn:uuid:[0-9a-f-]+', read(again, 'OEBPS/content.opf')).group() == \
        re.search(rb'urn:uuid:[0-9a-f-]+', read(epub_bytes, 'OEBPS/content.opf')).group()


def test_cover_image_is_declared(epub_bytes):
    package = ET.fromstring(read(epub_bytes, 'OEBPS/content.opf'))
    cover_items = [i for i in package.find(f'{OPF}manifest') if i.get('properties') == 'cover-image']
    assert len(cover_items) == 1 and cover_items[0].get('media-type') == 'image/png'
    assert b'<meta name="cover"' in read(epub_bytes, 'OEBPS/content.opf')


def test_semantic_front_and_back_matter(epub_bytes):
    files = [n for n in names(epub_bytes) if n.startswith('OEBPS/text/')]
    joined = {n: read(epub_bytes, n).decode() for n in files}
    assert any('epub:type="dedication"' in t and 'For my family' in t for t in joined.values())
    assert any('epub:type="epigraph"' in t and 'Tao Teh Ching #78' in t and 'softer than water' in t
               for t in joined.values())
    assert any('epub:type="glossary"' in t for t in joined.values())
    assert any('epub:type="index"' in t for t in joined.values())
    about = joined['OEBPS/text/about.xhtml']
    assert 'Ann writes books.' in about and '<img' in about and 'author.png' not in about  # packaged path, not name


def test_navigation_toc_landmarks_and_page_list(epub_bytes, epub_book):
    nav = ET.fromstring(read(epub_bytes, 'OEBPS/nav.xhtml'))
    navs = {n.get('{http://www.idpf.org/2007/ops}type'): n for n in nav.iter(f'{XHTML}nav')}
    assert set(navs) == {'toc', 'landmarks', 'page-list'}
    toc_titles = [a.text for a in navs['toc'].iter(f'{XHTML}a')]
    assert toc_titles == ['Chapter 1', 'Chapter 2', 'Chapter 3', 'Glossary', 'Index', 'About the Author']
    pages = [int(a.text) for a in navs['page-list'].iter(f'{XHTML}a')]
    result = get_layout(epub_book)
    assert pages == list(range(1, max(result.pages[a] for a in result.pages if a.startswith('b')
                                      or a.startswith('sec-')) + 1))
    # page-list targets exist
    for a in navs['page-list'].iter(f'{XHTML}a'):
        href, fragment = a.get('href').split('#')
        assert f'OEBPS/{href}' in names(epub_bytes)
        assert f'id="{fragment}"' in read(epub_bytes, f'OEBPS/{href}').decode()


def all_links(epub_bytes):
    """(source file, href) for every relative link in the XHTML files."""
    for name in names(epub_bytes):
        if name.endswith('.xhtml'):
            text = read(epub_bytes, name).decode()
            for href in re.findall(r'<a [^>]*href="([^"]+)"', text):
                yield name, href


def test_every_internal_link_resolves(epub_bytes):
    checked = 0
    for source, href in all_links(epub_bytes):
        if href.startswith(('http:', 'https:', 'mailto:')):
            continue
        path, _, fragment = href.partition('#')
        target = normpath(join(dirname(source), path)) if path else source
        assert target in names(epub_bytes), f'{source} -> {href}'
        if fragment:
            assert f'id="{fragment}"' in read(epub_bytes, target).decode(), f'{source} -> {href}'
        checked += 1
    assert checked > 20


def test_glossary_words_link_to_glossary_entries_and_back_to_the_text(epub_bytes, epub_book):
    quokka = next(t for t in epub_book.terms if t.term == 'Quokka')
    chapter1 = read(epub_bytes, 'OEBPS/text/chapter-001.xhtml').decode()
    assert f'href="glossary.xhtml#term-{quokka.term_id}"' in chapter1
    glossary = read(epub_bytes, 'OEBPS/text/glossary.xhtml').decode()
    assert f'id="term-{quokka.term_id}"' in glossary and 'A small marsupial' in glossary
    entry = re.search(rf'id="term-{quokka.term_id}".*?</dd>', glossary, re.S).group()
    assert re.search(r'Pages? .*href="chapter-00[123]\.xhtml#o%d-\d+"' % quokka.term_id, entry)
    index = read(epub_bytes, 'OEBPS/text/index.xhtml').decode()
    assert re.search(r'Quokka</span>, <a class="pg" href="chapter-00\d\.xhtml#o%d-1">' % quokka.term_id, index)


def test_images_are_packaged_and_rewritten(epub_bytes):
    chapter1 = read(epub_bytes, 'OEBPS/text/chapter-001.xhtml').decode()
    assert 'ibs-media://' not in chapter1
    assert re.search(r'<img src="\.\./images/img-\d+\.png" alt="A red square"/>', chapter1)
    assert any(n.startswith('OEBPS/images/') and n.endswith('.png') for n in names(epub_bytes))


def test_content_is_escaped_and_xhtml_clean(epub_bytes):
    chapter1 = read(epub_bytes, 'OEBPS/text/chapter-001.xhtml').decode()
    assert 'A &lt;b&gt;heading&lt;/b&gt; &amp; more' in chapter1
    assert '<script' not in chapter1.lower()
    for name in names(epub_bytes):
        if name.endswith('.xhtml'):
            text = read(epub_bytes, name).decode()
            assert re.search(r'<(br|hr|img)(?![^>]*/>)[^>]*>', text) is None, name   # void tags self-closed
            assert 'ibs-media://' not in text


def test_ids_are_unique_within_each_file(epub_bytes):
    for name in names(epub_bytes):
        if name.endswith('.xhtml'):
            found = re.findall(r'\bid="([^"]+)"', read(epub_bytes, name).decode())
            assert len(found) == len(set(found)), name


def test_webp_images_are_converted_to_png(app):
    from PIL import Image
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2)
    buffer = io.BytesIO()
    Image.new('RGB', (20, 20), 'blue').save(buffer, 'WEBP')
    asset = make_asset(app, user, 'pic.webp', data=buffer.getvalue())
    asset.mime_type = 'image/webp'
    book.chapters[0].blocks.append(ContentBlock(block_type='image', content_text='w', asset_id=asset.asset_id,
                                                sort_order=9))
    db.session.flush()
    data = build_epub(book, get_layout(book))
    assert any(n.endswith('.png') for n in names(data)) and not any(n.endswith('.webp') for n in names(data))
    package = read(data, 'OEBPS/content.opf').decode()
    assert 'image/webp' not in package


def test_missing_images_are_left_out_without_breaking_the_book(app):
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2)
    asset = make_asset(app, user, 'gone.png')
    book.chapters[0].blocks.append(ContentBlock(block_type='image', content_text='lost', asset_id=asset.asset_id,
                                                sort_order=9))
    db.session.flush()
    import os
    os.remove(os.path.join(app.config['UPLOAD_DIR'], asset.file_path))
    data = build_epub(book, get_layout(book))
    chapter = read(data, 'OEBPS/text/chapter-001.xhtml').decode()
    ET.fromstring(chapter.encode())
    assert '<img' not in chapter and 'lost' in chapter


def test_minimal_book_without_extras(app):
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=1,
                        settings={'include_covers': False, 'include_title_page': False})
    book.cover('front').content_text = ''
    data = build_epub(book, get_layout(book))
    nav = read(data, 'OEBPS/nav.xhtml').decode()
    assert 'page-list' in nav and 'Glossary' not in nav and 'Index' not in nav
    for name in names(data):
        if name.endswith(('.xhtml', '.opf')):
            ET.fromstring(read(data, name))


@pytest.mark.skipif(shutil.which('java') is None, reason='EPUBCheck needs Java')
def test_epubcheck_reports_no_errors_or_warnings(epub_bytes, tmp_path):
    from epubcheck import EpubCheck
    path = tmp_path / 'book.epub'
    path.write_bytes(epub_bytes)
    result = EpubCheck(str(path))
    problems = [m for m in result.messages if m.level in ('ERROR', 'WARNING', 'FATAL')]
    assert not problems, '\n'.join(f'{m.level} {m.id} {m.location}: {m.message}' for m in problems)
    assert result.valid


@pytest.mark.skipif(shutil.which('java') is None, reason='EPUBCheck needs Java')
def test_epubcheck_also_accepts_a_minimal_book(app, tmp_path):
    from epubcheck import EpubCheck
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2,
                        settings={'include_covers': False, 'include_title_page': False})
    path = tmp_path / 'min.epub'
    path.write_bytes(build_epub(book, get_layout(book)))
    result = EpubCheck(str(path))
    problems = [m for m in result.messages if m.level in ('ERROR', 'WARNING', 'FATAL')]
    assert not problems, '\n'.join(f'{m.level} {m.id} {m.location}: {m.message}' for m in problems)
