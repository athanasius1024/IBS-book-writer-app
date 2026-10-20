"""Cropping and resizing of embedded images, and turning inline image references into final HTML.

The original file in the media library is never touched. A crop (and any downsizing of a very large
picture) is made once with Pillow, cached on disk under UPLOAD_DIR/derived/<user>/ and recorded in
the media_derivative table, so PDF/EPUB/HTML/ODT builds stay small and fast.
"""
import re
from collections import Counter
from html import escape, unescape
from pathlib import Path

from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError

from imagespec import (ASSET_SRC, CROP_SCALE, DERIVED_SCHEME, FULL, IMAGE_REF, MEDIA_SCHEME, format_crop,
                       parse_align, parse_crop, parse_width)
from models import Book, Chapter, ContentBlock, MediaAsset, MediaDerivative, db

MAX_PX = 2000                         # longest side of a derivative
MAX_SOURCE_PIXELS = 60_000_000        # refuse to decode anything bigger than this

# One scan finds both a picture alone in its paragraph (group 1) and any other <img>, so the tags this
# module writes are never read again.
_PICTURE = re.compile(r'<p>\s*(<img\b[^>]*>)\s*</p>|<img\b[^>]*>')
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def upload_root():
    return Path(current_app.config['UPLOAD_DIR']).resolve()


def _inside(root, relative):
    path = (root / relative).resolve()
    return path if root in path.parents and path.is_file() else None


# ---- derivatives ------------------------------------------------------------------------------------

def derive(asset, crop=None, max_px=MAX_PX):
    """The cached copy of `asset` cropped to `crop` (x, y, w, h in ten-thousandths) and limited to
    `max_px` on its longest side, creating it if needed.

    Returns a MediaDerivative, or None when the original should be used as it is (no crop and already
    small enough) or when the picture cannot be read.
    """
    spec = crop or FULL
    row = MediaDerivative.query.filter_by(asset_id=asset.asset_id, crop_x=spec[0], crop_y=spec[1],
                                          crop_w=spec[2], crop_h=spec[3], max_px=max_px).first()
    root = upload_root()
    if row is not None and _inside(root, row.file_path):
        return row
    source = _inside(root, asset.file_path)
    if source is None:
        return None
    try:
        with Image.open(source) as opened:
            if opened.width * opened.height > MAX_SOURCE_PIXELS:
                return None
            fmt = opened.format
            image = ImageOps.exif_transpose(opened)          # crop what the author sees, not the raw sensor
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        return None
    width, height = image.size
    if crop is None and max(width, height) <= max_px:
        return None                                          # the original is already fine
    if crop is not None:
        x, y, w, h = crop
        left, top = round(x / CROP_SCALE * width), round(y / CROP_SCALE * height)
        right = min(width, left + max(1, round(w / CROP_SCALE * width)))
        bottom = min(height, top + max(1, round(h / CROP_SCALE * height)))
        image = image.crop((left, top, max(right, left + 1), max(bottom, top + 1)))
    if max(image.size) > max_px:
        image.thumbnail((max_px, max_px), Image.LANCZOS)

    jpeg = fmt == 'JPEG'
    extension, mime = ('jpg', 'image/jpeg') if jpeg else ('png', 'image/png')
    name = f'{asset.asset_id}-{spec[0]}-{spec[1]}-{spec[2]}-{spec[3]}-{max_px}.{extension}'
    relative = f'derived/{asset.user_id}/{name}'
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    if jpeg:
        image.convert('RGB').save(temporary, 'JPEG', quality=90, optimize=True)
    else:
        image.save(temporary, 'PNG', optimize=True)
    temporary.replace(destination)

    if row is None:
        row = MediaDerivative(asset_id=asset.asset_id, user_id=asset.user_id, crop_x=spec[0], crop_y=spec[1],
                              crop_w=spec[2], crop_h=spec[3], max_px=max_px)
        db.session.add(row)
    row.file_path, row.mime_type, row.file_size = relative, mime, destination.stat().st_size
    try:
        db.session.commit()
    except IntegrityError:                                   # another request made the same copy first
        db.session.rollback()
        row = MediaDerivative.query.filter_by(asset_id=asset.asset_id, crop_x=spec[0], crop_y=spec[1],
                                              crop_w=spec[2], crop_h=spec[3], max_px=max_px).first()
    return row


def remove_derivative_files(asset):
    """Delete the cached copies of `asset` from disk (the rows go with the asset)."""
    root = upload_root()
    for row in list(asset.derivatives):
        path = _inside(root, row.file_path)
        if path is not None:
            path.unlink()


