"""The book as an OpenDocument Text (.odt) file, written straight from the book document.

It opens in LibreOffice, Word, Google Docs and other editors, and is meant to be edited, so it reflows:
the Contents lists links (no page numbers), and the Index and Glossary point at the chapters where a term
is used instead of at printed pages that an editor would change. Everything else (covers, title page,
front matter, Contents with its version/date stamp, chapters with epigraphs, tables, lists, pictures with
their crop and size, Glossary, Index, About the Author) comes from the same BookDoc as the PDF and EPUB.
"""
import io
import re
import zipfile
from html import escape
from html.parser import HTMLParser

from PIL import Image

from bookdoc import cover_has_content, cover_html
from imaging import read_image
from layout import FONTS, page_size_mm, text_area_mm

FIXED_TIME = (2020, 1, 1, 0, 0, 0)
ODT_MIME = 'application/vnd.oasis.opendocument.text'
NAMESPACES = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"')
PX_TO_MM = 25.4 / 96
EXTENSION = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif'}
BLOCK_TAGS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table', 'pre', 'blockquote', 'hr',
              'figure', 'div', 'section', 'nav', 'dl', 'dt', 'dd', 'body', 'html', 'header', 'footer', 'article'}
SPAN_STYLES = {'em': 'T_Emph', 'i': 'T_Emph', 'strong': 'T_Strong', 'b': 'T_Strong', 'code': 'T_Code', 'kbd': 'T_Code',
               'samp': 'T_Code', 'tt': 'T_Code', 'sup': 'T_Sup', 'sub': 'T_Sub', 'del': 'T_Del', 's': 'T_Del',
               'strike': 'T_Del', 'u': 'T_Under'}


def _x(text):
    """Escape text for XML content."""
    return escape(text, quote=False)


def _q(text):
    """Escape text for an XML attribute value."""
    return escape(text, quote=True)


def _mm(value):
    return f'{value:.2f}mm'


class _Document:
    """Collects the body, the on-demand automatic styles and the embedded pictures."""

    def __init__(self, doc, user_id):
        self.doc = doc
        self.settings = doc.settings
        self.user_id = user_id
        self.text_w, self.text_h = text_area_mm(doc.settings)
        self.body = []
        self.auto_styles = {}          # key -> (name, xml)
        self.pictures = {}             # src -> (file name, mime, bytes, width px, height px) or None
        self.picture_files = []        # (file name, mime, bytes) in order of first use
        self.tables = 0
        self.frames = 0
        self.seen_ids = set()

    # -- styles made when first needed (paragraph styles that differ from a named style) --------------
    def pstyle(self, parent, align=None, italic=None, size=None, brk=False, indent_zero=False, keep_next=False):
        """Name of a paragraph style that is `parent` plus the given changes (or `parent` itself)."""
        key = (parent, align, italic, size, brk, indent_zero, keep_next)
        if not any(key[1:]):
            return parent
        if key not in self.auto_styles:
            name = f'P{len(self.auto_styles) + 1}'
            paragraph, text = [], []
            if align:
                paragraph.append(f'fo:text-align="{ {"left": "start", "right": "end"}.get(align, align) }"')
            if brk:
                paragraph.append('fo:break-before="page"')
            if indent_zero:
                paragraph.append('fo:text-indent="0cm"')
            if keep_next:
                paragraph.append('fo:keep-with-next="always"')
            if italic is not None:
                text.append(f'fo:font-style="{"italic" if italic else "normal"}"')
            if size:
                text.append(f'fo:font-size="{size}%"')
            xml = (f'<style:style style:name="{name}" style:family="paragraph" style:parent-style-name="{parent}">'
                   + (f'<style:paragraph-properties {" ".join(paragraph)}/>' if paragraph else '')
                   + (f'<style:text-properties {" ".join(text)}/>' if text else '') + '</style:style>')
            self.auto_styles[key] = (name, xml)
        return self.auto_styles[key][0]

    def extra_style(self, key, xml_for_name):
        if key not in self.auto_styles:
            name = f'A{len(self.auto_styles) + 1}'
            self.auto_styles[key] = (name, xml_for_name(name))
        return self.auto_styles[key][0]

    # -- pictures -------------------------------------------------------------------------------------
    def picture(self, src):
        """(file name, width px, height px) for a library picture owned by the book's author, else None."""
        if src not in self.pictures:
            entry = None
            found = read_image(src, self.user_id)
            if found:
                data, mime = found
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        width, height = image.size
                        if mime not in EXTENSION:                       # e.g. WebP: convert to PNG
                            buffer = io.BytesIO()
                            image.convert('RGBA').save(buffer, 'PNG')
                            data, mime = buffer.getvalue(), 'image/png'
                except Exception:
                    data = None
                if data is not None and width > 0 and height > 0:
                    name = f'img{len(self.picture_files) + 1}.{EXTENSION[mime]}'
                    entry = (name, mime, data, width, height)
                    self.picture_files.append((name, mime, data))
            self.pictures[src] = entry
        entry = self.pictures[src]
        return (entry[0], entry[3], entry[4]) if entry else None

    def frame(self, src, alt, width_mm=None, width_pct=None, max_pct=100, max_height_mm=None):
        """XML for an as-character frame holding the picture, or '' if it is unavailable."""
        found = self.picture(src)
        if found is None:
            return ''
        name, w_px, h_px = found
        natural = w_px * PX_TO_MM
        width = width_mm or (self.text_w * width_pct / 100 if width_pct else min(natural, self.text_w * max_pct / 100))
        width = min(width, self.text_w)
        height = width * h_px / w_px
        limit = max_height_mm or self.text_h * 0.85
        if height > limit:
            width, height = width * limit / height, limit
        self.frames += 1
        title = f'<svg:title>{_x(alt)}</svg:title>' if alt else ''
        return (f'<draw:frame draw:style-name="Fr" draw:name="Image{self.frames}" text:anchor-type="as-char" '
                f'svg:width="{_mm(width)}" svg:height="{_mm(height)}" draw:z-index="0">'
                f'<draw:image xlink:href="Pictures/{name}" xlink:type="simple" xlink:show="embed" '
                f'xlink:actuate="onLoad"/>{title}</draw:frame>')


