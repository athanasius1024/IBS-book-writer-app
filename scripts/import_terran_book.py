#!/usr/bin/env python3
"""Import the "Terran Society" book into IBS Book Writer.

Sources
  * the generated manuscript (Markdown) from the original terran-society-book-manager app
  * the original PostgreSQL database (read-only): dedication, copyright data and the glossary

What it creates (all in ONE transaction - everything or nothing)
  * a user account (password taken from the environment, never from a file)
  * a draft book with a five-panel cover (the dedication goes on the inside front cover)
  * one chapter per "##" section of the manuscript (the generated Index is skipped) plus a
    Glossary chapter holding a table of every term and definition
  * headings (### / ####) become Heading blocks, plain bullet/numbered lists become List
    blocks, everything else stays Markdown Text blocks

Before committing, the script proves that no text was lost, duplicated or reordered by
comparing the letters/digits of the source against what was stored in the database.

Usage (passwords come from the environment so they never appear in files or history):
    IBS_IMPORT_PASSWORD=... TERRAN_DB_PASSWORD=... \\
        .venv/bin/python scripts/import_terran_book.py --dry-run     # parse + verify, write nothing
    IBS_IMPORT_PASSWORD=... TERRAN_DB_PASSWORD=... \\
        .venv/bin/python scripts/import_terran_book.py               # do it
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))

DEFAULT_MANUSCRIPT = ('/media/infodine/LaCie/z_stash/z-terran/TerranSocietyBook/infobuild/'
                      'book/manuscript.md')

PAGE_BREAK = re.compile(r"^<div style='page-break-[a-z]+: always;'></div>\s*$")
GLOSSARY_LINK = re.compile(r'\[([^\]]+)\]\(#glossary-[^)]+\)')
HEADING = re.compile(r'^(#{3,4})\s+(.*\S)\s*$')
LIST_ITEM = re.compile(r'^( *)([-*+]|\d+\.)\s+(.*)$')
PLAIN_LIST_ITEM = re.compile(r'^([-*+]|\d+\.)\s+(\S.*)$')
MARKDOWN_SPECIALS = re.compile(r'[*_`\[<\\]')


# ---------------------------------------------------------------------------
# Markdown conversion (pure functions - unit tested)
# ---------------------------------------------------------------------------

def alnum(text):
    """Letters and digits only, lower-cased: used to prove no content changed."""
    return re.sub(r'[\W_]+', '', text, flags=re.UNICODE).lower()


def normalize_markdown(text):
    """Make hand-written Markdown render correctly with Python-Markdown.

    * [term](#glossary-x) cross-references become plain text (the app has no glossary anchors)
    * nested list items indented by 2 spaces are re-indented to 4
    * a list that directly follows a paragraph gets the blank line Python-Markdown requires
    """
    text = GLOSSARY_LINK.sub(r'\1', text)
    out = []
    previous_is_list = False
    for line in text.split('\n'):
        match = LIST_ITEM.match(line)
        if match:
            indent = len(match.group(1))
            if indent:
                line = ' ' * (4 * ((indent + 1) // 2)) + line.lstrip(' ')
            if out and out[-1].strip() and not previous_is_list:
                out.append('')
            previous_is_list = True
        elif line.strip():
            if not (previous_is_list and line.startswith((' ', '\t'))):   # list continuation
                previous_is_list = False
        else:
            # a blank line ends the "directly follows" window but not an open list
            pass
        out.append(line)
    return '\n'.join(out).strip('\n')


def as_plain_list(text):
    """Return (items, ordered) if `text` is nothing but one flat, markup-free list, else None."""
    lines = [line for line in text.split('\n') if line.strip()]
    if not lines:
        return None
    items, styles = [], set()
    for line in lines:
        match = PLAIN_LIST_ITEM.match(line)
        if not match or MARKDOWN_SPECIALS.search(match.group(2)):
            return None
        items.append(match.group(2).strip())
        styles.add(match.group(1)[0].isdigit())
    if len(styles) != 1:
        return None
    return items, styles.pop()


def run_to_block(run_lines):
    """Turn a run of non-heading lines into a ('list'|'text', payload) block, or None."""
    text = normalize_markdown('\n'.join(run_lines))
    if not text.strip():
        return None
    plain = as_plain_list(text)
    if plain:
        items, ordered = plain
        return ('list', {'items': items, 'ordered': ordered})
    return ('text', {'text': text})


def parse_manuscript(raw):
    """Return (front_matter dict, [(chapter_title, [blocks])]) from the manuscript text.

    Blocks are tuples: ('heading', {'level': 1|2, 'text': ..}), ('list', {...}), ('text', {...}).
    """
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    front = {}
    match = re.match(r'^---\n(.*?)\n---\n', raw, re.S)
    if match:
        for line in match.group(1).split('\n'):
            key, _, value = line.partition(':')
            front[key.strip()] = value.strip().strip('"')
        raw = raw[match.end():]

    lines = raw.split('\n')
    h1 = [i for i, line in enumerate(lines) if line.startswith('# ')]
    if not h1:
        raise ValueError('No top-level "# " heading found in the manuscript.')
    lines = lines[h1[-1] + 1:]          # everything after the main-title heading (cover/dedication pages come before)

    chapters, title, chapter_lines = [], None, []

    def close_chapter():
        if title is not None:
            chapters.append((title, chapter_lines[:]))

    for line in lines:
        if PAGE_BREAK.match(line):
            continue
        heading = re.match(r'^## (.*\S)\s*$', line)
        if heading:
            close_chapter()
            title, chapter_lines = heading.group(1), []
        elif title is not None:
            chapter_lines.append(line)
    close_chapter()

    parsed = []
    for chapter_title, body in chapters:
        if chapter_title.strip().lower() == 'index':
            continue                    # generated list of links to glossary anchors
        blocks, run = [], []

        def flush():
            block = run_to_block(run)
            if block:
                blocks.append(block)
            run.clear()

        for line in body:
            heading = HEADING.match(line)
            if heading:
                flush()
                blocks.append(('heading', {'level': len(heading.group(1)) - 2,
                                           'text': GLOSSARY_LINK.sub(r'\1', heading.group(2))}))
            elif re.match(r'^#{1,2}\s|^#{5,}\s', line):
                raise ValueError(f'Unexpected heading inside chapter "{chapter_title}": {line!r}')
            else:
                run.append(line)
        flush()
        parsed.append((chapter_title, blocks))
    return front, parsed


def blocks_to_markdown(chapter_title, blocks):
    """Rebuild Markdown from blocks (used only to verify nothing was lost)."""
    parts = [f'## {chapter_title}']
    for kind, data in blocks:
        if kind == 'heading':
            parts.append('#' * (data['level'] + 2) + ' ' + data['text'])
        elif kind == 'list':
            marker = (lambda n: f'{n}.') if data['ordered'] else (lambda n: '-')
            parts.append('\n'.join(f'{marker(n)} {item}' for n, item in enumerate(data['items'], 1)))
        elif kind == 'text':
            parts.append(data['text'])
    return '\n\n'.join(parts)


def source_markdown(raw):
    """The same chapters straight from the file, minus page breaks, Index and glossary link syntax."""
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    match = re.match(r'^---\n(.*?)\n---\n', raw, re.S)
    if match:
        raw = raw[match.end():]
    lines = raw.split('\n')
    h1 = [i for i, line in enumerate(lines) if line.startswith('# ')]
    lines = [line for line in lines[h1[-1] + 1:] if not PAGE_BREAK.match(line)]
    text = GLOSSARY_LINK.sub(r'\1', '\n'.join(lines))
    sections = re.split(r'(?m)^## ', text)
    kept = [s for s in sections if s.strip() and not s.split('\n', 1)[0].strip().lower() == 'index']
    return '\n\n'.join('## ' + s for s in kept)


def dedication_markdown(dedication, attribution):
    """Dedication verse as Markdown: stanza breaks kept, verse lines joined with hard line breaks."""
    text = (dedication or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    rendered = ['  \n'.join(line.rstrip() for line in p.split('\n')) for p in paragraphs]
    if attribution and attribution.strip():
        rendered.append('*' + re.sub(r'\s{2,}', ' - ', attribution.strip()) + '*')
    return '\n\n'.join(rendered)


# ---------------------------------------------------------------------------
# Database work
# ---------------------------------------------------------------------------

def read_terran_db():
    """Read dedication/copyright/glossary from the original database (read-only session)."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get('TERRAN_DB_HOST', 'localhost'),
        port=os.environ.get('TERRAN_DB_PORT', '5432'),
        dbname=os.environ.get('TERRAN_DB_NAME', 'db_terran_society'),
        user=os.environ.get('TERRAN_DB_USER', 'rock'),
        password=os.environ.get('TERRAN_DB_PASSWORD', ''),
        options='-c default_transaction_read_only=on',   # guarantees nothing is written there
    )
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT subtitle, copyright_holder, copyright_year, dedication_text, '
                        'dedication_attribution, current_version FROM scm_terran_society.book_metadata LIMIT 1')
            meta = dict(zip(('subtitle', 'copyright_holder', 'copyright_year', 'dedication_text',
                             'dedication_attribution', 'current_version'), cur.fetchone()))
            cur.execute('SELECT term, definition FROM scm_terran_society.glossary_entry '
                        'WHERE is_active ORDER BY lower(term), term')
            glossary = [(t.strip(), (d or '').strip()) for t, d in cur.fetchall()]
    finally:
        conn.close()
    return meta, glossary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manuscript', default=DEFAULT_MANUSCRIPT)
    parser.add_argument('--username', default='APA')
    parser.add_argument('--title', default='Terran Society')
    parser.add_argument('--author', default='Angelo Patrick Arteman')
    parser.add_argument('--dry-run', action='store_true', help='parse and verify, then roll back')
    args = parser.parse_args()

    password = os.environ.get('IBS_IMPORT_PASSWORD')
    if not password or len(password) < 8:
        sys.exit('Set IBS_IMPORT_PASSWORD (8+ characters) in the environment.')

    raw = Path(args.manuscript).read_text(encoding='utf-8')
    front, chapters = parse_manuscript(raw)
    meta, glossary = read_terran_db()
    if not glossary:
        sys.exit('The glossary came back empty - refusing to continue.')

    # --- verification of the parse, before touching the target database -------------------
    rebuilt = '\n\n'.join(blocks_to_markdown(t, b) for t, b in chapters)
    if alnum(rebuilt) != alnum(source_markdown(raw)):
        sys.exit('VERIFY FAILED: parsed chapters do not match the source manuscript text.')
    print(f'parse verified: {len(chapters)} chapters, source text identical (letters/digits)')

    from ibsbook import create_app
    from blocks import parse_table
    from models import Book, Chapter, ContentBlock, User, db

    app = create_app()
    with app.app_context():
        url = db.engine.url
        print(f'target database: {url.drivername}://{url.host}/{url.database}')
        if url.drivername.split('+')[0] != 'postgresql' or url.database != 'db_ibs_bookwriter':
            sys.exit('Refusing to run: target is not the db_ibs_bookwriter PostgreSQL database.')

        username_key = args.username.strip().lower()
        if User.query.filter_by(username_key=username_key).first():
            sys.exit(f'User "{args.username}" already exists - nothing was changed.')

        user = User(username=args.username.strip(), username_key=username_key, is_admin=False)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        book = Book(owner=user, title=args.title, subtitle=meta['subtitle'] or front.get('subtitle'),
                    author_name=args.author, copyright_holder=meta['copyright_holder'],
                    copyright_year=meta['copyright_year'], version=meta['current_version'] or '0.1')
        db.session.add(book)
        book.init_covers()
        dedication = dedication_markdown(meta['dedication_text'], meta['dedication_attribution'])
        if dedication:
            book.cover('inside_front').content_text = dedication

        for order, (title, blocks) in enumerate(chapters, start=1):
            chapter = Chapter(title=title, sort_order=order)
            book.chapters.append(chapter)
            for position, (kind, data) in enumerate(blocks, start=1):
                if kind == 'heading':
                    block = ContentBlock(block_type='heading', content_text=data['text'],
                                         content_data={'level': data['level']}, sort_order=position)
                elif kind == 'list':
                    block = ContentBlock(block_type='list', content_text='\n'.join(data['items']),
                                         content_data={'ordered': data['ordered']}, sort_order=position)
                else:
                    block = ContentBlock(block_type='text', content_text=data['text'], sort_order=position)
                chapter.blocks.append(block)

        # Glossary chapter: one table (Term | Definition) with a header row.
        source = 'Term | Definition\n' + '\n'.join(f'{t} | {d}' for t, d in glossary)
        glossary_chapter = Chapter(title='Glossary', sort_order=len(chapters) + 1)
        glossary_chapter.blocks.append(ContentBlock(
            block_type='table', content_text=source, sort_order=1,
            content_data={'header': True, 'rows': parse_table(source)}))
        book.chapters.append(glossary_chapter)

        db.session.flush()
        book_id = book.book_id

        # --- verification against what the database now holds ------------------------------
        db.session.expire_all()
        stored = db.session.get(Book, book_id)
        stored_chapters = [(c.title, [b for b in c.blocks]) for c in stored.chapters]
        stored_rebuilt = []
        for title, blocks in stored_chapters[:-1]:
            converted = []
            for b in blocks:
                if b.block_type == 'heading':
                    converted.append(('heading', {'level': b.content_data['level'], 'text': b.content_text}))
                elif b.block_type == 'list':
                    converted.append(('list', {'items': b.content_text.split('\n'),
                                               'ordered': b.content_data['ordered']}))
                else:
                    converted.append(('text', {'text': b.content_text}))
            stored_rebuilt.append(blocks_to_markdown(title, converted))
        if alnum('\n\n'.join(stored_rebuilt)) != alnum(source_markdown(raw)):
            db.session.rollback()
            sys.exit('VERIFY FAILED: stored blocks differ from the source manuscript. Rolled back.')
        table = stored_chapters[-1][1][0]
        if len(table.content_data['rows']) != len(glossary) + 1:
            db.session.rollback()
            sys.exit('VERIFY FAILED: glossary row count mismatch. Rolled back.')

        by_type = {}
        for _, blocks in stored_chapters:
            for b in blocks:
                by_type[b.block_type] = by_type.get(b.block_type, 0) + 1
        print(f'stored book #{book_id}: {len(stored_chapters)} chapters, {stored.block_count} blocks '
              f'{by_type}, {stored.word_count:,} words')
        print('chapters: ' + ' | '.join(f'{i}. {t} ({len(b)})' for i, (t, b) in enumerate(stored_chapters, 1)))
        print(f'glossary table: {len(table.content_data["rows"]) - 1} terms')
        print(f'inside front cover (dedication): {len(stored.cover("inside_front").content_text)} characters')
        print('database verify OK: stored text identical to the source manuscript')

        if args.dry_run:
            db.session.rollback()
            print('DRY RUN: rolled back, nothing was written.')
        else:
            db.session.commit()
            print(f'COMMITTED: user "{user.username}" (id {user.user_id}) owns book #{book_id}.')


if __name__ == '__main__':
    main()