def read_image(src, user_id):
    """(bytes, mime type) for an ibs-media:// or ibs-derived:// source owned by `user_id`, else None."""
    root = upload_root()
    if src.startswith(DERIVED_SCHEME):
        try:
            number = int(src[len(DERIVED_SCHEME):])
        except ValueError:
            return None
        row = MediaDerivative.query.filter_by(derivative_id=number, user_id=user_id).first()
        path = _inside(root, row.file_path) if row else None
        return (path.read_bytes(), row.mime_type) if path else None
    match = ASSET_SRC.match(src)
    if not match:
        return None
    asset = MediaAsset.query.filter_by(asset_id=int(match.group(1)), user_id=user_id).first()
    path = _inside(root, asset.file_path) if asset else None
    return (path.read_bytes(), asset.mime_type) if path else None


# ---- where inline images are used ---------------------------------------------------------------------

def inline_usage_counts(user_id):
    """{asset_id: number of text blocks that use it inline} for one user."""
    rows = (db.session.query(ContentBlock.content_text)
            .join(Chapter, ContentBlock.chapter_id == Chapter.chapter_id)
            .join(Book, Chapter.book_id == Book.book_id)
            .filter(Book.user_id == user_id, ContentBlock.block_type == 'text',
                    ContentBlock.content_text.like('%image:%')).all())
    counts = Counter()
    for (text,) in rows:
        for asset_id in {int(n) for n in IMAGE_REF.findall(text or '')}:
            counts[asset_id] += 1
    return counts


# ---- turning sanitised image tags into final HTML ------------------------------------------------------------------

def _parse_img(tag_html):
    """(asset_id, crop, width, align, alt, caption) from a sanitised <img> tag, or None if unusable."""
    attrs = {name: unescape(value) for name, value in _ATTR.findall(tag_html)}
    match = ASSET_SRC.match(attrs.get('src', ''))
    if not match:
        return None
    alt = attrs.get('alt', '')
    return (int(match.group(1)), parse_crop(attrs.get('data-crop')), parse_width(attrs.get('data-w')),
            parse_align(attrs.get('class')), alt, attrs.get('title', ''))


def finalize_inline_images(html, resolver):
    """Replace the sanitised <img> tags in `html` with their final form.

    `resolver(asset_id, crop)` returns the image source to use, or None if the picture is not
    available. A picture alone in its paragraph becomes a <figure> (with a caption if it has a title);
    a picture inside a line of text stays an inline <img>. Tags that are not valid references are
    dropped, so nothing from outside the media library can be loaded.
    """
    def figure(match):
        info = _parse_img(match.group(1))
        if info is None:
            return ''
        asset_id, crop, width, align, alt, caption = info
        src = resolver(asset_id, crop)
        if src is None:
            return '<p><em>[image no longer available]</em></p>'
        style = f' style="width: {width}%"' if width else ''
        text = escape(caption.strip())
        return (f'<figure class="inline-figure img-{align}"{style}>'
                f'<img src="{escape(src, quote=True)}" alt="{escape(alt or caption, quote=True)}"/>'
                + (f'<figcaption>{text}</figcaption>' if text else '') + '</figure>')

    def inline(match):
        info = _parse_img(match.group(0))
        if info is None:
            return ''
        asset_id, crop, width, _, alt, caption = info
        src = resolver(asset_id, crop)
        if src is None:
            return '<em>[image no longer available]</em>'
        style = f' style="width: {width}%"' if width else ''
        return (f'<img class="inline-img" src="{escape(src, quote=True)}" '
                f'alt="{escape(alt or caption, quote=True)}"{style}/>')

    def replace(match):
        return figure(match) if match.group(1) else inline(match)

    return _PICTURE.sub(replace, html)


def render_markdown_with_images(text):
    """Template filter for chapter text on the web pages: Markdown with its inline pictures shown."""
    from markupsafe import Markup

    from markup import render_markdown
    html = str(render_markdown(text, images=True))
    if '<img' in html:
        html = finalize_inline_images(html, resolve_web)
    return Markup(html)


def resolve_web(asset_id, crop):
    """Image source for the web pages: owner-scoped routes (the page is only shown to the owner)."""
    if crop is None:
        return url_for('media.serve', asset_id=asset_id)
    return url_for('media.serve_crop', asset_id=asset_id, c=format_crop(crop))


def resolve_export(asset_id, crop, user_id):
    """Image source for PDF/EPUB/HTML/ODT builds, or None if `user_id` does not own the picture."""
    asset = MediaAsset.query.filter_by(asset_id=asset_id, user_id=user_id).first()
    if asset is None:
        return None
    derivative = derive(asset, crop)
    return f'{DERIVED_SCHEME}{derivative.derivative_id}' if derivative else f'{MEDIA_SCHEME}{asset_id}'
