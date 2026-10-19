import importlib.util
from pathlib import Path

import pytest

from bookfactory import make_book, make_user
from models import Chapter, ContentBlock, db

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


up = load('upgrade_terran_book')
imp = load('import_terran_book')

DEDICATION = ('"For this and future generations of Terrans"\r\n\r\nNothing in the world is softer\r\n'
              'and weaker than water;\r\nBut, for attacking the hard and strong,\r\nthere is nothing like it!\r\n\r\n'
              'Indeed, Truth sounds like its opposite!')
ATTRIBUTION = 'Tao Teh Ching #78     Translated by John C. H. Wu'
GLOSSARY = [('Arbitration', 'A method of dispute resolution'), ('Arbitrator', 'An elected official'),
            ('World', 'The highest tier')]


def imported_like_book():
    """A book shaped exactly like the one the import script produced."""
    user = make_user('apa')
    book, _ = make_book(user, title='Terran Society', chapters=2, paragraphs=3)
    book.cover('inside_front').content_text = imp.dedication_markdown(DEDICATION, ATTRIBUTION)
    source = 'Term | Definition\n' + '\n'.join(f'{t} | {d}' for t, d in GLOSSARY)
    glossary = Chapter(title='Glossary', sort_order=3)
    glossary.blocks.append(ContentBlock(block_type='table', content_text=source, sort_order=1,
                                        content_data={'header': True, 'rows': [['Term', 'Definition']] +
                                                      [[t, d] for t, d in GLOSSARY]}))
    book.chapters.append(glossary)
    db.session.flush()
    return book


def test_split_inside_front_cover():
    text = imp.dedication_markdown(DEDICATION, ATTRIBUTION)
    dedication, verse, attribution = up.split_inside_front(text)
    assert dedication == '"For this and future generations of Terrans"'
    assert verse.startswith('Nothing in the world is softer\nand weaker than water;')
    assert '  \n' not in verse and verse.endswith('Indeed, Truth sounds like its opposite!')
    assert attribution == 'Tao Teh Ching #78, Translated by John C. H. Wu'


@pytest.mark.parametrize('text', ['', 'only one paragraph', 'one\n\ntwo', 'one\n\ntwo\n\nthree without italics'])
def test_split_refuses_text_that_is_not_the_imported_shape(text):
    with pytest.raises(up.UpgradeError):
        up.split_inside_front(text)


def test_upgrade_moves_everything_and_loses_nothing(app):
    book = imported_like_book()
    original = book.cover('inside_front').content_text
    summary = up.upgrade_book(book, 'Angelo Patrick Arteman', 'Also known as Gerry Carton')
    db.session.flush()

    assert [(p.page_type, p.sort_order) for p in book.pages] == [('dedication', 1), ('quote', 2)]
    dedication, quote = book.pages
    assert dedication.body == '"For this and future generations of Terrans"'
    assert quote.attribution == 'Tao Teh Ching #78, Translated by John C. H. Wu'
    assert up.alnum(dedication.body + quote.body + quote.attribution) == up.alnum(original)
    assert book.cover('inside_front').content_text == ''

    assert sorted((t.term, t.definition) for t in book.terms) == sorted(GLOSSARY)
    assert all(t.match_plural and t.in_index and t.in_glossary and not t.match_case for t in book.terms)
    assert [c.title for c in book.chapters] == ['Chapter 1', 'Chapter 2']
    assert [c.sort_order for c in book.chapters] == [1, 2]
    assert ContentBlock.query.filter_by(block_type='table').count() == 0           # the table block went with it

    author = book.authors[0]
    assert (author.name, author.role, author.bio) == ('Angelo Patrick Arteman', 'Author', 'Also known as Gerry Carton')
    assert summary['terms'] == 3 and summary['chapters_left'] == 2


def test_upgraded_book_renders_with_the_new_sections(app):
    from epub import build_epub
    from render import clear_cache, get_layout
    clear_cache()
    book = imported_like_book()
    book.chapters[0].blocks[0].content_text = 'The World has an Arbitrator. World events matter.'
    up.upgrade_book(book, 'Angelo Patrick Arteman', '')
    db.session.flush()
    result = get_layout(book)
    doc = result.doc
    assert [t.term for t in doc.glossary_terms()] == ['Arbitration', 'Arbitrator', 'World']
    assert {t.term for t in doc.index_terms()} == {'Arbitrator', 'World'}
    assert build_epub(book, result).startswith(b'PK')
    clear_cache()


def test_running_the_upgrade_twice_is_refused_and_changes_nothing(app):
    book = imported_like_book()
    up.upgrade_book(book, 'A', 'bio')
    db.session.flush()
    before = (len(book.pages), len(book.terms), len(book.authors), len(book.chapters))
    with pytest.raises(up.UpgradeError, match='already upgraded'):
        up.upgrade_book(book, 'A', 'bio')
    assert before == (len(book.pages), len(book.terms), len(book.authors), len(book.chapters))


def test_unexpected_shapes_leave_the_book_untouched(app):
    book = imported_like_book()
    book.cover('inside_front').content_text = 'Just a plain sentence.'
    db.session.flush()
    with pytest.raises(up.UpgradeError):
        up.upgrade_book(book, 'A', '')
    assert book.pages == [] and book.terms == [] and book.authors == []
    assert any(c.title == 'Glossary' for c in book.chapters)
    assert book.cover('inside_front').content_text == 'Just a plain sentence.'


def test_a_glossary_chapter_that_is_not_one_table_is_refused(app):
    book = imported_like_book()
    glossary = next(c for c in book.chapters if c.title == 'Glossary')
    glossary.blocks.append(ContentBlock(block_type='text', content_text='An extra paragraph', sort_order=2))
    db.session.flush()
    with pytest.raises(up.UpgradeError, match='not a single table'):
        up.upgrade_book(book, 'A', '')
    assert book.pages == [] and book.terms == []


def test_missing_or_headerless_glossary_is_refused(app):
    book = imported_like_book()
    glossary = next(c for c in book.chapters if c.title == 'Glossary')
    glossary.blocks[0].content_data = {'header': False, 'rows': [['x', 'y']]}
    db.session.flush()
    with pytest.raises(up.UpgradeError, match='header'):
        up.upgrade_book(book, 'A', '')
    book.chapters.remove(glossary)
    db.session.flush()
    with pytest.raises(up.UpgradeError, match='no "Glossary" chapter'):
        up.upgrade_book(book, 'A', '')
