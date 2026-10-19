"""Finding glossary/index terms in rendered book text.

Rules (kept deliberately simple and predictable):
  * whole words only; a hyphenated compound does not match ("world-wide" is not "World")
  * the longest term wins at each position ("World Council of the People" is counted for
    that term and not also for "World")
  * case-insensitive unless the term is marked match-case; optional plural ("Region" matches
    "Regions", "Jury" matches "Juries") and extra variants per term
  * text inside links, code and <pre> is never matched; text inside headings is counted for the
    Index but never turned into a link
  * a term must sit inside one text node, so "**Fair** Witness" (split by markup) is not matched

Every counted match is wrapped so it carries an id ("o<term>-<n>"), which is what page numbers
are looked up by. Glossary-linked matches become <a class="gl" href="#term-<id>">.
"""
import html
import re
from html.parser import HTMLParser

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
SKIP_TAGS = {'a', 'code', 'pre', 'script', 'style'}
HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

LINK_FIRST, LINK_ALL, LINK_NONE = 'first', 'all', 'none'


def _word_pattern(word):
    return re.escape(word)


def _phrase_pattern(phrase, plural):
    """Regex for a phrase with flexible whitespace and an optionally plural last word."""
    words = phrase.split()
    parts = [_word_pattern(w) for w in words]
    last = words[-1]
    if plural:
        if re.search(r'[^aeiouAEIOU\W\d_]y$', last):
            parts[-1] = _word_pattern(last[:-1]) + '(?:y|ies)'
        else:
            parts[-1] = _word_pattern(last) + '(?:e?s)?'
    return r'\s+'.join(parts)


class Matcher:
    """Compiled matcher for a list of BookTerm-like objects (term_id, term, variant_list, ...)."""

    def __init__(self, terms):
        self.terms = {t.term_id: t for t in terms}
        entries = []   # (sort_length, regex_source, term_id)
        for t in terms:
            if not (t.term or '').strip():
                continue
            forms = [(t.term.strip(), bool(t.match_plural))]
            forms += [(v, False) for v in t.variant_list]
            for text, plural in forms:
                source = _phrase_pattern(text, plural)
                if not t.match_case:
                    source = f'(?i:{source})'
                entries.append((len(text), source, t.term_id))
        entries.sort(key=lambda e: -e[0])          # longest first => longest match wins
        self._ids = []
        alternatives = []
        for index, (_, source, term_id) in enumerate(entries):
            alternatives.append(f'(?P<g{index}>{source})')
            self._ids.append(term_id)
        self._regex = (re.compile(r'(?<![\w-])(?:' + '|'.join(alternatives) + r')(?![\w-])')
                       if alternatives else None)

    def term_id_for(self, match):
        return self._ids[int(match.lastgroup[1:])]

    def finditer(self, text):
        if self._regex is None:
            return iter(())
        return self._regex.finditer(text)


class Annotator:
    """Annotates rendered HTML fragments in document order, keeping state across fragments."""

    def __init__(self, matcher, link_mode=LINK_FIRST):
        self.matcher = matcher
        self.link_mode = link_mode
        self.counters = {}          # term_id -> occurrences so far
        self.occurrences = {}       # term_id -> [occurrence ids in document order]
        self._linked_in_chapter = set()

    def start_chapter(self):
        self._linked_in_chapter = set()

    def annotate(self, fragment, linkable=True):
        parser = _Parser(self, linkable)
        parser.feed(fragment)
        parser.close()
        return ''.join(parser.out)

    # -- used by the parser -------------------------------------------------------
    def _wrap(self, match, in_heading, linkable):
        term_id = self.matcher.term_id_for(match)
        term = self.matcher.terms[term_id]
        number = self.counters.get(term_id, 0) + 1
        self.counters[term_id] = number
        occ_id = f'o{term_id}-{number}'
        self.occurrences.setdefault(term_id, []).append(occ_id)
        text = html.escape(match.group(0), quote=False)

        can_link = (linkable and not in_heading and term.has_entry and self.link_mode != LINK_NONE)
        if can_link and self.link_mode == LINK_FIRST and term_id in self._linked_in_chapter:
            can_link = False
        if can_link:
            self._linked_in_chapter.add(term_id)
            return f'<a class="gl" id="{occ_id}" href="#term-{term_id}">{text}</a>'
        return f'<span class="occ" id="{occ_id}">{text}</span>'


class _Parser(HTMLParser):
    def __init__(self, annotator, linkable):
        super().__init__(convert_charrefs=True)
        self.annotator = annotator
        self.linkable = linkable
        self.out = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        self.out.append(self.get_starttag_text())
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        self.out.append(f'</{tag}>')
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_comment(self, data):
        self.out.append(f'<!--{data}-->')

    def handle_data(self, data):
        if any(tag in SKIP_TAGS for tag in self.stack):
            self.out.append(html.escape(data, quote=False))
            return
        in_heading = any(tag in HEADING_TAGS for tag in self.stack)
        position = 0
        for match in self.annotator.matcher.finditer(data):
            self.out.append(html.escape(data[position:match.start()], quote=False))
            self.out.append(self.annotator._wrap(match, in_heading, self.linkable))
            position = match.end()
        self.out.append(html.escape(data[position:], quote=False))


def collapse_pages(pages):
    """[3, 3, 5, 6, 7, 9] -> '3, 5-7, 9' as a list of (first, last) ranges (runs of 3+ become ranges)."""
    unique = sorted(set(pages))
    ranges, start = [], None
    for index, page in enumerate(unique):
        if start is None:
            start = previous = page
        elif page == previous + 1:
            previous = page
        else:
            ranges.append((start, previous))
            start = previous = page
        if index == len(unique) - 1:
            ranges.append((start, previous))
    output = []
    for first, last in ranges:
        if last - first >= 2:
            output.append((first, last))
        else:
            output.extend((p, p) for p in range(first, last + 1))
    return output
