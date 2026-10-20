"""Parsing and validation of inline-image references (no Flask, database or Pillow here).

In chapter text an image is written  ![description](image:12 "Caption"){: data-crop="x,y,w,h" data-w="60" .img-left}
  12          the media-library id of the picture
  Caption     shown under a picture that stands on its own line (optional)
  data-crop   the part of the picture to show: left, top, width, height as fractions of the original
  data-w      display width as a percentage of the text width (10 to 100)
  .img-left   placement of a stand-alone picture: .img-left, .img-center (default) or .img-right
Everything is range-checked; an invalid value is ignored rather than trusted.
"""
import re

MEDIA_SCHEME = 'ibs-media://'        # an original file in the media library
DERIVED_SCHEME = 'ibs-derived://'    # a cropped / downsized copy made from one

CROP_SCALE = 10000                   # crops are stored as integers in ten-thousandths
MIN_CROP = 100                       # smallest crop edge: 1% of the original
WIDTH_MIN, WIDTH_MAX = 10, 100
ALIGNS = ('left', 'center', 'right')
IMG_CLASSES = frozenset(f'img-{a}' for a in ALIGNS)

IMAGE_REF = re.compile(r'\]\(\s*image:(\d{1,9})')           # the "](image:12" part of a reference
ASSET_SRC = re.compile(r'^ibs-media://(\d{1,9})$')
_NUMBER = r'(\d(?:\.\d{1,6})?)'
_CROP = re.compile(rf'^\s*{_NUMBER}\s*,\s*{_NUMBER}\s*,\s*{_NUMBER}\s*,\s*{_NUMBER}\s*$')
FULL = (0, 0, CROP_SCALE, CROP_SCALE)


def parse_crop(text):
    """'0.1,0.2,0.5,0.5' -> (x, y, w, h) in ten-thousandths, or None when absent, invalid or the whole image."""
    match = _CROP.match(text or '')
    if not match:
        return None
    x, y, w, h = (float(v) for v in match.groups())
    if not all(0 <= v <= 1 for v in (x, y, w, h)):
        return None
    if w * CROP_SCALE < MIN_CROP or h * CROP_SCALE < MIN_CROP:
        return None
    x_i, y_i = round(x * CROP_SCALE), round(y * CROP_SCALE)
    if x_i >= CROP_SCALE - MIN_CROP + 1 or y_i >= CROP_SCALE - MIN_CROP + 1:
        return None
    w_i = min(round(w * CROP_SCALE), CROP_SCALE - x_i)         # a rectangle that spills over is trimmed
    h_i = min(round(h * CROP_SCALE), CROP_SCALE - y_i)
    if w_i < MIN_CROP or h_i < MIN_CROP:
        return None
    spec = (x_i, y_i, w_i, h_i)
    return None if spec == FULL else spec


def format_crop(spec):
    """(x, y, w, h) -> '0.1,0.2,0.5,0.5' (the form used in the text and in URLs)."""
    return ','.join(f'{v / CROP_SCALE:.4f}'.rstrip('0').rstrip('.') or '0' for v in spec)


def parse_width(text):
    """'60' -> 60 when it is a whole number from 10 to 100, else None."""
    text = (text or '').strip()
    if not text.isdigit() or len(text) > 3:
        return None
    value = int(text)
    return value if WIDTH_MIN <= value <= WIDTH_MAX else None


def parse_align(class_text):
    """The placement named by a class attribute ('img-left' ...), default 'center'."""
    for token in (class_text or '').split():
        if token in IMG_CLASSES:
            return token[4:]
    return 'center'
