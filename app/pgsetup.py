"""Switching the desktop edition to a PostgreSQL server (`IBSBookWriter --setup-postgres`).

Does what setup_database.sh does, but needs no `psql` and works on Windows: asks for the server details, creates
the database if it is missing, applies the bundled sql/schema.sql (safe to repeat; it only adds what is missing)
and saves the connection settings in the data folder's .env so the next start uses PostgreSQL.
"""
import getpass
import os
import re
from pathlib import Path

import paths

NAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


def apply_schema(host, port, dbname, user, password, schema_path=None, connect_timeout=8):
    """Create the database if needed and apply the schema. Returns True if the database had to be created."""
    import psycopg2
    from psycopg2 import sql

    if not NAME_RE.match(dbname or ''):
        raise ValueError('The database name may only contain letters, digits and underscores.')
    script = Path(schema_path or paths.schema_file()).read_text(encoding='utf-8')
    settings = dict(host=host, port=int(port), user=user, password=password or None, connect_timeout=connect_timeout)

    created = False
    admin = psycopg2.connect(dbname='postgres', **settings)
    try:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (dbname,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(dbname)))
                created = True
    finally:
        admin.close()

    connection = psycopg2.connect(dbname=dbname, **settings)
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(script)                      # one transaction: all of it or nothing
    finally:
        connection.close()
    return created


def write_env(env_file, values):
    """Set KEY=VALUE lines in the .env file (other lines are kept); the file is private to the user."""
    env_file = Path(env_file)
    lines = env_file.read_text(encoding='utf-8').splitlines() if env_file.exists() else []
    remaining = dict(values)
    out = []
    for line in lines:
        key = line.split('=', 1)[0].strip()
        if key in remaining and not line.lstrip().startswith('#'):
            out.append(f'{key}={_quote(remaining.pop(key))}')
        else:
            out.append(line)
    out += [f'{key}={_quote(value)}' for key, value in remaining.items()]
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text('\n'.join(out) + '\n', encoding='utf-8')
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass


def _quote(value):
    """A .env value that python-dotenv reads back exactly (single quotes, with \\ and \\' escaped)."""
    value = str(value)
    if not re.search(r'[\s#"\'$\\=]', value):
        return value
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def run_interactive(data_dir, ask=input, ask_password=getpass.getpass, say=print):
    """Ask for the server details, prepare the database, remember the settings. Returns a process exit code."""
    say('Use a PostgreSQL server instead of the built-in database.\n'
        'Press Enter to accept the value in [brackets].\n')
    host = ask('Server host [localhost]: ').strip() or 'localhost'
    port = ask('Server port [5432]: ').strip() or '5432'
    name = ask('Database name [db_ibs_bookwriter]: ').strip() or 'db_ibs_bookwriter'
    user = ask('User name [postgres]: ').strip() or 'postgres'
    password = ask_password('Password (hidden; blank if none): ')
    if not port.isdigit():
        say('The port must be a number.')
        return 1
    try:
        created = apply_schema(host, port, name, user, password)
    except ValueError as exc:
        say(str(exc))
        return 1
    except Exception as exc:                            # connection refused, wrong password, no permission...
        say(f'Could not prepare the database: {exc}')
        return 1
    values = {'DB_HOST': host, 'DB_PORT': port, 'DB_NAME': name, 'DB_USER': user, 'DB_PASSWORD': password}
    write_env(Path(data_dir) / '.env', values)
    say(f'\nDatabase {name} {"created and " if created else ""}prepared.\n'
        f'The settings are saved in {Path(data_dir) / ".env"}. Start the program again to use it.\n'
        'Note: your existing books in the built-in database are not copied to PostgreSQL.')
    return 0
