"""EPUB 3 export built from the same BookDoc and page numbers as the PDF.

A reflowable EPUB cannot have fixed pages, so the print page numbers used in the Index and Glossary
are also published as a page list (a map from each print page to the first block on it). Links between
glossary words, glossary entries and index entries work across files.
"""
import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from flask import current_app

from bookdoc import MEDIA_SCHEME, cover_has_content, cover_html
from layout import epub_css
from models import MediaAsset

NAMESPACE = uuid.UUID('7b8f5a60-3b1e-4a52-9a43-1b0c2d9c5e11')
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
ID_RE = re.compile(r'\bid="([^"]+)"')
EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif'}   # EPUB core image types
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
BODY_TYPES = ('bodymatter', 'backmatter', 'frontmatter', 'cover')


@dataclass
class Item:
    key: str
    href: str                   # relative to OEBPS/, e.g. text/chapter-001.xhtml
    title: str
    body: str                   # inner body HTML (converted to XHTML when written)
    epub_type: str = ''
    in_toc: bool = False
    ids: set = field(default_factory=set)

    @property
    def manifest_id(self):
        return f'x-{self.key}'


def xml_text(value):
    return escape(value or '', quote=True)


class _XhtmlWriter(HTMLParser):
    """Re-serialises sanitised HTML as well-formed XHTML, rewriting links and image sources."""

    def __init__(self, link_resolver, image_resolver):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.link_resolver = link_resolver
        self.image_resolver = image_resolver

    def _attrs(self, tag, attrs):
        parts = []
        for name, value in attrs:
            value = '' if value is None else value
            if tag == 'a' and name == 'href':
                value = self.link_resolver(value)
                if value is None:
                    continue                       # a link to nowhere is dropped, the text stays
            if tag == 'img' and name == 'src':
                value = self.image_resolver(value)
                if value is None:
                    return None                    # an image that cannot be packaged is left out
            parts.append(f' {name}="{xml_text(value)}"')
        return ''.join(parts)

    def handle_starttag(self, tag, attrs):
        attributes = self._attrs(tag, attrs)
        if attributes is not None:
            self.out.append(f'<{tag}{attributes}/>' if tag in VOID_TAGS else f'<{tag}{attributes}>')

    def handle_startendtag(self, tag, attrs):
        attributes = self._attrs(tag, attrs)
        if attributes is not None:
            self.out.append(f'<{tag}{attributes}/>')

    def handle_endtag(self, tag):
        if tag not in VOID_TAGS:
            self.out.append(f'</{tag}>')

    def handle_data(self, data):
        self.out.append(escape(data, quote=False))


def to_xhtml(html, link_resolver, image_resolver):
    writer = _XhtmlWriter(link_resolver, image_resolver)
    writer.feed(html)
    writer.close()
    return ''.join(writer.out)


