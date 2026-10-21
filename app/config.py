"""Application configuration.

All secrets and connection settings come from environment variables (optionally
loaded from a ``.env`` file in the project root). Nothing sensitive is stored in
source control.
"""
import os
import json
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env', interpolate=False)

# Optional connection overrides saved by the admin "Database settings" page.
DB_CONFIG_FILE = BASE_DIR / 'config' / 'db_config.json'


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


# Postgres schema that holds the application tables. An empty value means
# "no schema" (used by the SQLite-based test suite).
DB_SCHEMA = os.environ.get('BOOKWRITER_SCHEMA', 'scm_bookwriter') or None


def build_database_uri():
    explicit = os.environ.get('DATABASE_URL')
    if explicit:
        return explicit
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
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Uploads (cover images etc.) live outside ``static`` and are served through an
# authenticated route so one user cannot read another user's files.
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR') or (BASE_DIR / 'uploads'))
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
