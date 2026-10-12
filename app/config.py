"""Flask application configuration."""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.parent

# Database configuration
DATABASE_CONFIG = {
    'host': 'localhost',
    'database': 'db_terran_society',
    'user': 'rock',
    'password': 'river'
}

# Flask configuration
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
SQLALCHEMY_DATABASE_URI = f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}/{DATABASE_CONFIG['database']}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Book generation
BOOK_OUTPUT_DIR = BASE_DIR / 'book'
SCRIPTS_DIR = BASE_DIR / 'scripts'
GENERATE_SCRIPT = SCRIPTS_DIR / 'generate_book.py'

# Book metadata
BOOK_TITLE = "Terran Society: A New Social Contract"
BOOK_AUTHOR = "Angelo Patrick Arteman"
BOOK_VERSION = "1.1"
