from types import SimpleNamespace

import pytest

from terms import Annotator, Matcher, collapse_pages


def term(term_id, text, definition='A definition', variants='', plural=True, case=False,
         in_index=True, in_glossary=True):
    t = SimpleNamespace(term_id=term_id, term=text, definition=definition, variants=variants,
                        match_plural=plural, match_case=case, in_index=in_index, in_glossary=in_glossary)
    t.variant_list = [v.strip() for v in variants.splitlines() if v.strip()]
    t.has_entry = bool(in_glossary and (definition or '').strip())
    return t


def annotate(terms, fragment, mode='first'):
    annotator = Annotator(Matcher(terms), link_mode=mode)
    return annotator.annotate(fragment), annotator


def test_whole_words_only_and_hyphenated_compounds_do_not_match():
    out, ann = annotate([term(1, 'World')], '<p>The World, world-wide, Worldly and a sub-World.</p>')
    assert out.count('id="o1-') == 1 and ann.occurrences == {1: ['o1-1']}
    assert '>World</a>,' in out                                   # the real term is linked
    assert 'world-wide, Worldly and a sub-World.' in out         # compounds are left untouched


def test_hyphen_and_longer_word_are_left_alone():
    out, ann = annotate([term(1, 'World')], '<p>world-wide Worldly pre-world</p>')
    assert ann.occurrences == {}
    assert out == '<p>world-wide Worldly pre-world</p>'


def test_longest_term_wins_at_a_position():
    terms = [term(1, 'World'), term(2, 'World Council of the People')]
    _, ann = annotate(terms, '<p>The World Council of the People and the World.</p>')
    assert len(ann.occurrences[2]) == 1 and len(ann.occurrences[1]) == 1


def test_plural_and_y_plural_and_extra_variants():
    terms = [term(1, 'Region'), term(2, 'Jury'), term(3, 'Elder', variants='Council Member\nElders\' Council')]
    _, ann = annotate(terms, '<p>Regions, a Jury, two juries, Elders and a Council Member.</p>')
    assert len(ann.occurrences[1]) == 1
    assert len(ann.occurrences[2]) == 2
    assert len(ann.occurrences[3]) == 2          # Elders (plural) + variant


def test_plural_can_be_switched_off():
    _, ann = annotate([term(1, 'Region', plural=False)], '<p>Region and Regions</p>')
    assert len(ann.occurrences[1]) == 1


def test_match_case():
    _, ann = annotate([term(1, 'World', case=True)], '<p>World and world and WORLD</p>')
    assert len(ann.occurrences[1]) == 1
    _, ann = annotate([term(1, 'World', case=False)], '<p>World and world and WORLD</p>')
    assert len(ann.occurrences[1]) == 3


def test_possessive_and_multiword_whitespace():
    _, ann = annotate([term(1, 'Fair Witness')], '<p>The Fair Witness\'s role and a fair\n   witness.</p>')
    assert len(ann.occurrences[1]) == 2


def test_special_characters_in_terms_are_literal():
    _, ann = annotate([term(1, 'C++'), term(2, 'a.b')], '<p>I like C++ and a.b but not aXb.</p>')
    assert len(ann.occurrences[1]) == 1 and len(ann.occurrences[2]) == 1


def test_unicode_terms():
    _, ann = annotate([term(1, 'caf\u00e9')], '<p>Un caf\u00e9, deux Caf\u00e9s.</p>')
    assert len(ann.occurrences[1]) == 2


def test_links_code_and_pre_are_never_matched():
    out, ann = annotate([term(1, 'World')],
                        '<p><a href="#x">World</a> <code>World</code></p><pre>World</pre><p>World</p>')
    assert len(ann.occurrences[1]) == 1
    assert out.count('<a class="gl"') == 1


def test_headings_are_indexed_but_never_linked():
    out, ann = annotate([term(1, 'World')], '<h2>The World</h2><p>World</p>')
    assert len(ann.occurrences[1]) == 2
    heading, paragraph = out.split('</h2>')
    assert '<span class="occ" id="o1-1">World</span>' in heading and 'href' not in heading
    assert '<a class="gl"' in paragraph


def test_link_modes():
    fragment = '<p>World World</p>'
    first, _ = annotate([term(1, 'World')], fragment, 'first')
    assert first.count('<a class="gl"') == 1 and first.count('class="occ"') == 1
    every, _ = annotate([term(1, 'World')], fragment, 'all')
    assert every.count('<a class="gl"') == 2
    none, _ = annotate([term(1, 'World')], fragment, 'none')
    assert none.count('<a class="gl"') == 0 and none.count('class="occ"') == 2


def test_first_use_link_restarts_in_each_chapter():
    annotator = Annotator(Matcher([term(1, 'World')]), 'first')
    annotator.start_chapter()
    one = annotator.annotate('<p>World</p>')
    two = annotator.annotate('<p>World</p>')
    annotator.start_chapter()
    three = annotator.annotate('<p>World</p>')
    assert '<a class="gl"' in one and '<a class="gl"' not in two and '<a class="gl"' in three
    assert annotator.occurrences[1] == ['o1-1', 'o1-2', 'o1-3']


def test_terms_without_a_glossary_entry_are_indexed_but_not_linked():
    out, ann = annotate([term(1, 'World', definition=''), term(2, 'Region', in_glossary=False)],
                        '<p>World Region</p>', 'all')
    assert '<a ' not in out and len(ann.occurrences) == 2


def test_markup_inside_a_term_is_not_matched_but_surrounding_text_is_kept_intact():
    fragment = '<p><strong>Fair</strong> Witness and Fair Witness</p>'
    out, ann = annotate([term(1, 'Fair Witness')], fragment)
    assert len(ann.occurrences[1]) == 1
    assert out.startswith('<p><strong>Fair</strong> Witness and ')


def test_text_is_escaped_and_attributes_are_untouched():
    out, ann = annotate([term(1, 'AT&T')], '<p title="a &amp; b">AT&amp;T <b>x &lt; y</b></p>')
    assert 'title="a &amp; b"' in out
    assert '>AT&amp;T</a>' in out and 'x &lt; y' in out


def test_no_terms_leaves_html_untouched():
    out, ann = annotate([], '<p>Anything <b>here</b></p>')
    assert out == '<p>Anything <b>here</b></p>' and ann.occurrences == {}


@pytest.mark.parametrize('pages,expected', [
    ([], []),
    ([3], [(3, 3)]),
    ([3, 3, 3], [(3, 3)]),
    ([5, 3, 9], [(3, 3), (5, 5), (9, 9)]),
    ([3, 4], [(3, 3), (4, 4)]),                    # two consecutive pages stay separate
    ([3, 4, 5], [(3, 5)]),                         # three or more become a range
    ([1, 2, 3, 4, 7, 9, 10, 11], [(1, 4), (7, 7), (9, 11)]),
])
def test_collapse_pages(pages, expected):
    assert collapse_pages(pages) == expected
