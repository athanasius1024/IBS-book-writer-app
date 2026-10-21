"""PDF layout: the authoritative source of page numbers for the Page view, Index, Glossary and EPUB.

Rendering is done in passes because the Index/Glossary/Contents show page numbers that depend on the
layout itself. The body always comes before the Index and Glossary, so body numbers are stable from
pass 1; later passes only settle the back matter and the Contents. WeasyPrint lists an anchor on
every page its element spans, so the *first* page an anchor appears on is the one that counts.
"""
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from flask import current_app
from weasyprint import CSS, HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

import paths
from bookdoc import DERIVED_SCHEME, MEDIA_SCHEME, BookDoc, cover_has_content, cover_html
from layout import ALLOWED_FONT_FILES, FONT_SCHEME, get_settings, pdf_css, settings_hash
from models import MediaAsset, MediaDerivative

log = logging.getLogger(__name__)

MAX_PASSES = 4
_CACHE = OrderedDict()
_CACHE_SIZE = 4


class MediaFetcher(URLFetcher):
    """Serves only the book owner's own media-library files; every other URL is refused.

    This stops a book from making the server read local files or call out to other hosts.
    """

    def __init__(self, user_id, upload_dir):
        super().__init__()
        self.user_id = user_id
        self.upload_dir = Path(upload_dir).resolve()

    def fetch(self, url, headers=None):
        if url.startswith(FONT_SCHEME):
            return self._fetch_font(url)
        if url.startswith(DERIVED_SCHEME):
            return self._fetch_derivative(url)
        if not url.startswith(MEDIA_SCHEME):
            raise ValueError(f'Blocked URL: {url[:60]}')
        try:
            asset_id = int(url[len(MEDIA_SCHEME):])
        except ValueError:
            raise ValueError('Bad media URL') from None
        asset = MediaAsset.query.filter_by(asset_id=asset_id, user_id=self.user_id).first()
        if asset is None:
            raise ValueError('Unknown media')
        path = (self.upload_dir / asset.file_path).resolve()
        if self.upload_dir not in path.parents or not path.is_file():
            raise ValueError('Media file missing')
        return URLFetcherResponse(url, body=path.read_bytes(), headers={'Content-Type': asset.mime_type})

    @staticmethod
    def _fetch_font(url):
        """One of the bundled fonts, by exact file name from a fixed list: never a path, never anything else."""
        name = url[len(FONT_SCHEME):]
        if name not in ALLOWED_FONT_FILES:
            raise ValueError(f'Blocked font: {name[:60]}')
        path = (paths.fonts_dir() / name).resolve()
        if paths.fonts_dir().resolve() not in path.parents or not path.is_file():
            raise ValueError('Font file missing')
        return URLFetcherResponse(url, body=path.read_bytes(), headers={'Content-Type': 'font/ttf'})

    def _fetch_derivative(self, url):
        """A cropped / downsized copy of one of the owner's pictures."""
        try:
            number = int(url[len(DERIVED_SCHEME):])
        except ValueError:
            raise ValueError('Bad media URL') from None
        row = MediaDerivative.query.filter_by(derivative_id=number, user_id=self.user_id).first()
        if row is None:
            raise ValueError('Unknown media')
        path = (self.upload_dir / row.file_path).resolve()
        if self.upload_dir not in path.parents or not path.is_file():
            raise ValueError('Media file missing')
        return URLFetcherResponse(url, body=path.read_bytes(), headers={'Content-Type': row.mime_type})


@dataclass
class LayoutResult:
    doc: BookDoc
    pdf: bytes
    pages: dict = field(default_factory=dict)         # anchor id -> printed page number
    toc_pages: dict = field(default_factory=dict)     # contents anchor -> printed page number
    physical_pages: int = 0
    body_start: int = 1                               # physical page where page 1 begins
    passes: int = 0


