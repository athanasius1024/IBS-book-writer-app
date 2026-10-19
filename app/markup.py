"""Markdown rendering shared by the web UI and the export renderers."""
import re

import bleach
import markdown as md
from markupsafe import Markup

_MD_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'hr', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'sup', 'sub',
]
_MD_ATTRS = {'a': ['href', 'title'], 'abbr': ['title'], 'acronym': ['title']}


def render_markdown(text):
    """Render user markdown to sanitised HTML (raw HTML/script is stripped)."""
    html = md.markdown(text or '', extensions=['extra', 'sane_lists'])
    clean = bleach.clean(html, tags=_MD_TAGS, attributes=_MD_ATTRS,
                         protocols=['http', 'https', 'mailto'], strip=True)
    return Markup(clean)


def render_markdown_lines(text):
    """Like render_markdown, but every single line break in the text stays a line break.

    Used for verse, quotes and dedications, where the author's line endings matter.
    """
    return render_markdown(re.sub(r'(?<!\n)\n(?!\n)', '  \n', (text or '').replace('\r\n', '\n')))
