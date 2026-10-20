"""Editing the Contents page of a book.

A book is in 'custom' mode exactly when it has BookTocEntry rows; deleting them all restores the
automatic Contents. Entries are an ordered list (sort_order 1..n) that the author can rename, hide,
indent, move or delete, and extend with headings, section lines and part dividers.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from access import ensure_editable, owned_book_or_404, owned_toc_entry_or_404
from bookdoc import BookDoc
from layout import get_settings
from models import TOC_MAX_LEVEL, TOC_SECTION_KEYS, BookTocEntry, db

bp = Blueprint('contents', __name__)

MAX_LABEL = 300
SECTION_NAMES = {'glossary': 'Glossary', 'index': 'Index', 'about': 'About the Author(s)'}
ACTIONS = ('save', 'show', 'hide', 'indent', 'outdent', 'up', 'down', 'delete')


def _back(book):
    return redirect(url_for('contents.edit', book_id=book.book_id))


def _renumber(entries):
    for position, entry in enumerate(entries, start=1):
        entry.sort_order = position


def _chapter_of(entry):
    """The chapter an entry belongs to (a chapter line, or a heading line inside a chapter)."""
    if entry.kind == 'chapter':
        return entry.chapter_id
    if entry.kind == 'heading' and entry.block is not None:
        return entry.block.chapter_id
    return None


def _heading_blocks(book):
    return [(chapter, block) for chapter in book.chapters for block in chapter.blocks
            if block.block_type == 'heading']


def _heading_entry_level(block):
    return 1


def _insert(book, entries, new_entry, index):
    """Put new_entry at `index` of the ordered list and renumber everything."""
    entries.insert(max(0, min(index, len(entries))), new_entry)
    book.toc_entries.append(new_entry)
    _renumber(entries)


def _index_after_chapter_group(entries, chapter_id):
    """Index just after the last entry that belongs to `chapter_id`, or None if there is none."""
    last = None
    for position, entry in enumerate(entries):
        if _chapter_of(entry) == chapter_id:
            last = position
    return None if last is None else last + 1


def _index_before_sections(entries):
    for position, entry in enumerate(entries):
        if entry.kind == 'section':
            return position
    return len(entries)


def _row(entry):
    """What the editor shows for one entry."""
    if entry.kind == 'chapter':
        default = entry.chapter.title if entry.chapter else None
    elif entry.kind == 'heading':
        default = entry.block.content_text if entry.block else None
    elif entry.kind == 'section':
        default = SECTION_NAMES.get(entry.section_key)
    else:
        default = None
    return {'entry': entry, 'default': default,
            'broken': entry.kind in ('chapter', 'heading') and default is None}


@bp.route('/books/<int:book_id>/contents')
@login_required
def edit(book_id):
    book = owned_book_or_404(book_id)
    entries = list(book.toc_entries)
    listed_chapters = {e.chapter_id for e in entries if e.kind == 'chapter'}
    listed_blocks = {e.block_id for e in entries if e.kind == 'heading'}
    listed_sections = {e.section_key for e in entries if e.kind == 'section'}
    doc = BookDoc(book, get_settings(book))
    automatic = doc.automatic_toc_lines()
    return render_template(
        'contents/edit.html', book=book, custom=bool(entries), rows=[_row(e) for e in entries],
        automatic=automatic,
        missing_chapters=[c for c in book.chapters if c.chapter_id not in listed_chapters],
        available_headings=[(c, b) for c, b in _heading_blocks(book) if b.block_id not in listed_blocks],
        missing_sections=[(k, SECTION_NAMES[k]) for k in TOC_SECTION_KEYS if k not in listed_sections],
        stamp=doc.stamp(), max_level=TOC_MAX_LEVEL)


@bp.route('/books/<int:book_id>/contents/customize', methods=['POST'])
@login_required
def customize(book_id):
    """Turn the automatic Contents into an editable list (optionally with the headings listed too)."""
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    if book.toc_entries:
        flash('The Contents is already customized.', 'info')
        return _back(book)
    with_headings = request.form.get('with_headings') == '1'
    doc = BookDoc(book, get_settings(book))
    entries = []

    def add(**fields):
        entry = BookTocEntry(level=fields.pop('level', 0), visible=True, **fields)
        entries.append(entry)
        book.toc_entries.append(entry)

    for chapter in book.chapters:
        add(kind='chapter', chapter=chapter)
        if with_headings:
            for block in chapter.blocks:
                if block.block_type == 'heading' and (block.content_data or {}).get('level', 2) in (1, 2):
                    add(kind='heading', block=block, level=1)
    for key in doc.toc_sections():
        add(kind='section', section_key=key)
    _renumber(entries)
    book.touch()
    db.session.commit()
    flash('The Contents is now editable. Page numbers are still added automatically when the book is built.',
          'success')
    return _back(book)


@bp.route('/books/<int:book_id>/contents/reset', methods=['POST'])
@login_required
def reset(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    for entry in list(book.toc_entries):
        db.session.delete(entry)
    book.touch()
    db.session.commit()
    flash('The Contents is automatic again.', 'success')
    return _back(book)


@bp.route('/contents/<int:entry_id>/update', methods=['POST'])
@login_required
def entry_update(entry_id):
    entry = owned_toc_entry_or_404(entry_id)
    book = entry.book
    ensure_editable(book)
    action = request.form.get('action')
    if action not in ACTIONS:
        abort(400)
    entries = list(book.toc_entries)

    if action == 'save':
        label = (request.form.get('label') or '').strip()
        if len(label) > MAX_LABEL:
            flash(f'A Contents line is limited to {MAX_LABEL} characters.', 'danger')
            return _back(book)
        if entry.kind == 'part' and not label:
            flash('A part divider needs some text.', 'danger')
            return _back(book)
        entry.label = label or None
    elif action in ('show', 'hide'):
        entry.visible = action == 'show'
    elif action == 'indent':
        entry.level = min(TOC_MAX_LEVEL, entry.level + 1)
    elif action == 'outdent':
        entry.level = max(0, entry.level - 1)
    elif action in ('up', 'down'):
        index = entries.index(entry)
        other = index - 1 if action == 'up' else index + 1
        if 0 <= other < len(entries):
            entries[index], entries[other] = entries[other], entries[index]
        _renumber(entries)
    elif action == 'delete':
        db.session.delete(entry)
        _renumber([e for e in entries if e is not entry])
    book.touch()
    db.session.commit()
    return _back(book)


@bp.route('/books/<int:book_id>/contents/add-headings', methods=['POST'])
@login_required
def add_headings(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    wanted = {int(v) for v in request.form.getlist('block_ids') if v.isdigit()}
    listed = {e.block_id for e in book.toc_entries if e.kind == 'heading'}
    entries = list(book.toc_entries)
    added = 0
    for chapter, block in _heading_blocks(book):          # document order keeps each group in order
        if block.block_id not in wanted or block.block_id in listed:
            continue
        index = _index_after_chapter_group(entries, chapter.chapter_id)
        if index is None:
            index = _index_before_sections(entries)
        _insert(book, entries, BookTocEntry(kind='heading', block=block, level=_heading_entry_level(block),
                                            visible=True), index)
        added += 1
    if not added:
        flash('Choose at least one heading to add.', 'warning')
        return _back(book)
    book.touch()
    db.session.commit()
    flash(f'Added {added} heading{"" if added == 1 else "s"} to the Contents.', 'success')
    return _back(book)


@bp.route('/books/<int:book_id>/contents/add-part', methods=['POST'])
@login_required
def add_part(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    label = (request.form.get('label') or '').strip()
    if not label:
        flash('Enter the text of the part divider, for example "Part One".', 'danger')
        return _back(book)
    if len(label) > MAX_LABEL:
        flash(f'A Contents line is limited to {MAX_LABEL} characters.', 'danger')
        return _back(book)
    entries = list(book.toc_entries)
    before = request.form.get('before', type=int)
    index = len(entries)
    if before:
        target = next((e for e in entries if e.entry_id == before), None)
        if target is None:
            abort(404)
        index = entries.index(target)
    _insert(book, entries, BookTocEntry(kind='part', label=label, level=0, visible=True), index)
    book.touch()
    db.session.commit()
    flash('Part divider added.', 'success')
    return _back(book)


@bp.route('/books/<int:book_id>/contents/add-missing', methods=['POST'])
@login_required
def add_missing(book_id):
    """Add the chapters created after the Contents was customized, each after the chapter before it."""
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    entries = list(book.toc_entries)
    listed = {e.chapter_id for e in entries if e.kind == 'chapter'}
    added = 0
    previous_chapter_id = None
    for chapter in book.chapters:
        if chapter.chapter_id not in listed:
            index = (_index_after_chapter_group(entries, previous_chapter_id)
                     if previous_chapter_id is not None else None)
            if index is None:
                index = 0 if previous_chapter_id is None else _index_before_sections(entries)
            _insert(book, entries, BookTocEntry(kind='chapter', chapter=chapter, level=0, visible=True), index)
            added += 1
        previous_chapter_id = chapter.chapter_id
    if not added:
        flash('Every chapter is already listed.', 'info')
        return _back(book)
    book.touch()
    db.session.commit()
    flash(f'Added {added} chapter{"" if added == 1 else "s"} to the Contents.', 'success')
    return _back(book)


@bp.route('/books/<int:book_id>/contents/add-section', methods=['POST'])
@login_required
def add_section(book_id):
    book = owned_book_or_404(book_id)
    ensure_editable(book)
    key = request.form.get('section_key')
    if key not in TOC_SECTION_KEYS:
        abort(400)
    entries = list(book.toc_entries)
    if any(e.kind == 'section' and e.section_key == key for e in entries):
        flash('That section is already listed.', 'info')
        return _back(book)
    _insert(book, entries, BookTocEntry(kind='section', section_key=key, level=0, visible=True), len(entries))
    book.touch()
    db.session.commit()
    flash(f'{SECTION_NAMES[key]} added. It only appears if the book has one.', 'success')
    return _back(book)
