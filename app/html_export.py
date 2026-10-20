"""The whole book as ONE self-contained HTML file.

Same sections, Contents (with the version/date stamp), glossary links and Index as the other formats
(they all come from BookDoc). Pictures are embedded as data: URIs and only from the owner's own files,
so the file works on its own: email it, open it offline, or print it from a browser.
"""
import base64
import re
from html import escape

from bookdoc import DERIVED_SCHEME, MEDIA_SCHEME
from imaging import read_image
from layout import FONTS, epub_css
from render import assemble_body

_SRC = re.compile(rf'src="((?:{re.escape(MEDIA_SCHEME)}|{re.escape(DERIVED_SCHEME)})\d+)"')
_EPUB_TYPE = re.compile(r' epub:type="[^"]*"')

_SCREEN_CSS = """
html { background: #f3f1ec; }
body { max-width: 42em; margin: 2rem auto; padding: 2rem clamp(1rem, 5vw, 3.5rem); background: #fff;
       box-shadow: 0 0 .6rem rgba(0, 0, 0, .15); font-family: %(font)s; font-size: 1.05rem; line-height: %(line)s; }
img { max-width: 100%%; height: auto; }
section { margin: 0 0 3rem; }
section.cover, section.titlepage { text-align: center; }
nav.toc a { display: block; }
a.gl { text-decoration: none; border-bottom: 1px dotted #777; color: inherit; }
@media print {
  html, body { background: #fff; box-shadow: none; max-width: none; margin: 0; padding: 0; }
  section.cover, section.titlepage, section.fm-page, section.contents, section.chapter, section.backmatter { page-break-before: always; }
  a { color: inherit; text-decoration: none; }
}
"""


def _embed_pictures(html, user_id):
    """Replace library picture sources by data: URIs (pictures that cannot be read are dropped)."""
    cache = {}

    def embed(match):
        src = match.group(1)
        if src not in cache:
            found = read_image(src, user_id)
            cache[src] = (f'src="data:{found[1]};base64,{base64.b64encode(found[0]).decode("ascii")}"'
                          if found else 'src=""')
        return cache[src]

    return _SRC.sub(embed, html)


def build_html(book, result):
    """The book as UTF-8 HTML bytes. `result` is the cached layout result (it supplies the document and
    the printed page numbers that the Index and Glossary refer to)."""
    doc = result.doc
    s = doc.settings
    body = assemble_body(doc, result.pages, {})
    body = _embed_pictures(_EPUB_TYPE.sub('', body), book.user_id)
    css = epub_css(s) + _SCREEN_CSS % {'font': FONTS[s['font']][1], 'line': s['line_height']}
    byline = escape(doc.byline(), quote=True)
    html = (f'<!DOCTYPE html>\n<html lang="{s["language"]}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="generator" content="IBS Book Writer">\n'
            f'<meta name="author" content="{byline}">\n'
            f'<title>{escape(doc.title)}</title>\n<style>{css}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')
    return html.encode('utf-8')
