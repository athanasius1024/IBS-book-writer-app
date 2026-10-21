"""Preparing a SQLite database for the desktop edition.

PostgreSQL databases are prepared with sql/schema.sql (setup_database.sh, or `--setup-postgres` in the
desktop edition). SQLite needs no server and no script: the tables are created from the models when the
app starts, and a version number kept inside the database file drives upgrades.

Upgrading: `db.create_all()` only creates tables that are missing, it never changes an existing one.
So when a release needs a changed column, append an entry to MIGRATIONS (never edit or remove old ones):
each entry is a list of SQL statements run once, in order, on databases older than that entry.
"""
import logging

from sqlalchemy import event, text

from models import db

log = logging.getLogger(__name__)

# (version, [SQL statements]). The current version is the highest number here, or 1 while the list is empty.
MIGRATIONS = []
BASELINE_VERSION = 1


def schema_version():
    return max([BASELINE_VERSION] + [version for version, _ in MIGRATIONS])


def _on_connect(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys = ON')       # ON DELETE CASCADE / SET NULL are honoured, as in PostgreSQL
    cursor.execute('PRAGMA journal_mode = WAL')      # readers do not block the writer; survives a crash
    cursor.execute('PRAGMA synchronous = NORMAL')
    cursor.close()


def init_database(app):
    """Create missing tables, switch on integrity features and apply any pending migrations. Safe to repeat."""
    with app.app_context():
        engine = db.engine
        if not event.contains(engine, 'connect', _on_connect):
            event.listen(engine, 'connect', _on_connect)
            engine.dispose()                          # connections made before the listener get replaced
        db.create_all()
        with engine.begin() as connection:
            # The same case-insensitive uniqueness that sql/schema.sql gives PostgreSQL.
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_book_term_name '
                                    'ON book_term (book_id, lower(term))'))
            current = connection.execute(text('PRAGMA user_version')).scalar() or 0
            if current > schema_version():
                raise RuntimeError(
                    f'This data folder was written by a newer version of IBS Book Writer (database version {current}; '
                    f'this program understands up to {schema_version()}). Use the newer program, or a different data folder.')
            for version, statements in sorted(MIGRATIONS):
                if current < version:
                    log.info('Upgrading the database to version %s', version)
                    for statement in statements:
                        connection.execute(text(statement))
                    current = version
            connection.execute(text(f'PRAGMA user_version = {max(current, schema_version())}'))
