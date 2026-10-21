"""The self-contained HTML export and the OpenDocument Text (.odt) export."""
import base64
import io
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from bookfactory import add_author, add_front_matter, make_asset, make_book, make_user
from html_export import build_html
from imaging import derive
from imagespec import parse_crop
from models import BookTocEntry, ContentBlock, db
from odt import ODT_MIME, build_odt
from render import clear_cache, get_layout

NO_HYPHEN = {'hyphenate': False}
NS = {'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0', 'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
      'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0', 'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
      'xlink': 'http://www.w3.org/1999/xlink', 'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
      'svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
      'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
      'manifest': 'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0'}
VALIDATOR = Path(os.environ.get('ODF_VALIDATOR_JAR', Path.home() / '.cache' / 'ibs-tools' / 'odfvalidator.jar'))


def q(prefix, name):
    return f'{{{NS[prefix]}}}{name}'


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()


def picture(width=100, height=80):
    image = Image.new('RGB', (width, height), (255, 0, 0))
    image.paste((0, 0, 255), (width // 2, 0, width, height))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


@pytest.fixture()
def rich_book(app):
    """A book that uses every feature the exporters handle."""
    user = make_user()
    book, _ = make_book(user, title='A & B <Tales>', chapters=3, paragraphs=3, settings=NO_HYPHEN,
                        terms=[('Quokka', 'A small marsupial'), ('fox', 'A clever animal')],
                        inject={(1, 2): 'Quokka', (2, 1): 'a Quokka and the fox'})
    add_front_matter(book)
    asset = make_asset(app, user, 'two.png', picture())
    add_author(book, photo=asset)
    book.cover('front').asset_id = asset.asset_id
    first = book.chapters[0]
    first.epigraph_text = 'Nothing in the world\nis softer than water.'
    first.epigraph_source = 'Tao Teh Ching #78'
    first.blocks.append(ContentBlock(block_type='heading', content_text='Origins <&>', content_data={'level': 1}, sort_order=20))
    first.blocks.append(ContentBlock(block_type='list', content_text='one\ntwo\nthree', content_data={'ordered': True}, sort_order=21))
    first.blocks.append(ContentBlock(block_type='table', content_text='a|b', sort_order=22,
                                     content_data={'header': True, 'rows': [['Term', 'Meaning'], ['x', 'y'], ['z', 'w']]}))
    first.blocks.append(ContentBlock(block_type='image', content_text='A picture', asset_id=asset.asset_id, sort_order=23))
    first.blocks.append(ContentBlock(block_type='text', sort_order=24, content_text=(
        'Some **bold** and *italic* text with `code`.\n\n> A quote\n\n'
        f'![Both halves](image:{asset.asset_id} "Left half"){{: data-crop="0,0,0.5,1" data-w="50"}}\n\n'
        '    preformatted line\n\n[a link](https://example.com)')))
    db.session.flush()
    return book, asset, user


@pytest.fixture()
def result(rich_book):
    return get_layout(rich_book[0])


# ================================ HTML ==================================================================

class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.srcs, self.tags = set(), [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if 'id' in a:
            self.ids.add(a['id'])
        if a.get('href'):
            self.hrefs.append(a['href'])
        if 'src' in a:
            self.srcs.append(a['src'])


def parsed(html):
    collector = _Collect()
    collector.feed(html)
    return collector


def test_html_is_one_self_contained_utf8_document(rich_book, result):
    book, _, _ = rich_book
    data = build_html(book, result)
    html = data.decode('utf-8')
    assert html.startswith('<!DOCTYPE html>') and '<meta charset="utf-8">' in html and '<style>' in html
    assert '<title>A &amp; B &lt;Tales&gt;</title>' in html                      # titles are escaped
    page = parsed(html)
    assert 'script' not in page.tags and 'link' not in page.tags
    assert all(src.startswith('data:image/') for src in page.srcs) and page.srcs
    assert not any(h.startswith(('http://example', '/media', 'ibs-')) for h in page.hrefs if 'example.com' not in h)
    assert 'ibs-media' not in html and 'ibs-derived' not in html and 'epub:type' not in html


def test_html_has_the_stamp_the_epigraph_the_glossary_and_the_index(rich_book, result):
    html = build_html(rich_book[0], result).decode()
    stamp = result.doc.stamp()
    assert f'<p class="toc-stamp">{stamp}</p>' in html
    assert 'class="epigraph ep-right ep-small ep-italic"' in html and 'softer than water.' in html
    assert 'id="sec-glossary"' in html and 'id="sec-index"' in html and 'A small marsupial' in html
    assert 'Origins &lt;&amp;&gt;' in html                                         # heading text is escaped


def test_every_internal_link_in_the_html_has_a_target(rich_book, result):
    page = parsed(build_html(rich_book[0], result).decode())
    internal = [h[1:] for h in page.hrefs if h.startswith('#')]
    assert len(internal) > 10
    missing = [h for h in internal if h not in page.ids]
    assert not missing, missing[:5]


def test_html_embeds_the_cropped_copy_not_the_original(rich_book, result):
    html = build_html(rich_book[0], result).decode()
    sizes = set()
    for src in re.findall(r'src="data:image/png;base64,([^"]+)"', html):
        sizes.add(Image.open(io.BytesIO(base64.b64decode(src))).size)
    assert (50, 80) in sizes and (100, 80) in sizes          # the crop, and the uncropped picture used in the image block


def test_html_never_embeds_someone_elses_picture(app):
    owner, other = make_user('owner'), make_user('other')
    theirs = make_asset(app, other, 'theirs.png', picture())
    book, _ = make_book(owner, chapters=1, paragraphs=1, settings=NO_HYPHEN)
    book.chapters[0].blocks[0].content_text = f'![sneaky](image:{theirs.asset_id})'
    db.session.flush()
    html = build_html(book, get_layout(book)).decode()
    assert 'data:image' not in html and 'no longer available' in html


def test_html_for_a_bare_book_and_without_contents(app):
    user = make_user()
    book, _ = make_book(user, chapters=0, settings={'include_contents': False, 'include_covers': False,
                                                    'include_title_page': False})
    html = build_html(book, get_layout(book)).decode()
    assert '<body>' in html and '<p class="toc-stamp">' not in html           # no Contents page, so no stamp


def test_html_page_links_in_the_index_point_at_real_places(rich_book, result):
    page = parsed(build_html(rich_book[0], result).decode())
    occurrences = [h[1:] for h in page.hrefs if re.fullmatch(r'#o\d+-\d+', h)]
    assert occurrences and all(o in page.ids for o in occurrences)


# ================================ ODT ===================================================================

@pytest.fixture()
def odt(rich_book, result):
    return build_odt(rich_book[0], result)


def archive(data):
    return zipfile.ZipFile(io.BytesIO(data))


def content(data):
    return ET.fromstring(archive(data).read('content.xml'))


def test_odt_package_structure(odt):
    z = archive(odt)
    first = z.infolist()[0]
    assert first.filename == 'mimetype' and first.compress_type == zipfile.ZIP_STORED
    assert z.read('mimetype').decode() == ODT_MIME and z.testzip() is None
    for name in ('content.xml', 'styles.xml', 'meta.xml', 'META-INF/manifest.xml'):
        ET.fromstring(z.read(name))                                              # every XML part is well-formed
    manifest = ET.fromstring(z.read('META-INF/manifest.xml'))
    declared = {e.get(q('manifest', 'full-path')) for e in manifest}
    packaged = {n for n in z.namelist() if n not in ('mimetype', 'META-INF/manifest.xml')}
    assert declared == packaged | {'/'}
    assert all(n.startswith('Pictures/') for n in packaged if n not in ('content.xml', 'styles.xml', 'meta.xml'))


def test_odt_headings_contents_stamp_and_epigraph(odt, result):
    root = content(odt)
    text = root.find('.//office:text', NS)
    headings = [(h.get(q('text', 'outline-level')), ''.join(h.itertext())) for h in text.iter(q('text', 'h'))]
    assert ('1', 'Chapter 1') in headings and ('1', 'Chapter 3') in headings and ('1', 'Glossary') in headings
    assert ('2', 'Origins <&>') in headings                                      # the heading's text arrives unharmed
    paragraphs = [''.join(p.itertext()) for p in text.iter(q('text', 'p'))]
    assert result.doc.stamp() in paragraphs
    assert 'Contents' in paragraphs
    assert any('softer than water' in p for p in paragraphs) and '\u2014 Tao Teh Ching #78' in paragraphs


def test_odt_chapter_headings_start_new_pages(odt):
    root = content(odt)
    styles = {s.get(q('style', 'name')): s for s in root.iter(q('style', 'style'))}
    heading = next(h for h in root.iter(q('text', 'h')) if ''.join(h.itertext()) == 'Chapter 2')
    style = styles[heading.get(q('text', 'style-name'))]
    assert style.find('style:paragraph-properties', NS).get(q('fo', 'break-before')) == 'page'


def test_odt_internal_links_all_point_at_bookmarks(odt):
    root = content(odt)
    bookmarks = {b.get(q('text', 'name')) for b in root.iter(q('text', 'bookmark'))}
    links = [a.get(q('xlink', 'href')) for a in root.iter(q('text', 'a'))]
    internal = [h[1:] for h in links if h.startswith('#')]
    assert len(internal) > 10 and not [h for h in internal if h not in bookmarks]
    assert 'https://example.com' in links                                        # external links stay external
    assert len(bookmarks) == len(list(root.iter(q('text', 'bookmark'))))         # no duplicate bookmark names


def test_odt_lists_table_code_and_quote(odt):
    root = content(odt)
    assert [''.join(li.itertext()) for li in root.iter(q('text', 'list-item'))] == ['one', 'two', 'three']
    table = root.find('.//table:table', NS)
    assert table.find('table:table-header-rows', NS) is not None
    assert len(table.findall('.//table:table-row', NS)) == 3
    assert int(table.find('table:table-column', NS).get(q('table', 'number-columns-repeated'))) == 2
    assert [''.join(c.itertext()) for c in table.find('table:table-header-rows', NS).iter(q('table', 'table-cell'))] == ['Term', 'Meaning']
    paragraph_styles = {p.get(q('text', 'style-name')) for p in root.iter(q('text', 'p'))}
    assert 'Preformatted_20_Text' in paragraph_styles and 'Quotations' in paragraph_styles
    spans = {s.get(q('text', 'style-name')) for s in root.iter(q('text', 'span'))}
    assert {'T_Strong', 'T_Emph', 'T_Code'} <= spans


def test_odt_embeds_the_cropped_picture_with_its_size_and_alt_text(odt, rich_book):
    z = archive(odt)
    sizes = sorted(Image.open(io.BytesIO(z.read(n))).size for n in z.namelist() if n.startswith('Pictures/'))
    assert (50, 80) in sizes and (100, 80) in sizes
    root = content(odt)
    frames = list(root.iter(q('draw', 'frame')))
    assert len(frames) >= 3 and all(f.get(q('text', 'anchor-type')) == 'as-char' for f in frames)
    cropped = next(f for f in frames if (f.find('svg:title', NS) is not None and f.find('svg:title', NS).text == 'Both halves'))
    width_mm = float(cropped.get(q('svg', 'width'))[:-2])
    text_width = 139.7 - 20 - 15                                                  # trim width minus margins (defaults)
    assert abs(width_mm - text_width * 0.5) < 0.1                                 # data-w="50": half the text width
    assert abs(float(cropped.get(q('svg', 'height'))[:-2]) / width_mm - 80 / 50) < 0.01   # the crop's proportions


def test_odt_glossary_and_index_point_at_chapters_not_page_numbers(odt):
    root = content(odt)
    text = ' '.join(''.join(p.itertext()) for p in root.iter(q('text', 'p')))
    assert 'A small marsupial' in text and 'Chapter 1' in text
    entry = next(p for p in root.iter(q('text', 'p')) if ''.join(p.itertext()).startswith('Quokka:'))
    assert ''.join(entry.itertext()) == 'Quokka: Chapter 1, Chapter 2'
    assert len(list(entry.iter(q('text', 'a')))) == 2


def test_odt_page_layout_and_footer_follow_the_layout_settings(rich_book, result):
    book, _, _ = rich_book
    styles = ET.fromstring(archive(build_odt(book, result)).read('styles.xml'))
    props = styles.find('.//style:page-layout-properties', NS)
    assert props.get(q('fo', 'page-width')) == '139.70mm' and props.get(q('fo', 'page-height')) == '215.90mm'
    assert props.get(q('fo', 'margin-left')) == '20.00mm' and props.get(q('fo', 'margin-right')) == '15.00mm'
    assert styles.find('.//style:page-layout', NS).get(q('style', 'page-usage')) == 'mirrored'
    assert styles.find('.//style:footer//text:page-number', NS) is not None
    book.layout.settings = {'hyphenate': False, 'page_numbers': 'none', 'trim': 'a5'}
    db.session.flush()
    clear_cache()
    plain = ET.fromstring(archive(build_odt(book, get_layout(book))).read('styles.xml'))
    assert plain.find('.//style:footer', NS) is None
    assert plain.find('.//style:page-layout-properties', NS).get(q('fo', 'page-width')) == '148.00mm'


def test_odt_follows_an_edited_contents(rich_book):
    book, _, _ = rich_book
    c1, c2, c3 = book.chapters
    for position, spec in enumerate([{'kind': 'part', 'label': 'Part One'}, {'kind': 'chapter', 'chapter': c1, 'label': 'The Start'},
                                     {'kind': 'chapter', 'chapter': c2, 'visible': False},
                                     {'kind': 'part', 'label': 'Part Two'}, {'kind': 'chapter', 'chapter': c3, 'level': 1}], 1):
        book.toc_entries.append(BookTocEntry(sort_order=position, visible=spec.pop('visible', True), level=spec.pop('level', 0), **spec))
    db.session.flush()
    root = content(build_odt(book, get_layout(book)))
    lines = [(p.get(q('text', 'style-name')), ''.join(p.itertext())) for p in root.iter(q('text', 'p'))
             if (p.get(q('text', 'style-name')) or '').startswith('Contents_20_')]
    # (the Contents title opens its page, so it carries a page-break variant of its style and is not listed here)
    assert lines == [('Contents_20_Part', 'Part One'), ('Contents_20_1', 'The Start'),
                     ('Contents_20_Part', 'Part Two'), ('Contents_20_2', 'Chapter 3')]
    assert 'Contents' in [''.join(p.itertext()) for p in root.iter(q('text', 'p'))]
    assert 'Chapter 2' not in [text for _, text in lines]                           # the hidden chapter is not listed


def test_odt_never_embeds_someone_elses_picture(app):
    owner, other = make_user('owner'), make_user('other')
    theirs = make_asset(app, other, 'theirs.png', picture())
    book, _ = make_book(owner, chapters=1, paragraphs=1, settings=NO_HYPHEN)
    book.chapters[0].blocks[0].content_text = f'![sneaky](image:{theirs.asset_id})'
    db.session.flush()
    z = archive(build_odt(book, get_layout(book)))
    assert not [n for n in z.namelist() if n.startswith('Pictures/')]
    assert 'no longer available' in ''.join(content(z.fp.read() if False else build_odt(book, get_layout(book))).itertext())


def test_odt_for_a_minimal_book_and_for_odd_text(app):
    user = make_user()
    book, _ = make_book(user, title='Plain', chapters=0, settings={'include_covers': False, 'include_title_page': False,
                                                                    'include_contents': False})
    data = build_odt(book, get_layout(book))
    ET.fromstring(archive(data).read('content.xml'))
    odd, _ = make_book(user, title='Odd', chapters=1, paragraphs=1, settings=NO_HYPHEN)
    odd.chapters[0].blocks[0].content_text = 'Ampersand & angle < bracket > "quotes" \u00e9\u4e2d\u6587 \U0001f600\n\n* a\n    * nested\n\n| a | b |\n|---|---|\n| 1 | 2 |'
    db.session.flush()
    clear_cache()
    root = content(build_odt(odd, get_layout(odd)))
    flat = ''.join(root.itertext())
    assert 'Ampersand & angle < bracket >' in flat and '\u4e2d\u6587' in flat and 'nested' in flat
    assert root.find('.//table:table', NS) is not None                              # Markdown tables become tables


@pytest.mark.skipif(shutil.which('java') is None or not VALIDATOR.exists(),
                    reason='needs Java and the ODF validator jar (see DEPLOYMENT.md, ODF_VALIDATOR_JAR)')
def test_odf_validator_accepts_the_document(odt, tmp_path):
    path = tmp_path / 'book.odt'
    path.write_bytes(odt)
    run = subprocess.run(['java', '-jar', str(VALIDATOR), '-1.3', str(path)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and 'Error' not in run.stdout + run.stderr, run.stdout + run.stderr


@pytest.mark.skipif(shutil.which('soffice') is None, reason='LibreOffice is not installed')
def test_libreoffice_opens_the_document_and_it_reads_correctly(odt, tmp_path, result):
    path = tmp_path / 'book.odt'
    path.write_bytes(odt)
    profile = tmp_path / 'profile'
    run = subprocess.run(['soffice', f'-env:UserInstallation=file://{profile}', '--headless', '--convert-to', 'pdf',
                          '--outdir', str(tmp_path), str(path)], capture_output=True, text=True, timeout=180)
    pdf = tmp_path / 'book.pdf'
    assert pdf.exists(), run.stdout + run.stderr
    reader = PdfReader(str(pdf))
    text = ' '.join(page.extract_text() or '' for page in reader.pages)
    assert len(reader.pages) >= 10
    for expected in ('Chapter 1', 'Chapter 3', 'Contents', 'Glossary', 'Index', 'softer than water', 'Origins',
                     result.doc.stamp(), 'A clever animal'):
        assert expected in text, expected
