"""Markdown rendering shared by the web UI and the export renderers."""
import re

import bleach
import markdown as md
from markupsafe import Markup

from imagespec import ASSET_SRC, IMAGE_REF, IMG_CLASSES, parse_crop, parse_width

_MD_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'hr', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'sup', 'sub',
]
_MD_ATTRS = {'a': ['href', 'title'], 'abbr': ['title'], 'acronym': ['title']}

_IMG_TAGS = _MD_TAGS + ['img']
_IMG_PROTOCOLS = ['http', 'https', 'mailto', 'ibs-media']
MAX_IMG_TEXT = 500


def _image_attrs(tag, name, value):
    """Attribute filter when images are allowed: only a media-library source, text, a placement class
    and a valid crop / width survive; links may not point into the media library."""
    if tag == 'a':
        return name == 'title' or (name == 'href' and not value.lower().startswith('ibs-media'))
    if tag in ('abbr', 'acronym'):
        return name == 'title'
    if tag == 'img':
        if name == 'src':
            return bool(ASSET_SRC.match(value))
        if name in ('alt', 'title'):
            return len(value) <= MAX_IMG_TEXT
        if name == 'class':
            return bool(value.split()) and set(value.split()) <= IMG_CLASSES
        if name == 'data-crop':
            return parse_crop(value) is not None
        if name == 'data-w':
            return parse_width(value) is not None
    return False


def render_markdown(text, images=False):
    """Render user markdown to sanitised HTML (raw HTML/script is stripped).

    With images=True, ![text](image:12) picture references are kept as <img src="ibs-media://12">,
    together with their crop / width / placement attributes; see imagespec.py. Anything else that
    would load a picture is stripped. The result still has to go through
    imaging.finalize_inline_images before it is shown.
    """
    text = text or ''
    if images:
        text = IMAGE_REF.sub(r'](ibs-media://\1', text)
    html = md.markdown(text, extensions=['extra', 'sane_lists'])
    if images:
        clean = bleach.clean(html, tags=_IMG_TAGS, attributes=_image_attrs, protocols=_IMG_PROTOCOLS, strip=True)
    else:
        clean = bleach.clean(html, tags=_MD_TAGS, attributes=_MD_ATTRS,
                             protocols=['http', 'https', 'mailto'], strip=True)
    return Markup(clean)


def render_markdown_lines(text):
    """Like render_markdown, but every single line break in the text stays a line break.

    Used for verse, quotes and dedications, where the author's line endings matter.
    """
    return render_markdown(re.sub(r'(?<!\n)\n(?!\n)', '  \n', (text or '').replace('\r\n', '\n')))