class _Converter(HTMLParser):
    """Writes the HTML that BookDoc produces (a small, known subset) as ODF text, appending to `out`."""

    def __init__(self, document, break_first=True):
        super().__init__(convert_charrefs=True)
        self.d = document
        self.out = document.body
        self.stack = []                 # (html tag, text to emit when it ends)
        self.ctx = []                   # contexts that choose default paragraph styles
        self.p_close = None             # '</text:p>' or '</text:h>' while a paragraph or heading is open
        self.fresh = False              # nothing written in the open paragraph yet
        self.pre = 0
        self.skip = 0
        self.skip_text = 0              # inside an empty page-number span
        self.pending_break = break_first
        self.pending_bookmarks = []
        self.lists = []                 # 'bullet' / 'number' per open list
        self.figure = None
        self.table = None               # {'rows': [(is_header, [cell xml])], 'row': [...] or None, 'in_head': bool, ...}

    # ---- paragraphs and headings ----------------------------------------------------------------
    def open_block(self, style, heading=None, **changes):
        self.close_block()
        brk = self.pending_break
        self.pending_break = False
        style = self.d.pstyle(style, brk=brk, **changes)
        if heading:
            self.out.append(f'<text:h text:style-name="{style}" text:outline-level="{heading}">')
            self.p_close = '</text:h>'
        else:
            self.out.append(f'<text:p text:style-name="{style}">')
            self.p_close = '</text:p>'
        self.fresh = True
        for name in self.pending_bookmarks:
            self.out.append(f'<text:bookmark text:name="{_q(name)}"/>')
        self.pending_bookmarks = []

    def close_block(self):
        if self.p_close:
            self.out.append(self.p_close)
            self.p_close = None

    def bookmark(self, name):
        if not name or name in self.d.seen_ids:
            return
        self.d.seen_ids.add(name)
        if self.p_close:
            self.out.append(f'<text:bookmark text:name="{_q(name)}"/>')
        else:
            self.pending_bookmarks.append(name)

    def context_style(self):
        """Default paragraph style for text found here, from the innermost context that has an opinion."""
        for ctx in reversed(self.ctx):
            kind = ctx['kind']
            if kind == 'cell':
                return 'Table_20_Heading' if ctx.get('head') else 'Table_20_Contents', {}
            if kind == 'li':
                return 'List_20_Body', {}
            if kind == 'quote':
                return 'Quotations', {}
            if kind == 'epigraph':
                return 'Epigraph', {'align': ctx['align'], 'italic': ctx['italic'], 'size': ctx['size']}
            if kind == 'fm':
                return 'Front_20_Matter', {'align': ctx['align'], 'italic': ctx['italic'], 'size': ctx['size']}
            if kind == 'cover':
                return 'Cover_20_Text', {}
            if kind == 'dd':
                return 'Glossary_20_Definition', {}
        return 'Text_20_body', {}

    def ensure_paragraph(self):
        if not self.p_close:
            style, changes = self.context_style()
            self.open_block(style, **changes)

    def write_text(self, data):
        if self.skip or self.skip_text:
            return
        if self.pre:
            self.ensure_paragraph()
            self.out.append(self._preformatted(data))
            self.fresh = False
            return
        data = re.sub(r'\s+', ' ', data)
        if not self.p_close:
            data = data.lstrip()
            if not data:
                return
            self.ensure_paragraph()
        if self.fresh:
            data = data.lstrip()
            if not data:
                return
        self.fresh = False
        self.out.append(_x(data))

    @staticmethod
    def _preformatted(data):
        pieces = []
        for line_number, line in enumerate(data.replace('\r\n', '\n').split('\n')):
            if line_number:
                pieces.append('<text:line-break/>')
            for chunk in re.split(r'(\t| {2,})', line):
                if chunk == '\t':
                    pieces.append('<text:tab/>')
                elif chunk.startswith('  '):
                    pieces.append(f'<text:s text:c="{len(chunk)}"/>')
                else:
                    pieces.append(_x(chunk))
        return ''.join(pieces)

    # ---- HTML events ----------------------------------------------------------------------------------
    def handle_data(self, data):
        self.write_text(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('br', 'img', 'hr'):
            self.handle_endtag(tag)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or '') for k, v in attrs}
        classes = set(a.get('class', '').split())
        closer = ''
        if tag in ('style', 'script', 'head', 'title'):
            self.skip += 1
            self.stack.append((tag, ''))
            return
        if self.skip:
            self.stack.append((tag, ''))
            return
        if tag in BLOCK_TAGS and tag != 'li':
            self.close_block()                      # a block element never lives inside an open paragraph

        if tag == 'br':
            self.ensure_paragraph()
            self.out.append('<text:line-break/>')
            return
        if tag == 'hr':
            self.open_block('Horizontal_20_Line')
            self.close_block()
            return
        if tag == 'img':
            self._image(a, classes)
            return

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._heading(tag, a, classes)
            self.stack.append((tag, ''))
            return
        if tag == 'p':
            self._paragraph(a, classes)
            self.stack.append((tag, ''))
            return
        if tag in ('ul', 'ol'):
            if self._in_ctx('toc'):
                self.stack.append((tag, ''))
                return
            self.lists.append('number' if tag == 'ol' else 'bullet')
            self.out.append(f'<text:list text:style-name="{"L_Number" if tag == "ol" else "L_Bullet"}">')
            self.stack.append((tag, '</text:list>'))
            return
        if tag == 'li':
            self._list_item(a, classes)
            return
        if tag == 'pre':
            self.pre += 1
            self.open_block('Preformatted_20_Text')
            self.stack.append((tag, ''))
            return
        if tag == 'blockquote':
            if 'epigraph' in classes:
                settings = self.d.settings
                self.ctx.append({'kind': 'epigraph', 'align': settings['epigraph_align'],
                                 'italic': bool(settings['epigraph_italic']),
                                 'size': {'small': 92, 'medium': 105, 'large': 120}[settings['epigraph_size']]})
            else:
                self.ctx.append({'kind': 'quote'})
            self.stack.append((tag, 'ctx'))
            return
        if tag == 'figure':
            align = next((c[4:] for c in classes if c in ('img-left', 'img-right', 'img-center')), 'center')
            width = re.search(r'width:\s*(\d+)%', a.get('style', ''))
            self.figure = {'align': align, 'width': int(width.group(1)) if width else None, 'icon': 'blk-icon' in classes,
                           'framed': False}
            self.stack.append((tag, 'figure'))
            return
        if tag == 'figcaption':
            self.open_block('Illustration')
            self.stack.append((tag, ''))
            return
        if tag == 'table':
            self._table_start()
            self.stack.append((tag, 'table'))
            return
        if tag in ('thead', 'tbody'):
            if self.table is not None:
                self.table['in_head'] = tag == 'thead'
            self.stack.append((tag, ''))
            return
        if tag == 'tr':
            if self.table is not None:
                self.table['row'] = []
            self.stack.append((tag, 'tr'))
            return
        if tag in ('td', 'th'):
            self._cell_start(tag)
            self.stack.append((tag, 'cell'))
            return
        if tag == 'dl':
            self.stack.append((tag, ''))
            return
        if tag == 'dt':
            self.bookmark(a.get('id'))
            self.open_block('Glossary_20_Term')
            self.stack.append((tag, ''))
            return
        if tag == 'dd':
            self.ctx.append({'kind': 'dd'})
            self.stack.append((tag, 'ctx'))
            return

        # transparent containers that matter for context or anchors
        if tag in ('div', 'section', 'nav', 'header', 'footer', 'article', 'body', 'html'):
            if tag == 'nav' and 'toc' in classes:
                self.ctx.append({'kind': 'toc'})
                closer = 'ctx'
            elif 'cover-box' in classes:
                self.ctx.append({'kind': 'cover'})
                closer = 'ctx'
            elif 'fm-page' in classes:
                self.ctx.append({'kind': 'fm', 'align': next((c[6:] for c in classes if c.startswith('align-')), 'center'),
                                 'italic': 'italic' in classes,
                                 'size': {'small': 92, 'medium': 115, 'large': 150}.get(
                                     next((c[5:] for c in classes if c.startswith('size-')), 'medium'), 115)})
                closer = 'ctx'
            self.bookmark(a.get('id'))
            self.stack.append((tag, closer))
            return

        # inline
        if tag == 'a':
            href = a.get('href', '')
            if href.startswith('#'):
                target = href
            elif re.match(r'^(https?|mailto):', href, re.I):
                target = href
            else:
                target = ''
            if target:
                self.ensure_paragraph()
                style = ('T_Gloss' if 'gl' in classes else 'T_Plain' if (self._in_ctx('toc') or 'pg' in classes)
                         else 'Internet_20_link')
                self.out.append(f'<text:a xlink:type="simple" xlink:href="{_q(target)}" text:style-name="{style}" '
                                f'text:visited-style-name="{style}">')
                self.bookmark(a.get('id'))
                self.stack.append((tag, '</text:a>'))
            else:
                self.stack.append((tag, ''))
            return
        if tag in SPAN_STYLES:
            self.ensure_paragraph()
            self.out.append(f'<text:span text:style-name="{SPAN_STYLES[tag]}">')
            self.stack.append((tag, '</text:span>'))
            return
        if tag == 'span':
            if 'toc-page' in classes:
                self.skip_text += 1
                self.stack.append((tag, 'skiptext'))
                return
            if 'refs' in classes:
                self.ensure_paragraph()
                self.out.append('<text:span text:style-name="T_Refs">')
                self.bookmark(a.get('id'))
                self.stack.append((tag, '</text:span>'))
                return
            if a.get('id'):
                self.ensure_paragraph()
                self.bookmark(a.get('id'))
            self.stack.append((tag, ''))
            return
        self.stack.append((tag, ''))

    def handle_endtag(self, tag):
        if not self.stack:
            return
        # close up to the matching start tag (HTML from our own builders is well-formed, this is a safety net)
        while self.stack:
            open_tag, closer = self.stack.pop()
            self._finish(open_tag, closer)
            if open_tag == tag:
                break

    def _finish(self, tag, closer):
        if tag in ('style', 'script', 'head', 'title'):
            self.skip -= 1
            return
        if self.skip:
            return
        if closer == 'skiptext':
            self.skip_text -= 1
            return
        if closer == 'ctx':
            self.close_block()
            self.ctx.pop()
            return
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'figcaption', 'dt'):
            self.close_block()
            if tag == 'pre':
                self.pre -= 1
            return
        if tag in ('ul', 'ol'):
            if closer:
                self.close_block()
                self.out.append(closer)
                self.lists.pop()
            return
        if tag == 'li':
            self.close_block()
            if closer:
                self.out.append(closer)
                self.ctx.pop()
            return
        if closer == 'figure':
            self.close_block()
            self.figure = None
            return
        if closer == 'table':
            self._table_end()
            return
        if closer == 'tr':
            self._row_end()
            return
        if closer == 'cell':
            self._cell_end()
            return
        if tag in ('div', 'section', 'nav', 'header', 'footer', 'article', 'dl', 'dd', 'blockquote'):
            self.close_block()
            return
        if closer:
            self.out.append(closer)

    def close(self):
        super().close()
        self.close_block()
        while self.table is not None:             # a table left open by malformed input
            self._table_end()

    # ---- element handlers ---------------------------------------------------------------------------
    def _in_ctx(self, kind):
        return any(ctx['kind'] == kind for ctx in self.ctx)

    def _heading(self, tag, a, classes):
        if self._in_ctx('toc'):
            self.bookmark(a.get('id'))
            self.open_block('Contents_20_Title')
            return
        if self._in_ctx('cover'):
            self.open_block('Cover_20_Title')
        elif 'chapter-title' in classes or 'section-title' in classes:
            self.open_block('Heading_20_1', heading=1)
        elif 'ix-letter' in classes:
            self.open_block('Index_20_Letter')
        elif tag == 'h1':
            self.open_block('Title')
        else:
            level = min(int(tag[1]), 4)
            self.open_block(f'Heading_20_{level}', heading=level)
        self.bookmark(a.get('id'))

    def _paragraph(self, a, classes):
        ctx_style, changes = self.context_style()
        if 'attribution' in classes:
            fm = next((c for c in reversed(self.ctx) if c['kind'] == 'fm'), {'align': 'center'})
            self.open_block('Attribution', align=fm['align'])
        elif 'epigraph-source' in classes:
            ep = next((c for c in reversed(self.ctx) if c['kind'] == 'epigraph'), None)
            self.open_block('Epigraph_20_Source', align=ep['align'] if ep else 'end')
        elif 'toc-stamp' in classes:
            self.open_block('Toc_20_Stamp')
        elif 'subtitle' in classes:
            self.open_block('Subtitle')
        elif 'byline' in classes:
            self.open_block('Byline')
        elif 'role' in classes:
            self.open_block('Role')
        elif 'ix' in classes:
            self.open_block('Index_20_Entry')
        else:
            self.open_block(ctx_style, **changes)
        self.bookmark(a.get('id'))

    def _list_item(self, a, classes):
        if self._in_ctx('toc'):
            level = next((int(c[5:]) for c in classes if re.fullmatch(r'toc-l\d', c)), 0)
            self.bookmark(a.get('id'))
            self.open_block('Contents_20_Part' if 'toc-part' in classes else f'Contents_20_{min(level, 2) + 1}')
            self.stack.append(('li', ''))
            return
        self.close_block()
        self.out.append('<text:list-item>')
        self.ctx.append({'kind': 'li'})
        self.stack.append(('li', '</text:list-item>'))

    def _image(self, a, classes):
        src, alt = a.get('src', ''), a.get('alt', '')
        style = a.get('style', '')
        width = re.search(r'width:\s*(\d+)%', style)
        if self.figure is not None:
            fig = self.figure
            if fig['icon']:
                xml = self.d.frame(src, alt, max_height_mm=16, width_mm=min(16, self.d.text_w))
            else:
                xml = self.d.frame(src, alt, width_pct=fig['width'])
            if not xml:
                return                                  # the picture cannot be read: leave it out
            style_name = {'left': 'Figure_20_Left', 'right': 'Figure_20_Right'}.get(fig['align'], 'Figure_20_Center')
            self.open_block(style_name)
            self.out.append(xml)
            self.fresh = False
            self.close_block()
            return
        if 'author-photo' in classes:
            xml = self.d.frame(src, alt, width_mm=min(30, self.d.text_w), max_height_mm=45)
        elif self._in_ctx('cover'):
            xml = self.d.frame(src, alt, max_pct=70, max_height_mm=self.d.text_h * 0.5)
        else:
            xml = self.d.frame(src, alt, width_pct=int(width.group(1)) if width else None)
        if xml:
            self.ensure_paragraph()
            self.out.append(xml)
            self.fresh = False

    # ---- tables ---------------------------------------------------------------------------------
    # Each cell is written into its own buffer, so a row can be padded and the column count known at the end.
    def _table_start(self):
        self.close_block()
        self.table = {'rows': [], 'row': None, 'in_head': False, 'cell_saved': None}

    def _cell_start(self, tag):
        table = self.table
        if table is None:
            return
        self.close_block()
        self.ctx.append({'kind': 'cell', 'head': tag == 'th'})
        table['cell_saved'] = self.out
        self.out = []

    def _cell_end(self):
        table = self.table
        self.close_block()
        if table is None or table['cell_saved'] is None:
            return
        xml = ''.join(self.out)
        self.out = table['cell_saved']
        table['cell_saved'] = None
        self.ctx.pop()
        if table['row'] is not None:
            table['row'].append('<table:table-cell office:value-type="string" table:style-name="Cell">'
                                + xml + '</table:table-cell>')

    def _row_end(self):
        table = self.table
        if table is not None and table['row'] is not None:
            table['rows'].append((table['in_head'], table['row']))
            table['row'] = None

    def _table_end(self):
        table = self.table
        if table is None:
            return
        if table['cell_saved'] is not None:                 # unfinished cell in malformed input
            self._cell_end()
        self.close_block()
        self.table = None
        rows = table['rows']
        if not rows:
            return
        columns = max(len(cells) for _, cells in rows) or 1
        blank = ('<table:table-cell office:value-type="string" table:style-name="Cell">'
                 '<text:p text:style-name="Table_20_Contents"/></table:table-cell>')
        xml_rows = [(head, '<table:table-row>' + ''.join(cells) + blank * (columns - len(cells)) + '</table:table-row>')
                    for head, cells in rows]
        lead = 0
        while lead < len(xml_rows) and xml_rows[lead][0]:   # header rows are the ones at the top
            lead += 1
        body = ''.join(x for _, x in xml_rows[lead:])
        if lead:
            body = '<table:table-header-rows>' + ''.join(x for _, x in xml_rows[:lead]) + '</table:table-header-rows>' + body
        self.d.tables += 1
        self.out.append(f'<table:table table:name="Table{self.d.tables}" table:style-name="Tbl">'
                        f'<table:table-column table:number-columns-repeated="{columns}"/>{body}</table:table>')
        self.fresh = False


