"""The Contents page: the automatic list, a user-edited list, and the version/date stamp.

Every renderer (PDF, EPUB, HTML, ODT) asks BookDoc for `toc_lines()`, which comes from here, so the
Contents agree across formats. A book with no BookTocEntry rows uses the automatic list (one line per
chapter plus the generated back matter). A book with rows uses exactly those rows, in order.
"""
from collections import namedtuple
from html import escape

# anchor is None for a 'part' divider (a label with no link and no page number).
TocLine = namedtuple('TocLine', 'anchor title level kind')

SECTION_ANCHORS = {'glossary': 'sec-glossary', 'index': 'sec-index', 'about': 'sec-about'}


def stamp_text(version, when):
    """'Version 0.3 · Generated October 20, 2026' (small print under the Contents)."""
    return f'Version {version or "0.1"} \u00b7 Generated {when:%B} {when.day}, {when.year}'


def automatic_lines(chapters, sections):
    """chapters: [{'anchor', 'title', ...}]; sections: {'glossary': 'Glossary', ...} (only those present)."""
    lines = [TocLine(c['anchor'], c['title'], 0, 'chapter') for c in chapters]
    lines += [TocLine(SECTION_ANCHORS[key], title, 0, 'section') for key, title in sections.items()]
    return lines


def custom_lines(entries, chapters, headings, sections):
    """The edited list. Hidden entries, entries whose target is gone, and sections the book does not
    have are left out.

    headings: {block_id: heading text} for the book's heading blocks.
    """
    by_chapter = {c['id']: c for c in chapters}
    lines = []
    for entry in entries:
        if not entry.visible:
            continue
        label = (entry.label or '').strip()
        level = entry.level if entry.level in (0, 1, 2) else 0
        if entry.kind == 'chapter':
            chapter = by_chapter.get(entry.chapter_id)
            if chapter is not None:
                lines.append(TocLine(chapter['anchor'], label or chapter['title'], level, 'chapter'))
        elif entry.kind == 'heading':
            title = headings.get(entry.block_id)
            if title is not None:
                lines.append(TocLine(f'b{entry.block_id}', label or title, level, 'heading'))
        elif entry.kind == 'section':
            title = sections.get(entry.section_key)
            if title is not None:
                lines.append(TocLine(SECTION_ANCHORS[entry.section_key], label or title, level, 'section'))
        elif entry.kind == 'part' and label:
            lines.append(TocLine(None, label, level, 'part'))
    return lines


def flat_items_html(lines, toc_pages):
    """<li> items for the printed/web Contents page (indentation by CSS class, parts unlinked)."""
    toc_pages = toc_pages or {}
    items = []
    for line in lines:
        klass = f'toc-l{line.level} toc-{line.kind}'
        title = f'<span class="toc-title">{escape(line.title)}</span>'
        if line.anchor:
            page = toc_pages.get(line.anchor, '')
            items.append(f'<li class="{klass}"><a href="#{line.anchor}">{title}'
                         f'<span class="toc-page">{page}</span></a></li>')
        else:
            items.append(f'<li class="{klass}">{title}</li>')
    return ''.join(items)


class _Node:
    def __init__(self, line):
        self.line = line
        self.children = []


def nested_ol(lines, href_for):
    """A nested <ol> for navigation documents (EPUB nav, HTML sidebar-style Contents).

    Part dividers become a heading span that contains the lines after it, until the next part; levels
    1 and 2 nest under the nearest earlier line of a lower level. `href_for(anchor)` returns the link
    target or None to leave a line out. A part with nothing under it is dropped (an empty list would
    make the navigation document invalid). Returns '' when there is nothing to list.
    """
    root = _Node(None)
    stack = [(-2, root)]
    for line in lines:
        if line.anchor and href_for(line.anchor) is None:
            continue
        depth = -1 if line.kind == 'part' else line.level
        while stack[-1][0] >= depth:
            stack.pop()
        node = _Node(line)
        stack[-1][1].children.append(node)
        stack.append((depth, node))

    def render(children):
        items = []
        for node in children:
            line = node.line
            inner = render(node.children) if node.children else ''
            if line.anchor:
                items.append(f'<li><a href="{escape(href_for(line.anchor), quote=True)}">{escape(line.title)}</a>{inner}</li>')
            elif inner:
                items.append(f'<li><span>{escape(line.title)}</span>{inner}</li>')
        return f'<ol>{"".join(items)}</ol>' if items else ''

    return render(root.children)