class EpubBuilder:
    def __init__(self, book, result):
        self.book = book
        self.doc = result.doc
        self.settings = result.doc.settings
        self.pages = result.pages
        self.items = []
        self.anchor_file = {}         # anchor id -> OEBPS-relative file that contains it
        self.images = {}              # asset_id -> (href, media_type, bytes) or None
        self.cover_image_id = None
        self.upload_dir = Path(current_app.config['UPLOAD_DIR']).resolve()

    # ---- images ---------------------------------------------------------------------------------
    def _load_image(self, asset_id):
        if asset_id in self.images:
            return self.images[asset_id]
        entry = None
        asset = MediaAsset.query.filter_by(asset_id=asset_id, user_id=self.book.user_id).first()
        if asset is not None:
            path = (self.upload_dir / asset.file_path).resolve()
            if self.upload_dir in path.parents and path.is_file():
                data, media_type = path.read_bytes(), asset.mime_type
                if media_type not in EXTENSIONS:       # e.g. WebP is not a core EPUB type: convert to PNG
                    try:
                        from PIL import Image
                        buffer = io.BytesIO()
                        Image.open(io.BytesIO(data)).convert('RGBA').save(buffer, 'PNG')
                        data, media_type = buffer.getvalue(), 'image/png'
                    except Exception:
                        data = None
                if data is not None:
                    entry = (f'images/img-{asset_id}.{EXTENSIONS[media_type]}', media_type, data)
        self.images[asset_id] = entry
        return entry

    def _resolve_image(self, src):
        if not src.startswith(MEDIA_SCHEME):
            return None
        try:
            asset_id = int(src[len(MEDIA_SCHEME):])
        except ValueError:
            return None
        entry = self._load_image(asset_id)
        return f'../{entry[0]}' if entry else None

    # ---- sections ---------------------------------------------------------------------------------
    def _add(self, key, filename, title, body, epub_type='', in_toc=False):
        item = Item(key=key, href=f'text/{filename}', title=title, body=body, epub_type=epub_type, in_toc=in_toc)
        item.ids = set(ID_RE.findall(body))
        for anchor in item.ids:
            self.anchor_file[anchor] = item.href
        self.items.append(item)

    def build_sections(self):
        doc, s = self.doc, self.settings
        front = doc.cover('front')
        if cover_has_content(front):
            self._add('cover', 'cover.xhtml', 'Cover', cover_html(front), 'cover')
            if front.asset_id and self._load_image(front.asset_id):
                self.cover_image_id = front.asset_id
        if s['include_title_page']:
            self._add('title', 'title.xhtml', 'Title Page',
                      f'<section class="titlepage" epub:type="titlepage">{doc.title_html()}</section>', 'frontmatter')
        for page in doc.front_pages:
            kind = 'dedication' if page.page_type == 'dedication' else 'epigraph'
            self._add(page.key, f'{page.key}.xhtml', page.title,
                      f'<section class="fm-page {page.classes}" id="{page.anchor}" epub:type="{kind}">{page.html}</section>',
                      'frontmatter')
        for number, chapter in enumerate(doc.chapters, start=1):
            self._add(f'chapter-{number}', f'chapter-{number:03d}.xhtml', chapter['title'],
                      f'<section epub:type="chapter">{chapter["html"]}</section>', 'bodymatter', in_toc=True)
        if doc.has_glossary():
            self._add('glossary', 'glossary.xhtml', 'Glossary',
                      f'<section epub:type="glossary">{doc.glossary_html(self.pages)}</section>', 'backmatter', True)
        if doc.has_index():
            self._add('index', 'index.xhtml', 'Index',
                      f'<section epub:type="index">{doc.index_html(self.pages)}</section>', 'backmatter', True)
        if doc.has_about():
            self._add('about', 'about.xhtml', doc.about_title(),
                      f'<section>{doc.about_html()}</section>', 'backmatter', True)

    # ---- conversion ----------------------------------------------------------------------------------
    def _link_resolver(self, item):
        def resolve(href):
            if not href.startswith('#'):
                return href                                   # external links are left alone
            file = self.anchor_file.get(href[1:])
            if file is None:
                return None
            return href if file == item.href else f'{Path(file).name}{href}'
        return resolve

    def xhtml(self, item):
        language = self.settings['language']
        body = to_xhtml(item.body, self._link_resolver(item), self._resolve_image)
        epub_type = f' epub:type="{item.epub_type}"' if item.epub_type in BODY_TYPES else ''
        return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
                f'lang="{language}" xml:lang="{language}">\n<head>\n<meta charset="utf-8"/>\n'
                f'<title>{xml_text(item.title)}</title>\n'
                '<link rel="stylesheet" type="text/css" href="../styles/book.css"/>\n</head>\n'
                f'<body{epub_type}>\n{body}\n</body>\n</html>\n')

    # ---- navigation ------------------------------------------------------------------------------------
    def _page_list(self):
        """[(printed page, anchor)]: each print page maps to the first block starting on it, else the
        block that carries over onto it."""
        if not self.doc.chapters or not self.pages:
            return []
        blocks = {}
        for chapter in self.book.chapters:
            blocks[f'ch-{chapter.chapter_id}'] = [f'b{b.block_id}' for b in chapter.blocks]
        sequence = []
        for chapter in self.doc.chapters:
            sequence.append(chapter['anchor'])
            sequence.extend(blocks.get(chapter['anchor'], []))
        sequence += [a for a in ('sec-glossary', 'sec-index', 'sec-about') if a in self.pages]
        first_on = {}
        for anchor in sequence:
            if anchor in self.pages and anchor in self.anchor_file:
                first_on.setdefault(self.pages[anchor], anchor)
        entries, current = [], None
        for page in range(1, max(first_on, default=0) + 1):
            current = first_on.get(page, current)
            if current is not None:
                entries.append((page, current))
        return entries

    def nav_xhtml(self):
        language = self.settings['language']
        toc = ''.join(f'<li><a href="{i.href}">{xml_text(i.title)}</a></li>' for i in self.items if i.in_toc)
        by_key = {i.key: i for i in self.items}
        landmarks = []
        if 'cover' in by_key:
            landmarks.append(f'<li><a epub:type="cover" href="{by_key["cover"].href}">Cover</a></li>')
        if 'title' in by_key:
            landmarks.append(f'<li><a epub:type="titlepage" href="{by_key["title"].href}">Title Page</a></li>')
        first_chapter = next((i for i in self.items if i.key.startswith('chapter-')), None)
        if first_chapter:
            landmarks.append(f'<li><a epub:type="bodymatter" href="{first_chapter.href}">Start of Content</a></li>')
        landmarks.append('<li><a epub:type="toc" href="nav.xhtml#toc">Contents</a></li>')

        page_nav = ''
        entries = self._page_list()
        if entries:
            links = ''.join(f'<li><a href="{self.anchor_file[a]}#{a}">{page}</a></li>' for page, a in entries)
            page_nav = f'<nav epub:type="page-list" hidden="hidden"><ol>{links}</ol></nav>\n'
        return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
                f'lang="{language}" xml:lang="{language}">\n<head>\n<meta charset="utf-8"/>\n'
                f'<title>{xml_text(self.book.title)}</title>\n</head>\n<body>\n'
                f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{toc}</ol></nav>\n'
                f'<nav epub:type="landmarks" hidden="hidden"><h2>Guide</h2><ol>{"".join(landmarks)}</ol></nav>\n'
                f'{page_nav}</body>\n</html>\n')

    # ---- package -----------------------------------------------------------------------------------------
    def opf(self):
        book, s = self.book, self.settings
        identifier = uuid.uuid5(NAMESPACE, f'ibs-book-{book.book_id}')
        modified = (book.modified_at or datetime.utcnow()).replace(microsecond=0).isoformat() + 'Z'
        metadata = [f'<dc:identifier id="bookid">urn:uuid:{identifier}</dc:identifier>',
                    f'<dc:title id="main-title">{xml_text(book.title)}</dc:title>',
                    '<meta refines="#main-title" property="title-type">main</meta>']
        if (book.subtitle or '').strip():
            metadata += [f'<dc:title id="sub-title">{xml_text(book.subtitle)}</dc:title>',
                         '<meta refines="#sub-title" property="title-type">subtitle</meta>']
        metadata.append(f'<dc:language>{s["language"]}</dc:language>')
        names = ([a.name for a in self.doc.authors if (a.name or '').strip()]
                 or ([book.author_name] if book.author_name else []))
        for number, name in enumerate(names, start=1):
            metadata += [f'<dc:creator id="creator-{number}">{xml_text(name)}</dc:creator>',
                         f'<meta refines="#creator-{number}" property="role" scheme="marc:relators">aut</meta>']
        if book.copyright_holder or book.copyright_year:
            rights = f'\u00a9 {book.copyright_year or ""} {book.copyright_holder or ""}'.strip()
            metadata.append(f'<dc:rights>{xml_text(rights)}</dc:rights>')
        metadata.append(f'<meta property="dcterms:modified">{modified}</meta>')
        if self.cover_image_id:
            metadata.append(f'<meta name="cover" content="img-{self.cover_image_id}"/>')

        manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                    '<item id="css" href="styles/book.css" media-type="text/css"/>']
        for asset_id, entry in self.images.items():
            if entry:
                href, media_type, _ = entry
                props = ' properties="cover-image"' if asset_id == self.cover_image_id else ''
                manifest.append(f'<item id="img-{asset_id}" href="{href}" media-type="{media_type}"{props}/>')
        spine = []
        for item in self.items:
            manifest.append(f'<item id="{item.manifest_id}" href="{item.href}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{item.manifest_id}"/>')
        spine.append('<itemref idref="nav" linear="no"/>')
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" '
                f'xml:lang="{s["language"]}">\n'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' + '\n'.join(metadata) + '\n</metadata>\n'
                '<manifest>\n' + '\n'.join(manifest) + '\n</manifest>\n'
                '<spine>\n' + '\n'.join(spine) + '\n</spine>\n</package>\n')

    def build(self):
        self.build_sections()
        # Convert every section first: this also discovers which images the book really uses.
        xhtml = {item.key: self.xhtml(item) for item in self.items}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            info = zipfile.ZipInfo('mimetype', FIXED_TIME)          # must be first and stored uncompressed
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, 'application/epub+zip')

            def write(name, data):
                entry = zipfile.ZipInfo(name, FIXED_TIME)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)

            write('META-INF/container.xml',
                  '<?xml version="1.0" encoding="utf-8"?>\n'
                  '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                  '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                  '</rootfiles>\n</container>\n')
            write('OEBPS/content.opf', self.opf())
            write('OEBPS/nav.xhtml', self.nav_xhtml())
            write('OEBPS/styles/book.css', epub_css(self.settings))
            for item in self.items:
                write(f'OEBPS/{item.href}', xhtml[item.key])
            for entry in self.images.values():
                if entry:
                    write(f'OEBPS/{entry[0]}', entry[2])
        return buffer.getvalue()


def build_epub(book, result):
    """The book as EPUB bytes. `result` is the cached PDF layout result (it supplies page numbers)."""
    return EpubBuilder(book, result).build()