def _first_font(stack):
    return stack.split(',')[0].strip().strip('"')


def _list_style(name, bullet):
    levels = []
    for level in range(1, 6):
        indent = 6 + level * 6
        if bullet:
            levels.append(
                f'<text:list-level-style-bullet text:level="{level}" text:bullet-char="\u2022">'
                f'<style:list-level-properties text:list-level-position-and-space-mode="label-alignment">'
                f'<style:list-level-label-alignment text:label-followed-by="listtab" text:list-tab-stop-position="{indent}mm" '
                f'fo:text-indent="-5mm" fo:margin-left="{indent}mm"/></style:list-level-properties></text:list-level-style-bullet>')
        else:
            levels.append(
                f'<text:list-level-style-number text:level="{level}" style:num-suffix="." style:num-format="1">'
                f'<style:list-level-properties text:list-level-position-and-space-mode="label-alignment">'
                f'<style:list-level-label-alignment text:label-followed-by="listtab" text:list-tab-stop-position="{indent}mm" '
                f'fo:text-indent="-6mm" fo:margin-left="{indent}mm"/></style:list-level-properties></text:list-level-style-number>')
    return f'<text:list-style style:name="{name}">{"".join(levels)}</text:list-style>'


def _styles_xml(doc):
    s = doc.settings
    width, height = page_size_mm(s)
    font = _first_font(FONTS[s['font']][1])
    size = s['font_size']
    line = int(round(s['line_height'] * 100))
    justify = 'justify' if s['align'] == 'justify' else 'start'
    indent = '5mm' if s['para_style'] == 'indent' else '0mm'
    gap = '0mm' if s['para_style'] == 'indent' else '2.5mm'
    lang = s['language'].split('-')[0]
    country = s['language'].split('-')[1] if '-' in s['language'] else None
    country_attr = f' fo:country="{country}"' if country and len(country) == 2 else ''
    numbers = s['page_numbers'] != 'none'

    def para(name, display, parent='Standard', klass='text', para_props='', text_props='', next_style=None, extra=''):
        nxt = f' style:next-style-name="{next_style}"' if next_style else ''
        base = f' style:parent-style-name="{parent}"' if parent else ''
        return (f'<style:style style:name="{name}" style:display-name="{display}" style:family="paragraph"{base}{nxt} '
                f'style:class="{klass}"{extra}>'
                + (f'<style:paragraph-properties {para_props}/>' if para_props else '')
                + (f'<style:text-properties {text_props}/>' if text_props else '') + '</style:style>')

    def text(name, display, props):
        return (f'<style:style style:name="{name}" style:display-name="{display}" style:family="text">'
                f'<style:text-properties {props}/></style:style>')

    styles = [
        f'<style:default-style style:family="paragraph"><style:paragraph-properties fo:hyphenation-ladder-count="no-limit" '
        f'style:writing-mode="page"/><style:text-properties style:font-name="Body" fo:font-size="{size}pt" '
        f'fo:language="{lang}"{country_attr} fo:hyphenate="{"true" if s["hyphenate"] else "false"}"/></style:default-style>',
        '<style:style style:name="Standard" style:family="paragraph" style:class="text"/>',
        para('Text_20_body', 'Text body', klass='text',
             para_props=f'fo:margin-top="0mm" fo:margin-bottom="{gap}" fo:line-height="{line}%" fo:text-align="{justify}" '
                        f'fo:text-indent="{indent}" fo:orphans="2" fo:widows="2"'),
        para('List_20_Body', 'List body', parent='Text_20_body', klass='list',
             para_props='fo:text-indent="0mm" fo:text-align="start"'),
        para('Table_20_Contents', 'Table contents', parent='Text_20_body', klass='extra',
             para_props='fo:text-indent="0mm" fo:text-align="start" fo:margin-bottom="0mm"'),
        para('Table_20_Heading', 'Table heading', parent='Table_20_Contents', klass='extra',
             text_props='fo:font-weight="bold"'),
        para('Quotations', 'Quotations', parent='Text_20_body', klass='html',
             para_props='fo:margin-left="10mm" fo:margin-right="10mm" fo:text-indent="0mm"', text_props='fo:font-style="italic"'),
        para('Preformatted_20_Text', 'Preformatted Text', klass='html',
             para_props='fo:margin-top="2mm" fo:margin-bottom="2mm" fo:text-align="start" fo:orphans="1" fo:widows="1"',
             text_props='style:font-name="Mono" fo:font-size="90%" fo:hyphenate="false"'),
        para('Horizontal_20_Line', 'Horizontal Line', klass='html',
             para_props='fo:margin-top="3mm" fo:margin-bottom="3mm" fo:border-bottom="0.5pt solid #666666" fo:padding="0mm"',
             text_props='fo:font-size="6pt"'),
        para('Illustration', 'Illustration', klass='extra',
             para_props='fo:margin-top="1mm" fo:margin-bottom="4mm" fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="85%" fo:font-style="italic"'),
        para('Heading', 'Heading', klass='text', para_props='fo:keep-with-next="always" fo:text-align="start" fo:text-indent="0mm"',
             text_props='fo:font-weight="bold"', next_style='Text_20_body'),
        para('Heading_20_1', 'Heading 1', parent='Heading', klass='text',
             para_props='fo:margin-top="30mm" fo:margin-bottom="10mm" fo:text-align="center"', text_props='fo:font-size="180%"',
             extra=' style:default-outline-level="1"'),
        para('Heading_20_2', 'Heading 2', parent='Heading', klass='text',
             para_props='fo:margin-top="6mm" fo:margin-bottom="3mm"', text_props='fo:font-size="135%"',
             extra=' style:default-outline-level="2"'),
        para('Heading_20_3', 'Heading 3', parent='Heading', klass='text',
             para_props='fo:margin-top="5mm" fo:margin-bottom="2mm"', text_props='fo:font-size="115%"',
             extra=' style:default-outline-level="3"'),
        para('Heading_20_4', 'Heading 4', parent='Heading', klass='text',
             para_props='fo:margin-top="4mm" fo:margin-bottom="2mm"', text_props='fo:font-size="100%" fo:font-style="italic"',
             extra=' style:default-outline-level="4"'),
        para('Title', 'Title', parent='Heading', klass='chapter',
             para_props='fo:margin-top="50mm" fo:margin-bottom="6mm" fo:text-align="center"', text_props='fo:font-size="220%"'),
        para('Subtitle', 'Subtitle', klass='chapter',
             para_props='fo:margin-bottom="12mm" fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="130%" fo:font-style="italic"'),
        para('Byline', 'Byline', klass='chapter', para_props='fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="115%"'),
        para('Role', 'Role', parent='Text_20_body', klass='text', para_props='fo:text-indent="0mm" fo:margin-bottom="2mm"',
             text_props='fo:font-style="italic"'),
        para('Cover_20_Title', 'Cover Title', parent='Heading', klass='chapter',
             para_props='fo:margin-top="10mm" fo:margin-bottom="6mm" fo:text-align="center"', text_props='fo:font-size="200%"'),
        para('Cover_20_Text', 'Cover Text', klass='chapter',
             para_props='fo:text-align="center" fo:text-indent="0mm" fo:margin-bottom="4mm"'),
        para('Front_20_Matter', 'Front Matter', klass='text',
             para_props='fo:margin-top="0mm" fo:margin-bottom="3mm" fo:text-indent="0mm" fo:line-height="130%"',
             text_props='fo:font-size="115%"'),
        para('Attribution', 'Attribution', parent='Front_20_Matter', klass='text',
             para_props='fo:margin-top="5mm"', text_props='fo:font-size="90%" fo:font-style="normal"'),
        para('Epigraph', 'Epigraph', klass='text',
             para_props='fo:margin-left="25mm" fo:margin-right="0mm" fo:margin-bottom="1mm" fo:text-indent="0mm" fo:line-height="120%"'),
        para('Epigraph_20_Source', 'Epigraph Source', parent='Epigraph', klass='text',
             para_props='fo:margin-bottom="8mm" fo:margin-top="1mm"', text_props='fo:font-size="85%" fo:font-style="normal"'),
        para('Figure_20_Center', 'Figure Center', klass='extra',
             para_props='fo:text-align="center" fo:text-indent="0mm" fo:margin-top="3mm" fo:margin-bottom="0mm" fo:keep-with-next="always"'),
        para('Figure_20_Left', 'Figure Left', parent='Figure_20_Center', klass='extra', para_props='fo:text-align="start"'),
        para('Figure_20_Right', 'Figure Right', parent='Figure_20_Center', klass='extra', para_props='fo:text-align="end"'),
        para('Contents_20_Title', 'Contents Title', klass='index',
             para_props='fo:margin-top="10mm" fo:margin-bottom="8mm" fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="160%" fo:font-weight="bold"'),
        para('Contents_20_1', 'Contents 1', klass='index', para_props='fo:margin-bottom="1.5mm" fo:text-indent="0mm"'),
        para('Contents_20_2', 'Contents 2', parent='Contents_20_1', klass='index', para_props='fo:margin-left="7mm"'),
        para('Contents_20_3', 'Contents 3', parent='Contents_20_1', klass='index',
             para_props='fo:margin-left="14mm"', text_props='fo:font-size="95%"'),
        para('Contents_20_Part', 'Contents Part', parent='Contents_20_1', klass='index',
             para_props='fo:margin-top="4mm"', text_props='fo:font-weight="bold"'),
        para('Toc_20_Stamp', 'Contents Stamp', klass='index',
             para_props='fo:margin-top="12mm" fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="7.5pt" fo:color="#555555"'),
        para('Glossary_20_Term', 'Glossary Term', klass='index',
             para_props='fo:margin-top="3mm" fo:margin-bottom="0mm" fo:text-indent="0mm" fo:keep-with-next="always"',
             text_props='fo:font-weight="bold"'),
        para('Glossary_20_Definition', 'Glossary Definition', klass='index',
             para_props='fo:margin-left="6mm" fo:margin-bottom="1mm" fo:text-indent="0mm"'),
        para('Index_20_Letter', 'Index Letter', klass='index',
             para_props='fo:margin-top="5mm" fo:margin-bottom="2mm" fo:keep-with-next="always" fo:text-indent="0mm"',
             text_props='fo:font-size="115%" fo:font-weight="bold"'),
        para('Index_20_Entry', 'Index Entry', klass='index',
             para_props='fo:margin-left="6mm" fo:text-indent="-6mm" fo:margin-bottom="0.5mm"'),
        para('Footer', 'Footer', klass='extra', para_props='fo:text-align="center" fo:text-indent="0mm"',
             text_props='fo:font-size="9pt"'),
        text('T_Emph', 'Emphasis', 'fo:font-style="italic"'),
        text('T_Strong', 'Strong Emphasis', 'fo:font-weight="bold"'),
        text('T_Code', 'Source Text', 'style:font-name="Mono" fo:font-size="90%"'),
        text('T_Sup', 'Superscript', 'style:text-position="super 58%"'),
        text('T_Sub', 'Subscript', 'style:text-position="sub 58%"'),
        text('T_Del', 'Strikethrough', 'style:text-line-through-style="solid"'),
        text('T_Under', 'Underline', 'style:text-underline-style="solid" style:text-underline-width="auto" '
                                     'style:text-underline-color="font-color"'),
        text('T_Refs', 'References', 'fo:font-size="90%"'),
        text('T_Gloss', 'Glossary Link', 'style:text-underline-style="dotted" style:text-underline-width="auto" '
                                         'style:text-underline-color="font-color"'),
        text('T_Plain', 'Plain Link', 'fo:color="#000000"'),
        text('Internet_20_link', 'Internet link', 'fo:color="#0645ad" style:text-underline-style="solid" '
                                                  'style:text-underline-width="auto" style:text-underline-color="font-color"'),
        '<style:style style:name="Fr" style:family="graphic"><style:graphic-properties text:anchor-type="as-char" '
        'style:vertical-pos="top" style:vertical-rel="baseline" fo:margin-top="0mm" fo:margin-bottom="0mm" '
        'style:wrap="none"/></style:style>',
        _list_style('L_Bullet', True), _list_style('L_Number', False),
    ]
    footer = ''
    footer_style = ''
    if numbers:
        footer = ('<style:footer><text:p text:style-name="Footer"><text:page-number text:select-page="current">1'
                  '</text:page-number></text:p></style:footer>')
        footer_style = '<style:footer-style><style:header-footer-properties fo:min-height="0mm" fo:margin-top="4mm"/></style:footer-style>'
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-styles {NAMESPACES} office:version="1.3">'
            f'<office:font-face-decls>{_font_faces(font)}</office:font-face-decls>'
            f'<office:styles>{"".join(styles)}</office:styles>'
            f'<office:automatic-styles><style:page-layout style:name="Mpm1" style:page-usage="mirrored">'
            f'<style:page-layout-properties fo:page-width="{_mm(width)}" fo:page-height="{_mm(height)}" '
            f'style:print-orientation="portrait" fo:margin-top="{_mm(s["margin_top"])}" '
            f'fo:margin-bottom="{_mm(s["margin_bottom"])}" fo:margin-left="{_mm(s["margin_inside"])}" '
            f'fo:margin-right="{_mm(s["margin_outside"])}" style:writing-mode="lr-tb"/>'
            f'{footer_style}</style:page-layout></office:automatic-styles>'
            f'<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="Mpm1">{footer}'
            f'</style:master-page></office:master-styles></office:document-styles>')


