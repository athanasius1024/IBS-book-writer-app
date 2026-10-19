"""Parsing and validation of content-block forms (all block types)."""
from media import save_image
from models import MediaAsset, db

MAX_TEXT = 100000
MAX_HEADING = 300
MAX_CAPTION = 500
MAX_LIST_ITEMS = 200
MAX_LIST_ITEM_LEN = 1000
MAX_TABLE_ROWS = 200
MAX_TABLE_COLS = 20
MAX_CELL_LEN = 500


def parse_table(source):
    """Parse 'a | b | c' lines into a rectangular list of rows.

    Leading/trailing pipes are optional. Raises ValueError with a user-facing message.
    """
    rows = []
    for line in (source or '').splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]
        rows.append([cell.strip() for cell in line.split('|')])
    if not rows:
        raise ValueError('Enter at least one table row, with cells separated by "|".')
    if len(rows) > MAX_TABLE_ROWS:
        raise ValueError(f'Tables are limited to {MAX_TABLE_ROWS} rows.')
    width = max(len(row) for row in rows)
    if width > MAX_TABLE_COLS:
        raise ValueError(f'Tables are limited to {MAX_TABLE_COLS} columns.')
    if any(len(cell) > MAX_CELL_LEN for row in rows for cell in row):
        raise ValueError(f'Table cells are limited to {MAX_CELL_LEN} characters.')
    return [row + [''] * (width - len(row)) for row in rows]


def apply_block_form(block, form, files, user_id):
    """Validate the submitted form for ``block.block_type`` and set the block's fields.

    Returns an error message, or None on success. Image assets chosen from the
    library must belong to ``user_id``.
    """
    kind = block.block_type
    text = form.get('content_text') or ''

    if kind == 'text':
        if not text.strip():
            return 'Please enter some text.'
        if len(text) > MAX_TEXT:
            return 'That text is too long.'
        block.content_text, block.content_data, block.asset_id = text, None, None

    elif kind == 'heading':
        text = text.strip()
        if not text:
            return 'Please enter the heading text.'
        if len(text) > MAX_HEADING:
            return f'Headings are limited to {MAX_HEADING} characters.'
        level = form.get('heading_level', type=int)
        block.content_text = text
        block.content_data = {'level': level if level in (1, 2, 3) else 2}
        block.asset_id = None

    elif kind == 'list':
        items = [line.strip() for line in text.splitlines() if line.strip()]
        if not items:
            return 'Enter at least one list item (one per line).'
        if len(items) > MAX_LIST_ITEMS:
            return f'Lists are limited to {MAX_LIST_ITEMS} items.'
        if any(len(item) > MAX_LIST_ITEM_LEN for item in items):
            return f'List items are limited to {MAX_LIST_ITEM_LEN} characters.'
        block.content_text = '\n'.join(items)
        block.content_data = {'ordered': form.get('list_ordered') == '1'}
        block.asset_id = None

    elif kind == 'table':
        try:
            rows = parse_table(text)
        except ValueError as exc:
            return str(exc)
        block.content_text = text.strip()
        block.content_data = {'header': form.get('table_header') == '1', 'rows': rows}
        block.asset_id = None

    elif kind in ('image', 'icon'):
        caption = text.strip()
        if len(caption) > MAX_CAPTION:
            return f'Captions are limited to {MAX_CAPTION} characters.'
        asset = None
        upload = files.get('image')
        if upload and upload.filename:
            try:
                asset = save_image(upload, user_id)
            except ValueError as exc:
                return str(exc)
            db.session.add(asset)
            db.session.flush()
        else:
            asset_id = form.get('asset_id', type=int)
            if asset_id:
                asset = MediaAsset.query.filter_by(asset_id=asset_id, user_id=user_id).first()
                if asset is None:
                    return 'That image was not found in your library.'
        if asset is None and block.asset_id is None:
            return 'Choose an image to upload or pick one from your library.'
        if asset is not None:
            block.asset_id = asset.asset_id
        block.content_text, block.content_data = caption, None

    else:
        return 'Unknown block type.'
    return None
