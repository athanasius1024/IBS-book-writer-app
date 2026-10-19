"""Page layout settings (trim size, margins, columns, fonts, numbering...) and the CSS built from them.

Settings are stored as JSON on BookLayout, validated here, and merged over DEFAULTS, so a book with
no saved layout still renders.
"""
import hashlib
import json
import re

PRESETS = {
    '5x8': ('5 x 8 in', 127.0, 203.2),
    '5.5x8.5': ('5.5 x 8.5 in (digest)', 139.7, 215.9),
    '6x9': ('6 x 9 in', 152.4, 228.6),
    'a5': ('A5', 148.0, 210.0),
    'letter': ('US Letter', 215.9, 279.4),
    'custom': ('Custom size', None, None),
}

# key -> (label, CSS font stack). Fonts must exist on the machine that renders the PDF.
FONTS = {
    'serif': ('Serif (Liberation Serif)', '"Liberation Serif", "Times New Roman", Times, serif'),
    'sans': ('Sans-serif (Liberation Sans)', '"Liberation Sans", Arial, Helvetica, sans-serif'),
    'dejavu': ('DejaVu Serif', '"DejaVu Serif", Georgia, serif'),
}

ENUMS = {
    'trim': list(PRESETS),
    'columns': [1, 2],
    'font': list(FONTS),
    'align': ['justify', 'left'],
    'para_style': ['indent', 'space'],
    'page_numbers': ['outside', 'center', 'none'],
    'front_numbering': ['roman', 'none'],
    'running_head': ['none', 'chapter', 'title'],
    'link_mode': ['first', 'all', 'none'],
}
NUMBERS = {
    'width_mm': (80.0, 300.0), 'height_mm': (100.0, 400.0),
    'margin_top': (5.0, 60.0), 'margin_bottom': (5.0, 60.0),
    'margin_inside': (5.0, 60.0), 'margin_outside': (5.0, 60.0),
    'column_gap': (3.0, 20.0), 'font_size': (7.0, 18.0), 'line_height': (1.0, 2.2),
}
BOOLS = ['hyphenate', 'chapter_new_page', 'include_title_page', 'include_contents', 'include_covers']
LANG_RE = re.compile(r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$')

DEFAULTS = {
    'trim': '5.5x8.5', 'width_mm': 139.7, 'height_mm': 215.9,
    'margin_top': 18.0, 'margin_bottom': 20.0, 'margin_inside': 20.0, 'margin_outside': 15.0,
    'columns': 1, 'column_gap': 8.0,
    'font': 'serif', 'font_size': 11.0, 'line_height': 1.4, 'align': 'justify', 'hyphenate': True,
    'para_style': 'indent', 'chapter_new_page': True,
    'page_numbers': 'outside', 'front_numbering': 'roman', 'running_head': 'none',
    'include_title_page': True, 'include_contents': True, 'include_covers': True,
    'link_mode': 'first', 'language': 'en',
}

# Dedication / Quote page styling options
PAGE_STYLE_DEFAULTS = {'align': 'center', 'valign': 'middle', 'italic': True, 'size': 'medium'}
PAGE_STYLE_CHOICES = {'align': ['left', 'center', 'right'], 'valign': ['top', 'middle', 'bottom'],
                      'size': ['small', 'medium', 'large']}


def _clean(settings):
    """Keep only valid values from `settings`, merged over the defaults."""
    out = dict(DEFAULTS)
    for key, value in (settings or {}).items():
        if key in ENUMS and value in ENUMS[key]:
            out[key] = value
        elif key in NUMBERS:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            low, high = NUMBERS[key]
            if low <= number <= high:
                out[key] = number
        elif key in BOOLS and isinstance(value, bool):
            out[key] = value
        elif key == 'language' and isinstance(value, str) and LANG_RE.match(value):
            out[key] = value
    return out


def get_settings(book):
    stored = book.layout.settings if book.layout is not None else None
    return _clean(stored)


def parse_form(form, current):
    """Build settings from a submitted form. Returns (settings, errors)."""
    settings, errors = dict(current), []
    for key, options in ENUMS.items():
        raw = form.get(key)
        if raw is None:
            continue
        value = int(raw) if isinstance(options[0], int) and str(raw).isdigit() else raw
        if value in options:
            settings[key] = value
        else:
            errors.append(f'Invalid value for {key.replace("_", " ")}.')
    for key, (low, high) in NUMBERS.items():
        raw = form.get(key)
        if raw in (None, ''):
            continue
        try:
            number = float(raw)
        except ValueError:
            errors.append(f'{key.replace("_", " ").capitalize()} must be a number.')
            continue
        if not (low <= number <= high):
            errors.append(f'{key.replace("_", " ").capitalize()} must be between {low:g} and {high:g}.')
        else:
            settings[key] = number
    for key in BOOLS:
        settings[key] = key in form
    language = (form.get('language') or settings['language']).strip()
    if LANG_RE.match(language):
        settings['language'] = language
    else:
        errors.append('Language must be a code such as en or en-GB.')

    width, height = page_size_mm(settings)
    if width - settings['margin_inside'] - settings['margin_outside'] < 50:
        errors.append('The margins leave less than 50 mm of text width.')
    if height - settings['margin_top'] - settings['margin_bottom'] < 80:
        errors.append('The margins leave less than 80 mm of text height.')
    return settings, errors


def page_size_mm(settings):
    trim = settings['trim']
    if trim == 'custom':
        return settings['width_mm'], settings['height_mm']
    _, width, height = PRESETS[trim]
    return width, height


def text_area_mm(settings):
    width, height = page_size_mm(settings)
    return (width - settings['margin_inside'] - settings['margin_outside'],
            height - settings['margin_top'] - settings['margin_bottom'])


def settings_hash(settings):
    return hashlib.sha1(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def page_style(raw):
    """Validated dedication/quote page style."""
    style = dict(PAGE_STYLE_DEFAULTS)
    for key, options in PAGE_STYLE_CHOICES.items():
        if (raw or {}).get(key) in options:
            style[key] = raw[key]
    if isinstance((raw or {}).get('italic'), bool):
        style['italic'] = raw['italic']
    return style


def page_style_classes(raw):
    s = page_style(raw)
    return f'align-{s["align"]} valign-{s["valign"]} size-{s["size"]}' + (' italic' if s['italic'] else '')


# ---------------------------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------------------------

_PAGE_STYLE_CSS = """
.fm-page .fm-body p { margin: 0 0 .7em; text-indent: 0; text-align: inherit; }
.fm-page .attribution { margin-top: 1.1em; font-size: .9em; font-style: normal; }
.fm-page.align-left { text-align: left; } .fm-page.align-center { text-align: center; }
.fm-page.align-right { text-align: right; }
.fm-page.italic .fm-body { font-style: italic; }
.fm-page.size-small .fm-body { font-size: .92em; }
.fm-page.size-medium .fm-body { font-size: 1.15em; }
.fm-page.size-large .fm-body { font-size: 1.5em; line-height: 1.35; }
"""

_CONTENT_CSS = """
.blk-heading { margin: 1.3em 0 .5em; break-after: avoid; text-align: left; text-indent: 0; }
h2.blk-heading { font-size: 1.35em; } h3.blk-heading { font-size: 1.15em; } h4.blk-heading { font-size: 1em; font-style: italic; }
.blk ul, .blk ol { margin: .4em 0 .8em; padding-left: 1.6em; text-align: left; }
.blk table { border-collapse: collapse; width: 100%; margin: .6em 0 1em; font-size: .92em; text-align: left; }
.blk th, .blk td { border: .4pt solid #666; padding: 2pt 4pt; vertical-align: top; }
.blk th { background: #eee; }
.blk-figure { margin: .8em 0; text-align: center; break-inside: avoid; }
.blk-figure img { max-width: 100%; }
.blk-figure figcaption { font-size: .85em; font-style: italic; margin-top: .3em; text-indent: 0; }
.blk-icon img { max-width: 16mm; max-height: 16mm; }
.blk blockquote { margin: .8em 1.5em; font-style: italic; }
.gl { color: inherit; text-decoration: none; border-bottom: .5pt dotted #555; }
.glossary dt { font-weight: bold; margin-top: .7em; break-after: avoid; }
.glossary dd { margin: 0 0 0 1.2em; text-align: left; }
.glossary .refs, .ix .refs { font-size: .9em; }
.glossary .refs { display: block; margin-top: .15em; color: #333; }
a.pg { color: inherit; text-decoration: none; }
.ix-letter { font-size: 1.1em; font-weight: bold; margin: .9em 0 .3em; break-after: avoid; text-indent: 0; }
.ix { margin: 0; padding-left: 1.3em; text-indent: -1.3em; text-align: left; break-inside: avoid; }
.author { margin: 0 0 1.5em; overflow: hidden; }
.author-photo { float: left; width: 32mm; margin: 0 4mm 2mm 0; }
.author h2 { margin: 0; font-size: 1.2em; text-indent: 0; text-align: left; }
.author .role { margin: 0 0 .5em; font-style: italic; text-indent: 0; }
"""


def pdf_css(settings, book_title=''):
    width, height = page_size_mm(settings)
    font = FONTS[settings['font']][1]
    top, bottom = settings['margin_top'], settings['margin_bottom']
    inside, outside = settings['margin_inside'], settings['margin_outside']
    text_w, text_h = text_area_mm(settings)
    safe_title = book_title.replace('\\', '\\\\').replace('"', '\\"')

    numbers = settings['page_numbers']

    def number_rules(selector_prefix, counter):
        content = f'counter({counter})'
        if numbers == 'none':
            return ''
        if numbers == 'center':
            return f'@page {selector_prefix} {{ @bottom-center {{ content: {content}; font-size: 9pt; }} }}\n'
        return (f'@page {selector_prefix}:left {{ @bottom-left {{ content: {content}; font-size: 9pt; }} }}\n'
                f'@page {selector_prefix}:right {{ @bottom-right {{ content: {content}; font-size: 9pt; }} }}\n')

    css = [
        f'@page {{ size: {width}mm {height}mm; margin: {top}mm {outside}mm {bottom}mm {inside}mm; }}',
        f'@page :left {{ margin-left: {outside}mm; margin-right: {inside}mm; }}',
        f'@page :right {{ margin-left: {inside}mm; margin-right: {outside}mm; }}',
        # Cover, title/dedication/quote and Contents pages must not advance the body page counter, so the
        # first chapter is page 1. Contents pages count in roman numerals on their own counter.
        '@page cover { margin: 0; counter-increment: page 0; }',
        '@page plain { counter-increment: page 0; }',
        '@page front { counter-increment: page 0 front 1; }',
        number_rules('body', 'page'),
        number_rules('front', 'front, lower-roman') if settings['front_numbering'] == 'roman' else '',
    ]
    if settings['running_head'] == 'chapter':
        css.append('@page body { @top-center { content: string(chap); font-size: 9pt; font-style: italic; } }')
    elif settings['running_head'] == 'title':
        css.append(f'@page body {{ @top-center {{ content: "{safe_title}"; font-size: 9pt; font-style: italic; }} }}')

    align = settings['align']
    css.append(f"""
html {{ font-family: {font}; font-size: {settings['font_size']}pt; line-height: {settings['line_height']}; }}
body {{ margin: 0; text-align: {align}; hyphens: {'auto' if settings['hyphenate'] else 'manual'}; }}
p {{ margin: 0; orphans: 2; widows: 2; }}
""")
    if settings['para_style'] == 'indent':
        css.append('.blk p, .blk li { }\n.blk p { text-indent: 1.4em; } .blk p:first-child, .blk-heading + p, '
                   '.blk-heading ~ .blk p:first-child { text-indent: 0; }')
    else:
        css.append('.blk p { margin: 0 0 .7em; text-indent: 0; }')

    css.append(f"""
section.cover {{ page: cover; break-before: page; width: {width}mm; height: {height - 1}mm; overflow: hidden; }}
.cover-box {{ width: {width}mm; height: {height - 1}mm; box-sizing: border-box; padding: 14mm; display: flex;
    flex-direction: column; justify-content: center; align-items: center; text-align: center; overflow: hidden; }}
.cover-box img {{ max-width: 100%; max-height: 55%; margin-bottom: 6mm; }}
.cover-box p {{ text-indent: 0; text-align: center; }}
.cover-box h1 {{ font-size: 2em; margin: 0 0 .4em; }}
section.titlepage {{ page: plain; break-before: page; height: {text_h - 2}mm; display: flex; flex-direction: column;
    justify-content: center; align-items: center; text-align: center; }}
section.titlepage h1 {{ font-size: 2.2em; margin: 0 0 .3em; }}
section.titlepage .subtitle {{ font-size: 1.3em; margin: 0 0 2em; font-style: italic; text-indent: 0; text-align: center; }}
section.titlepage .byline {{ font-size: 1.15em; text-indent: 0; text-align: center; }}
section.fm-page {{ page: plain; break-before: page; height: {text_h - 2}mm; display: flex; flex-direction: column; }}
section.fm-page.valign-top {{ justify-content: flex-start; }}
section.fm-page.valign-middle {{ justify-content: center; }}
section.fm-page.valign-bottom {{ justify-content: flex-end; }}
section.fm-page.align-left {{ align-items: flex-start; }}
section.fm-page.align-center {{ align-items: center; }}
section.fm-page.align-right {{ align-items: flex-end; }}
section.fm-page .fm-inner {{ max-width: 88%; }}
section.contents {{ page: front; break-before: page; }}
section.contents h1 {{ text-align: center; font-size: 1.6em; margin: 0 0 1.2em; }}
section.contents ol {{ list-style: none; margin: 0; padding: 0; }}
section.contents li {{ margin: 0 0 .45em; }}
section.contents a {{ display: flex; justify-content: space-between; color: inherit; text-decoration: none; }}
section.contents .toc-page {{ padding-left: 1em; }}
section.chapter, section.backmatter {{ page: body; {'break-before: page;' if settings['chapter_new_page'] else ''} }}
section.chapter.first {{ break-before: page; }}
section.backmatter {{ break-before: page; }}
h1.chapter-title {{ font-size: 1.8em; margin: 2.2em 0 1em; text-align: center; text-indent: 0; string-set: chap content();
    bookmark-level: 1; bookmark-label: content(); break-after: avoid; }}
h1.section-title {{ font-size: 1.6em; margin: 2em 0 1em; text-align: center; text-indent: 0; string-set: chap content();
    bookmark-level: 1; bookmark-label: content(); break-after: avoid; }}
.chapter-body {{ column-count: {settings['columns']}; column-gap: {settings['column_gap']}mm; }}
.index-body {{ column-count: 2; column-gap: 8mm; font-size: .9em; }}
""")
    css.append(_CONTENT_CSS)
    css.append(_PAGE_STYLE_CSS)
    return '\n'.join(css)


def epub_css(settings):
    """Stylesheet for the EPUB: relative sizes only, the reader controls page size and font."""
    align = settings['align']
    css = [f"""
body {{ margin: 0 5%; line-height: {settings['line_height']}; text-align: {align}; hyphens: {'auto' if settings['hyphenate'] else 'manual'}; }}
p {{ margin: 0; }}
h1, h2, h3, h4 {{ text-align: left; line-height: 1.2; }}
h1.chapter-title, h1.section-title {{ text-align: center; margin: 2em 0 1em; font-size: 1.7em; page-break-before: always; }}
nav.toc ol {{ list-style: none; padding-left: 0; }}
.cover-box {{ text-align: center; padding: 2em 1em; }}
.cover-box img {{ max-width: 100%; }}
.titlepage {{ text-align: center; margin-top: 25%; }}
.titlepage h1 {{ font-size: 2em; margin-bottom: .3em; text-align: center; }}
.titlepage .subtitle {{ font-style: italic; margin-bottom: 2em; text-indent: 0; text-align: center; }}
.fm-page {{ margin-top: 20%; }}
.fm-page.valign-top {{ margin-top: 2em; }}
.fm-page.valign-bottom {{ margin-top: 40%; }}
.index-body .ix-letter {{ page-break-after: avoid; }}
"""]
    if settings['para_style'] == 'indent':
        css.append('.blk p { text-indent: 1.4em; } .blk p:first-child, .blk-heading + p { text-indent: 0; }')
    else:
        css.append('.blk p { margin: 0 0 .7em; }')
    css.append(_CONTENT_CSS.replace('.author-photo { float: left; width: 32mm; margin: 0 4mm 2mm 0; }',
                                    '.author-photo { float: left; width: 30%; margin: 0 4% 2% 0; }')
               .replace('.blk-icon img { max-width: 16mm; max-height: 16mm; }',
                        '.blk-icon img { max-width: 4em; max-height: 4em; }'))
    css.append(_PAGE_STYLE_CSS)
    return '\n'.join(css)