def _font_faces(font):
    return (f'<style:font-face style:name="Body" svg:font-family="&apos;{_q(font)}&apos;" style:font-family-generic="roman" '
            f'style:font-pitch="variable"/>'
            '<style:font-face style:name="Mono" svg:font-family="&apos;Liberation Mono&apos;" '
            'style:font-family-generic="modern" style:font-pitch="fixed"/>')


def _glossary_and_index(doc):
    """HTML for the Glossary and Index, pointing at chapters (an editable document has no fixed pages)."""
    occurrence_chapter = {}
    for chapter in doc.chapters:
        for occurrence in re.findall(r'\bid="(o\d+-\d+)"', chapter['html']):
            occurrence_chapter[occurrence] = chapter

    def references(term_id):
        seen, links = set(), []
        for occurrence in doc.annotator.occurrences.get(term_id, []):
            chapter = occurrence_chapter.get(occurrence)
            if chapter is not None and chapter['id'] not in seen:
                seen.add(chapter['id'])
                links.append(f'<a class="pg" href="#{occurrence}">{escape(chapter["title"])}</a>')
        return links

    parts = []
    if doc.has_glossary():
        entries = []
        for term in doc.glossary_terms():
            links = references(term.term_id)
            refs = (f' <span class="refs">({"; ".join(links)})</span>' if links else '')
            entries.append(f'<dt id="term-{term.term_id}">{escape(term.term)}</dt>'
                           f'<dd>{escape(term.definition.strip())}{refs}</dd>')
        parts.append(('<h1 class="section-title" id="sec-glossary">Glossary</h1><dl>' + ''.join(entries) + '</dl>'))
    if doc.has_index():
        groups = {}
        for term in doc.index_terms():
            letter = next((c.upper() for c in term.term if c.isalpha()), '#')
            groups.setdefault(letter, []).append(term)
        body = ['<h1 class="section-title" id="sec-index">Index</h1>']
        for letter in sorted(groups):
            body.append(f'<h2 class="ix-letter">{escape(letter)}</h2>')
            for term in groups[letter]:
                links = references(term.term_id)
                body.append(f'<p class="ix">{escape(term.term)}{": " + ", ".join(links) if links else ""}</p>')
        parts.append(''.join(body))
    return parts


