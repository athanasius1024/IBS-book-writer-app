"""Where the app finds its read-only resources and keeps the user's data.

Run from source, nothing changes: resources sit next to the code and data stays where it always was.
In the desktop edition (a PyInstaller bundle, or IBS_DESKTOP=1) resources come from the bundle and
everything the user creates (database, pictures, stored books, settings) lives in ONE per-user folder:

    Windows   %APPDATA%\\IBS Book Writer
    Linux     ~/.local/share/ibs-book-writer        (or $XDG_DATA_HOME/ibs-book-writer)

Copying that folder is a complete backup. IBS_DATA_DIR (or --data-dir) overrides the location.
"""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
DESKTOP = FROZEN or os.environ.get('IBS_DESKTOP') == '1'


def resource_dir():
    """The folder holding templates/, static/ and fonts/ (the app folder, or the unpacked bundle)."""
    return Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent


def fonts_dir():
    return resource_dir() / 'fonts'


def schema_file():
    """sql/schema.sql, used to prepare a PostgreSQL database."""
    if FROZEN:
        return resource_dir() / 'sql' / 'schema.sql'
    return Path(__file__).resolve().parent.parent / 'sql' / 'schema.sql'


def data_dir():
    """The per-user data folder (created on first use, readable only by the user where the OS allows)."""
    override = os.environ.get('IBS_DATA_DIR')
    if override:
        path = Path(override).expanduser()
    elif sys.platform == 'win32':
        path = Path(os.environ.get('APPDATA') or (Path.home() / 'AppData' / 'Roaming')) / 'IBS Book Writer'
    else:
        path = Path(os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share')) / 'ibs-book-writer'
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path