def assemble_body(doc, pages, toc_pages):
    """All sections of the book (covers, title, front matter, Contents, chapters, back matter) in order,
    as HTML for inside a <body>. Shared by the PDF layout and the HTML export."""
    s = doc.settings
    parts = []

    def cover_section(panel, anchor):
        cover = doc.cover(panel)
        return f'<section class="cover" id="{anchor}">{cover_html(cover)}</section>'

    if s['include_covers']:
        if cover_has_content(doc.cover('front')):
            parts.append(cover_section('front', 'cover-front'))
        if cover_has_content(doc.cover('inside_front')):
            parts.append(cover_section('inside_front', 'cover-inside-front'))
    if s['include_title_page']:
        parts.append(f'<section class="titlepage" id="title-page">{doc.title_html()}</section>')
    for page in doc.front_pages:
        parts.append(f'<section class="fm-page {page.classes}" id="{page.anchor}">{page.html}</section>')
    if s['include_contents'] and doc.has_contents():
        parts.append(f'<section class="contents" id="contents">{doc.toc_html(toc_pages)}</section>')
    for index, chapter in enumerate(doc.chapters):
        parts.append(f'<section class="chapter{" first" if index == 0 else ""}">{chapter["html"]}</section>')
    if doc.has_glossary():
        parts.append(f'<section class="backmatter">{doc.glossary_html(pages)}</section>')
    if doc.has_index():
        parts.append(f'<section class="backmatter">{doc.index_html(pages)}</section>')
    if doc.has_about():
        parts.append(f'<section class="backmatter">{doc.about_html()}</section>')
    if s['include_covers']:
        if cover_has_content(doc.cover('inside_back')):
            parts.append(cover_section('inside_back', 'cover-inside-back'))
        if cover_has_content(doc.cover('back')):
            parts.append(cover_section('back', 'cover-back'))

    return ''.join(parts)


def assemble_html(doc, pages, toc_pages):
    """The full print document as one HTML string."""
    from html import escape
    return (f'<!DOCTYPE html><html lang="{doc.settings["language"]}"><head><meta charset="utf-8">'
            f'<title>{escape(doc.title)}</title></head><body>' + assemble_body(doc, pages, toc_pages)
            + '</body></html>')


def first_pages(rendered):
    """anchor id -> first physical page (1-based) it appears on."""
    first = {}
    for number, page in enumerate(rendered.pages, start=1):
        for name in page.anchors:
            first.setdefault(name, number)
    return first


def run_layout(book, settings):
    doc = BookDoc(book, settings)
    fetcher = MediaFetcher(book.user_id, current_app.config['UPLOAD_DIR'])
    stylesheet = CSS(string=pdf_css(settings, book.title), url_fetcher=fetcher)

    pages, toc_pages, rendered, start, passes = {}, {}, None, 1, 0
    for passes in range(1, MAX_PASSES + 1):
        html = assemble_html(doc, pages, toc_pages)
        rendered = HTML(string=html, base_url='ibs://book/', url_fetcher=fetcher).render(stylesheets=[stylesheet])
        first = first_pages(rendered)
        start = first.get(doc.body_start_anchor, 1) if doc.body_start_anchor else 1
        new_pages = {anchor: number - start + 1 for anchor, number in first.items() if number >= start}
        new_toc = {anchor: new_pages[anchor] for anchor, _ in doc.toc_entries() if anchor in new_pages}
        if new_pages == pages and new_toc == toc_pages:
            break
        pages, toc_pages = new_pages, new_toc
    else:
        log.warning('Layout of book %s did not settle after %s passes', book.book_id, MAX_PASSES)

    return LayoutResult(doc=doc, pdf=rendered.write_pdf(), pages=pages, toc_pages=toc_pages,
                        physical_pages=len(rendered.pages), body_start=start, passes=passes)


def get_layout(book, fresh=False):
    """Cached layout of the book as it is right now (keyed by book edit time and settings).

    fresh=True rebuilds it even if the book has not changed (a new 'Generated' date on the Contents);
    the new result replaces the cached one.
    """
    settings = get_settings(book)
    key = (book.book_id, book.modified_at.isoformat() if book.modified_at else '', settings_hash(settings))
    if key in _CACHE and not fresh:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    result = run_layout(book, settings)
    _CACHE[key] = result
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return result


def clear_cache():
    _CACHE.clear()