def _meta_xml(book, doc):
    stamp = doc.generated_at.replace(microsecond=0).isoformat()
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-meta {NAMESPACES} office:version="1.3"><office:meta>'
            f'<dc:title>{_x(doc.title)}</dc:title><dc:creator>{_x(doc.byline())}</dc:creator>'
            f'<dc:language>{_x(doc.settings["language"])}</dc:language>'
            f'<meta:generator>IBS Book Writer</meta:generator><meta:creation-date>{stamp}</meta:creation-date>'
            f'<dc:date>{stamp}</dc:date></office:meta></office:document-meta>')


def _manifest_xml(pictures):
    entries = [f'<manifest:file-entry manifest:full-path="/" manifest:version="1.3" manifest:media-type="{ODT_MIME}"/>']
    for name in ('content.xml', 'styles.xml', 'meta.xml'):
        entries.append(f'<manifest:file-entry manifest:full-path="{name}" manifest:media-type="text/xml"/>')
    for name, mime, _ in pictures:
        entries.append(f'<manifest:file-entry manifest:full-path="Pictures/{name}" manifest:media-type="{mime}"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<manifest:manifest '
            'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
            + ''.join(entries) + '</manifest:manifest>')


def build_odt(book, result):
    """The book as .odt bytes. `result` is the layout result (it supplies the BookDoc)."""
    doc = result.doc
    s = doc.settings
    document = _Document(doc, book.user_id)
    sections = []                                     # (html, break_before)

    if s['include_covers']:
        for panel in ('front', 'inside_front'):
            if cover_has_content(doc.cover(panel)):
                sections.append((f'<div class="cover-box">{_cover_inner(doc.cover(panel))}</div>', True))
    if s['include_title_page']:
        sections.append((f'<div class="titlepage">{doc.title_html()}</div>', True))
    for page in doc.front_pages:
        sections.append((f'<div class="fm-page {page.classes}" id="{page.anchor}">{page.html}</div>', True))
    if s['include_contents'] and doc.has_contents():
        sections.append((doc.toc_html(), True))
    for chapter in doc.chapters:
        sections.append((chapter['html'], True))
    for html in _glossary_and_index(doc):
        sections.append((html, True))
    if doc.has_about():
        sections.append((doc.about_html(), True))
    if s['include_covers']:
        for panel in ('inside_back', 'back'):
            if cover_has_content(doc.cover(panel)):
                sections.append((f'<div class="cover-box">{_cover_inner(doc.cover(panel))}</div>', True))

    for index, (html, brk) in enumerate(sections):
        converter = _Converter(document, break_first=brk and index > 0)
        converter.feed(html)
        converter.close()

    automatic = ''.join(xml for _, xml in document.auto_styles.values()) + (
        f'<style:style style:name="Tbl" style:family="table"><style:table-properties style:width="{_mm(document.text_w)}" '
        f'table:align="margins" fo:margin-top="2mm" fo:margin-bottom="4mm"/></style:style>'
        '<style:style style:name="Cell" style:family="table-cell"><style:table-cell-properties fo:padding="1mm" '
        'fo:border="0.5pt solid #666666"/></style:style>')
    content = (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-content {NAMESPACES} office:version="1.3">'
               f'<office:font-face-decls>{_font_faces(_first_font(FONTS[s["font"]][1]))}</office:font-face-decls>'
               f'<office:automatic-styles>{automatic}</office:automatic-styles>'
               f'<office:body><office:text>{"".join(document.body)}</office:text></office:body></office:document-content>')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        info = zipfile.ZipInfo('mimetype', FIXED_TIME)            # first entry, stored, not compressed
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, ODT_MIME)

        def write(name, data, compress=True):
            entry = zipfile.ZipInfo(name, FIXED_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
            archive.writestr(entry, data)

        write('content.xml', content)
        write('styles.xml', _styles_xml(doc))
        write('meta.xml', _meta_xml(book, doc))
        for name, _, data in document.picture_files:
            write(f'Pictures/{name}', data, compress=False)
        write('META-INF/manifest.xml', _manifest_xml(document.picture_files))
    return buffer.getvalue()


def _cover_inner(cover):
    """Inner HTML of a cover panel (picture and Markdown text); its colours are not carried over."""
    return re.sub(r'^<div class="cover-box"[^>]*>|</div>$', '', cover_html(cover).strip())
