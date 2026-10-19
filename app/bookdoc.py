"""The book as one document: front matter, chapters (with annotated terms), glossary, index, authors.

The same BookDoc feeds every renderer (PDF via render.py, EPUB via epub.py), so content, links and
page numbers agree between formats. Page numbers are looked up in a `pages` mapping
(anchor id -> printed page number) produced by the PDF layout pass.
"""
import re
from dataclasses import dataclass
from html import escape

from layout import page_style_classes
from markup import render_markdown, render_markdown_lines
from terms import Annotator, Matcher, collapse_pages

MEDIA_SCHEME = 'ibs-media://'
HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

_HEADING_TAG = {1: 'h2', 2: 'h3', 3: 'h4'}


def media_src(asset_id):
    return f'{MEDIA_SCHEME}{int(asset_id)}'


def block_html(block):
    """HTML for one content block (all user text escaped or sanitised)."""
    data = block.content_data or {}
    kind = block.block_type
    text = block.content_text or ''
    if kind == 'heading':
        tag = _HEADING_TAG.get(data.get('level', 2), 'h3')
        inner = f'<{tag} class="blk-heading">{escape(text)}</{tag}>'
    elif kind == 'list':
        tag = 'ol' if data.get('ordered') else 'ul'
        items = ''.join(f'<li>{escape(item)}</li>' for item in block.list_items)
        inner = f'<{tag}>{items}</{tag}>'
    elif kind == 'table':
        rows = data.get('rows') or []
        head = ''
        if data.get('header') and rows:
            head = '<thead><tr>' + ''.join(f'<th>{escape(c)}</th>' for c in rows[0]) + '</tr></thead>'
            rows = rows[1:]
        body = ''.join('<tr>' + ''.join(f'<td>{escape(c)}</td>' for c in row) + '</tr>' for row in rows)
        inner = f'<table>{head}<tbody>{body}</tbody></table>'
    elif kind in ('image', 'icon'):
        if block.asset_id:
            alt = escape(text or (block.asset.asset_name if block.asset else ''), quote=True)
            caption = f'<figcaption>{escape(text)}</figcaption>' if text else ''
            klass = 'blk-figure blk-icon' if kind == 'icon' else 'blk-figure'
            inner = f'<figure class="{klass}"><img src="{media_src(block.asset_id)}" alt="{alt}"/>{caption}</figure>'
        else:
            inner = '<p><em>[image no longer available]</em></p>'
    else:
        inner = str(render_markdown(text))
    return f'<div class="blk blk-{kind}" id="b{block.block_id}">{inner}</div>'


def _safe_color(value, default):
    return value if value and HEX_COLOR.match(value) else default


def cover_html(cover):
    """Inner HTML of a cover panel box."""
    style = (f'background-color: {_safe_color(cover.background_color, "#ffffff")}; '
             f'color: {_safe_color(cover.text_color, "#000000")};')
    image = f'<img src="{media_src(cover.asset_id)}" alt=""/>' if cover.asset_id else ''
    body = str(render_markdown(cover.content_text or ''))
    return f'<div class="cover-box" style="{style}">{image}{body}</div>'


def cover_has_content(cover):
    return bool(cover and ((cover.content_text or '').strip() or cover.asset_id))


def usage_counts(book):
    """term_id -> number of times the term is used in the chapters (headings included)."""
    terms = list(book.terms)
    if not terms:
        return {}
    annotator = Annotator(Matcher(terms), 'none')
    for chapter in book.chapters:
        annotator.annotate(f'<h1>{escape(chapter.title)}</h1>' + ''.join(block_html(b) for b in chapter.blocks))
    return {term_id: len(found) for term_id, found in annotator.occurrences.items()}


@dataclass
class FrontPage:
    key: str
    anchor: str
    page_type: str
    html: str          # inner content (without the <section> wrapper)
    classes: str       # alignment classes
    title: str


