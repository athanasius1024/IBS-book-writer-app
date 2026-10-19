"""Unit tests for the manuscript conversion used by scripts/import_terran_book.py (no database needed)."""
import importlib.util
from pathlib import Path

import pytest

from ibsbook import render_markdown

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'import_terran_book.py'
spec = importlib.util.spec_from_file_location('import_terran_book', SCRIPT)
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)

MANUSCRIPT = (
    "---\ntitle: \"Terran Society\"\nsubtitle: \"A New Social Contract\"\nauthor: \"A. Author\"\n---\r\n\n"
    "<div class=\"cover-page\">\n\n# Terran Society\n\n**A New Social Contract**\n\n</div>\n\n"
    "<div style='page-break-after: always;'></div>\n\n"
    "<div class=\"dedication-page\">\n\n## Dedication\n\nFor everyone\n\n</div>\n\n"
    "# Terran Society: A New Social Contract\n\n"
    "## Introduction\n\nIntro paragraph with **bold**.\n\n"
    "### Core Objectives\n\nTerran Society exists to:\n\n1. **Protect Rights** – guaranteed\n2. **Meet Needs** – ensured\n\n"
    "### Plain list\n\n- first\n- second\n- third\n\n"
    "<div style='page-break-before: always;'></div>\n\n"
    "## District\n\n**District Level:**\n- Council of Elders\n- Representative\n  - nested item\n\n"
    "#### Right 1\n\nSee [Arbitrator](#glossary-arbitrator) for details.\n\n"
    "<div style='page-break-before: always;'></div>\n\n"
    "## Index\n\n### A\n\n[Arbitrator](#glossary-arbitrator)\n"
)


def test_alnum_ignores_markup_and_punctuation():
    assert imp.alnum('## Hello, **World** – 1.') == imp.alnum('hello world 1')


def test_normalize_adds_blank_line_before_list_and_reindents_nested():
    text = '**District Level:**\n- Council\n- Rep\n  - nested\n  - nested two'
    out = imp.normalize_markdown(text)
    assert out == '**District Level:**\n\n- Council\n- Rep\n    - nested\n    - nested two'


def test_normalize_leaves_already_separated_lists_alone():
    text = 'Intro\n\n- a\n- b'
    assert imp.normalize_markdown(text) == text


def test_normalize_strips_glossary_links():
    assert imp.normalize_markdown('see [Arbitrator](#glossary-arbitrator) now') == 'see Arbitrator now'


def test_normalized_lists_render_as_real_lists():
    html = str(render_markdown(imp.normalize_markdown('**Label:**\n- one\n- two\n  - nested')))
    assert html.count('<ul>') == 2 and '<li>one</li>' in html and '<li>nested</li>' in html


@pytest.mark.parametrize('text,expected', [
    ('- a\n- b', (['a', 'b'], False)),
    ('1. a\n2. b', (['a', 'b'], True)),
    ('- **bold** item\n- b', None),            # markup -> keep as Markdown text
    ('- a\n1. b', None),                       # mixed styles
    ('- a\n    - nested', None),               # nesting
    ('Intro\n- a', None),                      # not only a list
])
def test_as_plain_list(text, expected):
    assert imp.as_plain_list(text) == expected


def test_parse_manuscript_structure():
    front, chapters = imp.parse_manuscript(MANUSCRIPT)
    assert front['subtitle'] == 'A New Social Contract' and front['author'] == 'A. Author'
    assert [title for title, _ in chapters] == ['Introduction', 'District']      # Index and cover/dedication skipped
    intro = dict(chapters)['Introduction']
    assert intro[0][0] == 'text' and 'Intro paragraph' in intro[0][1]['text']
    assert intro[1] == ('heading', {'level': 1, 'text': 'Core Objectives'})
    assert intro[2][0] == 'text'                                                   # label + bold list stays Markdown
    assert intro[3] == ('heading', {'level': 1, 'text': 'Plain list'})
    assert intro[4] == ('list', {'items': ['first', 'second', 'third'], 'ordered': False})
    district = dict(chapters)['District']
    assert district[0][0] == 'text' and 'nested item' in district[0][1]['text']
    assert district[1] == ('heading', {'level': 2, 'text': 'Right 1'})
    assert 'Arbitrator for details' in district[2][1]['text'] and '#glossary' not in district[2][1]['text']


def test_parsed_chapters_reproduce_the_source_text_exactly():
    _, chapters = imp.parse_manuscript(MANUSCRIPT)
    rebuilt = '\n\n'.join(imp.blocks_to_markdown(t, b) for t, b in chapters)
    assert imp.alnum(rebuilt) == imp.alnum(imp.source_markdown(MANUSCRIPT))
    assert 'dedication' not in imp.alnum(rebuilt)       # skipped pages are not part of the body
    assert 'arbitrator' in imp.alnum(rebuilt)           # link text kept, link syntax dropped


def test_verification_detects_lost_text():
    _, chapters = imp.parse_manuscript(MANUSCRIPT)
    title, blocks = chapters[0]
    damaged = [(title, blocks[:-1])] + chapters[1:]
    rebuilt = '\n\n'.join(imp.blocks_to_markdown(t, b) for t, b in damaged)
    assert imp.alnum(rebuilt) != imp.alnum(imp.source_markdown(MANUSCRIPT))


def test_unexpected_heading_levels_are_rejected():
    bad = "# Book\n\n## Chapter\n\n##### Too deep\n\ntext\n"
    with pytest.raises(ValueError):
        imp.parse_manuscript(bad)


def test_dedication_markdown_keeps_stanzas_and_line_breaks():
    out = imp.dedication_markdown('"For all"\r\n\r\nline one\r\nline two\r\nline three',
                                  'Tao Teh Ching #78     Translated by J. Wu')
    assert '\r' not in out
    assert out.split('\n\n')[0] == '"For all"'
    assert out.split('\n\n')[1] == 'line one  \nline two  \nline three'
    assert out.endswith('*Tao Teh Ching #78 - Translated by J. Wu*')
    html = str(render_markdown(out))
    assert html.count('<br') == 2 and '<em>Tao Teh Ching' in html
