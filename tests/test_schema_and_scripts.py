"""Checks that don't need a Postgres server."""
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

from models import db

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = (ROOT / 'sql' / 'schema.sql').read_text()


def _parse_schema_sql():
    """Return {table: {column: (is_not_null_or_pk)}} and the set of FK pairs from schema.sql."""
    tables, fks = {}, set()
    for name, body in re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);', SCHEMA_SQL, re.S):
        cols = {}
        for line in body.splitlines():
            line = re.sub(r'--.*$', '', line).strip().rstrip(',')
            if not line or line.upper().startswith('CONSTRAINT'):
                continue
            col = line.split()[0]
            cols[col] = ('NOT NULL' in line.upper()) or ('PRIMARY KEY' in line.upper())
            ref = re.search(r'REFERENCES (\w+)\((\w+)\)', line)
            if ref:
                fks.add((name, col, ref.group(1), ref.group(2)))
        tables[name] = cols
    return tables, fks


def test_schema_sql_matches_models():
    sql_tables, sql_fks = _parse_schema_sql()
    model_tables = db.metadata.tables
    # keys are 'table' (no schema is configured in tests)
    assert set(sql_tables) == set(model_tables)

    model_fks = set()
    for name, table in model_tables.items():
        assert set(sql_tables[name]) == {c.name for c in table.columns}, name
        for column in table.columns:
            required = (not column.nullable) or column.primary_key
            assert sql_tables[name][column.name] == required, f'{name}.{column.name} nullability differs'
            for fk in column.foreign_keys:
                model_fks.add((name, column.name, fk.column.table.name, fk.column.name))
    assert sql_fks == model_fks


def test_schema_sql_has_constraints_the_app_relies_on():
    assert 'uq_book_cover_panel UNIQUE (book_id, panel)' in SCHEMA_SQL
    assert "status IN ('draft', 'completed')" in SCHEMA_SQL
    assert "panel IN ('front', 'spine', 'back', 'inside_front', 'inside_back')" in SCHEMA_SQL
    # user->book/media, book->cover/chapter/layout/page/author/term, chapter->block (9), then
    # toc entry->book/chapter/block (3), derivative->asset/user (2), rendered book->book/user (2)
    assert SCHEMA_SQL.count("ON DELETE CASCADE") == 16


def test_set_env_round_trips_special_characters(tmp_path, monkeypatch):
    # Run a copy of the script so the real .env is never touched.
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'set_env.py').write_text((ROOT / 'scripts' / 'set_env.py').read_text())
    env_file = tmp_path / '.env'
    env_file.write_text('SECRET_KEY=\nDB_HOST=localhost\n')

    def run(*args):
        subprocess.run([sys.executable, str(scripts / 'set_env.py'), *args], check=True)

    tricky = 'p@ss "w0rd" \\ $HOME #not-a-comment ${X}'
    run('DB_PASSWORD', tricky)
    run('SECRET_KEY', 'first', '--if-empty')
    run('SECRET_KEY', 'second', '--if-empty')   # must not overwrite
    run('DB_HOST', 'db.example')                 # replaces in place

    values = dotenv_values(env_file, interpolate=False)
    assert values['DB_PASSWORD'] == tricky
    assert values['SECRET_KEY'] == 'first'
    assert values['DB_HOST'] == 'db.example'
    assert (env_file.stat().st_mode & 0o777) == 0o600
    assert env_file.read_text().count('DB_HOST=') == 1