class BookDoc:
    """Builds and annotates the book once; renderers ask it for pieces."""

    def __init__(self, book, settings):
        self.book = book
        self.settings = settings
        self.title = book.title
        self.terms = list(book.terms)
        self.annotator = Annotator(Matcher(self.terms), settings['link_mode'])

        self.chapters = []         # {'id', 'anchor', 'title', 'html'}
        self.block_anchors = []    # block anchors in document order
        for chapter in book.chapters:
            self.annotator.start_chapter()
            anchor = f'ch-{chapter.chapter_id}'
            raw = (f'<h1 class="chapter-title" id="{anchor}">{escape(chapter.title)}</h1>'
                   '<div class="chapter-body">' + ''.join(block_html(b) for b in chapter.blocks) + '</div>')
            self.chapters.append({'id': chapter.chapter_id, 'anchor': anchor, 'title': chapter.title,
                                  'html': self.annotator.annotate(raw)})
            self.block_anchors.extend(f'b{b.block_id}' for b in chapter.blocks)

        self.front_pages = [self._front_page(p) for p in book.pages]
        self.authors = list(book.authors)

    # ---- front matter ----------------------------------------------------------------------
    def _front_page(self, page):
        body = str(render_markdown_lines(page.body))
        attribution = (f'<p class="attribution">\u2014 {escape(page.attribution)}</p>'
                       if (page.attribution or '').strip() else '')
        return FrontPage(
            key=f'{page.page_type}-{page.page_id}', anchor=f'fp-{page.page_id}', page_type=page.page_type,
            html=f'<div class="fm-inner"><div class="fm-body">{body}</div>{attribution}</div>',
            classes=page_style_classes(page.style), title=page.type_label)

    def title_html(self):
        subtitle = f'<p class="subtitle">{escape(self.book.subtitle)}</p>' if self.book.subtitle else ''
        return f'<h1>{escape(self.title)}</h1>{subtitle}<p class="byline">{escape(self.byline())}</p>'

    def byline(self):
        names = [a.name for a in self.authors if (a.name or '').strip()]
        return ', '.join(names) if names else (self.book.author_name or '')

    def cover(self, panel):
        return self.book.cover(panel)

    # ---- generated sections --------------------------------------------------------------------
    def glossary_terms(self):
        return sorted((t for t in self.terms if t.has_entry), key=lambda t: t.term.lower())

    def index_terms(self):
        return sorted((t for t in self.terms if t.in_index and self.annotator.occurrences.get(t.term_id)),
                      key=lambda t: t.term.lower())

    def has_glossary(self):
        return bool(self.glossary_terms())

    def has_index(self):
        return bool(self.index_terms())

    def has_about(self):
        return bool(self.authors)

    def page_links(self, term_id, pages):
        """Links like '3', '5-7' to where `term_id` is used; first occurrence on each page is the target."""
        by_page = {}
        for occ in self.annotator.occurrences.get(term_id, []):
            number = pages.get(occ)
            if number is not None:
                by_page.setdefault(number, occ)
        links = []
        for first, last in collapse_pages(list(by_page)):
            label = str(first) if first == last else f'{first}\u2013{last}'
            links.append(f'<a class="pg" href="#{by_page[first]}">{label}</a>')
        return links

    def glossary_html(self, pages):
        entries = []
        for term in self.glossary_terms():
            links = self.page_links(term.term_id, pages)
            refs = ''
            if links:
                label = 'Page' if len(links) == 1 and '\u2013' not in links[0] and ',' not in links[0] else 'Pages'
                refs = f'<span class="refs">{label} {", ".join(links)}</span>'
            entries.append(f'<dt id="term-{term.term_id}">{escape(term.term)}</dt>'
                           f'<dd>{escape(term.definition.strip())}{refs}</dd>')
        return '<h1 class="section-title" id="sec-glossary">Glossary</h1><dl class="glossary">' + ''.join(entries) + '</dl>'

    def index_html(self, pages):
        groups, current, parts = {}, None, []
        for term in self.index_terms():
            letter = next((c.upper() for c in term.term if c.isalpha()), '#')
            groups.setdefault(letter, []).append(term)
        for letter in sorted(groups):
            parts.append(f'<h2 class="ix-letter">{escape(letter)}</h2>')
            for term in groups[letter]:
                links = self.page_links(term.term_id, pages)
                refs = (', ' + ', '.join(links)) if links else ''
                parts.append(f'<p class="ix"><span class="ix-term">{escape(term.term)}</span>{refs}</p>')
        return ('<h1 class="section-title" id="sec-index">Index</h1><div class="index-body">'
                + ''.join(parts) + '</div>')

    def about_title(self):
        return 'About the Author' if len(self.authors) == 1 else 'About the Authors'

    def about_html(self):
        parts = [f'<h1 class="section-title" id="sec-about">{escape(self.about_title())}</h1>']
        for author in self.authors:
            photo = (f'<img class="author-photo" src="{media_src(author.photo_asset_id)}" '
                     f'alt="{escape(author.name, quote=True)}"/>' if author.photo_asset_id else '')
            role = f'<p class="role">{escape(author.role)}</p>' if (author.role or '').strip() else ''
            bio = str(render_markdown(author.bio or ''))
            parts.append(f'<div class="author" id="au-{author.author_id}">{photo}'
                         f'<h2>{escape(author.name)}</h2>{role}<div class="bio">{bio}</div></div>')
        return ''.join(parts)

    def toc_entries(self):
        """[(anchor, title)] for chapters and the generated back matter, in reading order."""
        entries = [(c['anchor'], c['title']) for c in self.chapters]
        if self.has_glossary():
            entries.append(('sec-glossary', 'Glossary'))
        if self.has_index():
            entries.append(('sec-index', 'Index'))
        if self.has_about():
            entries.append(('sec-about', self.about_title()))
        return entries

    def toc_html(self, toc_pages):
        items = ''.join(
            f'<li><a href="#{anchor}"><span class="toc-title">{escape(title)}</span>'
            f'<span class="toc-page">{toc_pages.get(anchor, "")}</span></a></li>'
            for anchor, title in self.toc_entries())
        return f'<nav class="toc"><h1>Contents</h1><ol>{items}</ol></nav>'

    @property
    def body_start_anchor(self):
        return self.chapters[0]['anchor'] if self.chapters else None
