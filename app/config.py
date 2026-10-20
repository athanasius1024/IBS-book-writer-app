"""Application configuration.

All secrets and connection settings come from environment variables (optionally
loaded from a ``.env`` file). Nothing sensitive is stored in source control.

Two ways of running:

* From source / on a server (the default): unchanged. ``.env`` in the project root, PostgreSQL, uploads
  in ``./uploads``.
* Desktop edition (the packaged app, or ``IBS_DESKTOP=1``): everything lives in one per-user folder
  (see paths.py). The database is a SQLite file there unless PostgreSQL has been configured, either in
  that folder's ``.env`` (DB_NAME / DB_HOST / DATABASE_URL) or in the environment.

``IBS_DB=sqlite`` or ``IBS_DB=postgres`` forces the choice in either mode.
"""
import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

import paths

BASE_DIR = Path(__file__).resolve().parent.parent
DESKTOP = paths.DESKTOP
DATA_DIR = paths.data_dir() if DESKTOP else None
_HOME = DATA_DIR if DESKTOP else BASE_DIR           # where .env, uploads and settings live

ENV_FILE = _HOME / '.env'
load_dotenv(ENV_FILE, interpolate=False)

# Optional connection overrides saved by the admin "Database settings" page.
DB_CONFIG_FILE = _HOME / 'config' / 'db_config.json'


def load_db_config_file():
    if DB_CONFIG_FILE.exists():
        try:
            return json.loads(DB_CONFIG_FILE.read_text())
        except (OSError, ValueError):
            return {}
    return {}


def _db_setting(env_name, key, default=''):
    value = os.environ.get(env_name)
    if value is not None and value != '':
        return value
    return str(load_db_config_file().get(key, default))


def _postgres_configured():
    return bool(os.environ.get('DATABASE_URL') or os.environ.get('DB_NAME') or os.environ.get('DB_HOST')
                or load_db_config_file())


def _choose_backend():
    explicit = (os.environ.get('IBS_DB') or '').lower()
    if explicit in ('sqlite', 'postgres'):
        return explicit
    if DESKTOP:
        return 'postgres' if _postgres_configured() else 'sqlite'
    return 'postgres'                                   # source and server runs behave exactly as before


BACKEND = _choose_backend()
SQLITE_PATH = Path(os.environ.get('IBS_SQLITE_PATH') or (_HOME / 'ibsbook.db'))

# Postgres schema that holds the application tables. No schema on SQLite, and none when the tests give an
# empty value or a SQLite URL.
DB_SCHEMA = os.environ.get('BOOKWRITER_SCHEMA', 'scm_bookwriter') or None
if BACKEND == 'sqlite' or (os.environ.get('DATABASE_URL') or '').startswith('sqlite'):
    DB_SCHEMA = None


def build_database_uri():
    explicit = os.environ.get('DATABASE_URL')
    if explicit:
        return explicit
    if BACKEND == 'sqlite':
        return f'sqlite:///{SQLITE_PATH}'
    host = _db_setting('DB_HOST', 'host', 'localhost')
    port = _db_setting('DB_PORT', 'port', '5432')
    name = _db_setting('DB_NAME', 'database', 'db_ibs_bookwriter')
    user = _db_setting('DB_USER', 'user', 'rock')
    password = _db_setting('DB_PASSWORD', 'password', '')
    auth = quote_plus(user)
    if password:
        auth += ':' + quote_plus(password)
    return f'postgresql://{auth}@{host}:{port}/{name}'


SECRET_KEY = os.environ.get('SECRET_KEY')


def load_or_create_secret_key():
    """Desktop edition: a random key made on first run and kept (readable only by the user) in the data folder,
    so sessions survive restarts and nobody has to configure one."""
    path = DATA_DIR / 'secret_key'
    if path.exists():
        key = path.read_text().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    path.write_text(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


SQLALCHEMY_TRACK_MODIFICATIONS = False

# Uploads (cover images etc.) live outside ``static`` and are served through an
# authenticated route so one user cannot read another user's files.
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR') or (_HOME / 'uploads'))
MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

# Optional folder (on the machine that runs the app) where stored books can also be saved with one click.
# Unset = the button is not offered; downloads through the browser always work.
EXPORT_DIR = os.environ.get('EXPORT_DIR') or None

# Authentication
MIN_PASSWORD_LENGTH = 8
ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', '1').lower() not in ('0', 'false', 'no')

# Session cookie hardening
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0').lower() in ('1', 'true', 'yes')
