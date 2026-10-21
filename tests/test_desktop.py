"""The desktop edition: where it keeps things, which database it uses, the launcher, and the bundled fonts."""
import http.server
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values
from pypdf import PdfReader
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import config
import dbinit
import desktop
import paths
import pgsetup
import version
from bookfactory import make_book, make_user
from conftest import has_mode
from ibsbook import create_app
from layout import ALLOWED_FONT_FILES, BUNDLED_FONT_FILES, FONT_SCHEME, font_face_css, pdf_css, DEFAULTS
from models import Book, BookTerm, User, db
from render import MediaFetcher, clear_cache, get_layout

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
NO_HYPHEN = {'hyphenate': False}


# Importing the app in this process loads the repository's own .env into os.environ (SECRET_KEY, DB_* ...), so a
# child process must be given a clean environment or it would behave like the developer's machine.
SETTING_PREFIXES = ('IBS_', 'DB_', 'DATABASE_URL', 'BOOKWRITER', 'UPLOAD_DIR', 'SECRET_KEY', 'ALLOW_REGISTRATION',
                    'EXPORT_DIR', 'SESSION_COOKIE', 'FONTCONFIG', 'XDG_DATA_HOME', 'HOST', 'PORT')


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(SETTING_PREFIXES)}
    env.update(extra)
    return env


def run_config(env, tmp_path, project=None):
    """What config decides in a fresh interpreter (config is evaluated once, at import) with this environment.

    With `project`, config.py and paths.py are copied into <project>/app first, so there is no .env next to them."""
    app_dir = APP
    if project is not None:
        app_dir = Path(project) / 'app'
        app_dir.mkdir(parents=True, exist_ok=True)
        for name in ('config.py', 'paths.py'):
            (app_dir / name).write_text((APP / name).read_text())
    base = clean_env(HOME=str(tmp_path / 'home'), PYTHONPATH=str(app_dir), **env)
    code = ("import json, config; print(json.dumps({'backend': config.BACKEND, 'schema': config.DB_SCHEMA, "
            "'uri': config.build_database_uri(), 'uploads': str(config.UPLOAD_DIR), 'data': str(config.DATA_DIR), "
            "'desktop': config.DESKTOP, 'env_file': str(config.ENV_FILE)}))")
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=base, cwd=str(tmp_path), timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


# ---- which database, and where things live ----------------------------------------------------------------

def test_desktop_mode_uses_sqlite_and_keeps_everything_in_the_data_folder(tmp_path):
    data = tmp_path / 'mydata'
    got = run_config({'IBS_DESKTOP': '1', 'IBS_DATA_DIR': str(data)}, tmp_path)
    assert got['backend'] == 'sqlite' and got['schema'] is None and got['desktop'] is True
    assert Path(got['uri'].removeprefix('sqlite:///')) == data / 'ibsbook.db'        # separators differ on Windows
    assert got['uploads'] == str(data / 'uploads') and got['env_file'] == str(data / '.env')
    assert data.is_dir() and has_mode(data, 0o700)


@pytest.mark.skipif(sys.platform == 'win32', reason='this is the Linux/XDG rule; Windows has its own test below')
def test_default_data_folder_on_linux(tmp_path):
    got = run_config({'IBS_DESKTOP': '1'}, tmp_path)
    assert got['data'] == str(tmp_path / 'home' / '.local' / 'share' / 'ibs-book-writer')
    got = run_config({'IBS_DESKTOP': '1', 'XDG_DATA_HOME': str(tmp_path / 'xdg')}, tmp_path)
    assert got['data'] == str(tmp_path / 'xdg' / 'ibs-book-writer')


def test_default_data_folder_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv('IBS_DATA_DIR', raising=False)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'AppData' / 'Roaming'))
    monkeypatch.setattr(paths, 'sys', SimpleNamespace(platform='win32', frozen=False))
    folder = paths.data_dir()
    assert folder == tmp_path / 'AppData' / 'Roaming' / 'IBS Book Writer' and folder.is_dir()


def test_desktop_mode_switches_to_postgres_when_it_is_configured(tmp_path):
    data = tmp_path / 'd'
    data.mkdir()
    (data / '.env').write_text('DB_HOST=db.example\nDB_NAME=books\nDB_USER=me\nDB_PASSWORD=pw\n')
    got = run_config({'IBS_DESKTOP': '1', 'IBS_DATA_DIR': str(data)}, tmp_path)
    assert got['backend'] == 'postgres' and got['schema'] == 'scm_bookwriter'
    assert got['uri'] == 'postgresql://me:pw@db.example:5432/books'
    forced = run_config({'IBS_DESKTOP': '1', 'IBS_DATA_DIR': str(data), 'IBS_DB': 'sqlite'}, tmp_path)
    assert forced['backend'] == 'sqlite' and forced['schema'] is None
    via_url = run_config({'IBS_DESKTOP': '1', 'IBS_DATA_DIR': str(tmp_path / 'e'), 'DATABASE_URL': 'postgresql://u@h/d'}, tmp_path)
    assert via_url['backend'] == 'postgres' and via_url['uri'] == 'postgresql://u@h/d'


def test_source_and_server_runs_are_unchanged(tmp_path):
    proj = tmp_path / 'proj'                                   # a project folder with no .env of its own
    got = run_config({}, tmp_path, project=proj)
    assert got['backend'] == 'postgres' and got['desktop'] is False and got['data'] == 'None'
    assert got['uri'] == 'postgresql://rock@localhost:5432/db_ibs_bookwriter' and got['schema'] == 'scm_bookwriter'
    assert got['uploads'] == str(proj / 'uploads') and got['env_file'] == str(proj / '.env')
    forced = run_config({'IBS_DB': 'sqlite'}, tmp_path, project=tmp_path / 'proj2')
    assert forced['backend'] == 'sqlite' and forced['uri'] == f'sqlite:///{tmp_path / "proj2" / "ibsbook.db"}'
    tests_style = run_config({'DATABASE_URL': 'sqlite://', 'BOOKWRITER_SCHEMA': ''}, tmp_path, project=tmp_path / 'proj3')
    assert tests_style['schema'] is None and tests_style['uri'] == 'sqlite://'
    with_env = tmp_path / 'proj4'
    (with_env / 'app').mkdir(parents=True)
    (with_env / '.env').write_text('DB_HOST=server.example\nDB_NAME=mybooks\nDB_USER=me\nDB_PASSWORD=pw\n')
    configured = run_config({}, tmp_path, project=with_env)
    assert configured['backend'] == 'postgres' and configured['uri'] == 'postgresql://me:pw@server.example:5432/mybooks'


def test_desktop_secret_key_is_made_once_kept_private_and_reused(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    first = config.load_or_create_secret_key()
    assert len(first) == 64 and has_mode(tmp_path / 'secret_key', 0o600)
    assert config.load_or_create_secret_key() == first
    (tmp_path / 'secret_key').write_text('')
    assert config.load_or_create_secret_key() not in ('', first)                   # an empty file is replaced


# ---- preparing SQLite ---------------------------------------------------------------------------------------

@pytest.fixture()
def sqlite_app(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "t.db"}',
                      'UPLOAD_DIR': tmp_path / 'uploads'})
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_init_creates_all_tables_and_turns_on_integrity_features(sqlite_app):
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        names = set(inspect(db.engine).get_table_names())
        assert {'app_user', 'book', 'chapter', 'content_block', 'book_toc_entry', 'media_derivative', 'rendered_book'} <= names
        assert len(names) == 13
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        assert db.session.execute(text('PRAGMA journal_mode')).scalar().lower() == 'wal'
        assert db.session.execute(text('PRAGMA user_version')).scalar() == dbinit.schema_version()


def test_init_is_safe_to_repeat_and_keeps_data(sqlite_app):
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        user = make_user('keeper')
        db.session.commit()
    dbinit.init_database(sqlite_app)
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        assert User.query.filter_by(username='keeper').count() == 1


def test_deleting_through_the_database_cascades_because_foreign_keys_are_on(sqlite_app):
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        user = make_user('cascade')
        book, _ = make_book(user, chapters=2, paragraphs=2)
        db.session.commit()
        db.session.execute(text('DELETE FROM app_user'))                           # raw SQL: no ORM help
        db.session.commit()
        assert db.session.execute(text('SELECT count(*) FROM book')).scalar() == 0
        assert db.session.execute(text('SELECT count(*) FROM content_block')).scalar() == 0


def test_term_names_are_unique_per_book_ignoring_case(sqlite_app):
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        user = make_user('terms')
        book, _ = make_book(user, chapters=0)
        book.terms.append(BookTerm(term='Fox', definition='a'))
        db.session.commit()
        book.terms.append(BookTerm(term='fox', definition='b'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_migrations_run_once_in_order_and_move_the_version_up(sqlite_app, monkeypatch):
    dbinit.init_database(sqlite_app)
    ran = []

    def fake_statement(label):
        ran.append(label)
        return f"CREATE TABLE IF NOT EXISTS migration_probe_{label} (id INTEGER)"

    monkeypatch.setattr(dbinit, 'MIGRATIONS', [(2, [fake_statement('two')]), (3, [fake_statement('three_a'), fake_statement('three_b')])])
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        assert db.session.execute(text('PRAGMA user_version')).scalar() == 3
        tables = set(inspect(db.engine).get_table_names())
        assert {'migration_probe_two', 'migration_probe_three_a', 'migration_probe_three_b'} <= tables
    assert ran == ['two', 'three_a', 'three_b']
    dbinit.init_database(sqlite_app)                                               # already at 3: nothing runs again
    assert ran == ['two', 'three_a', 'three_b']


def test_a_database_from_a_newer_program_is_refused_and_left_alone(sqlite_app):
    dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        user = make_user('future')
        db.session.commit()
        db.session.execute(text(f'PRAGMA user_version = {dbinit.schema_version() + 5}'))
        db.session.commit()
    with pytest.raises(RuntimeError, match='newer version'):
        dbinit.init_database(sqlite_app)
    with sqlite_app.app_context():
        assert db.session.execute(text('PRAGMA user_version')).scalar() == dbinit.schema_version() + 5   # not lowered
        assert User.query.filter_by(username='future').count() == 1


# ---- the admin Database page ------------------------------------------------------------------------------

def test_admin_database_page_explains_the_built_in_database(alice, monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'BACKEND', 'sqlite')
    monkeypatch.setattr(config, 'SQLITE_PATH', tmp_path / 'ibsbook.db')
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    page = alice.get('/settings/database')
    html = page.data.decode()
    assert page.status_code == 200 and 'Built-in database (SQLite)' in html and str(tmp_path / 'ibsbook.db') in html
    assert '--setup-postgres' in html and 'name="host"' not in html                # no PostgreSQL form


def test_admin_database_page_still_shows_the_form_for_postgres(alice, monkeypatch):
    monkeypatch.setattr(config, 'BACKEND', 'postgres')
    html = alice.get('/settings/database').data.decode()
    assert 'PostgreSQL Connection' in html and 'name="host"' in html


# ---- the launcher ------------------------------------------------------------------------------------------------

def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def test_arguments():
    args = desktop.parse_args(['--port', '5055', '--no-browser', '--data-dir', '/x'])
    assert (args.port, args.no_browser, args.data_dir, args.setup_postgres, args.version) == (5055, True, '/x', False, False)
    assert desktop.parse_args([]).port == desktop.DEFAULT_PORT


def test_version_flag_prints_and_exits(capsys):
    assert desktop.main(['--version']) == 0
    assert capsys.readouterr().out.strip() == f'IBS Book Writer v{desktop.VERSION}' == version.DISPLAY_NAME


def test_the_version_is_one_number_that_names_every_file(capsys):
    assert re.fullmatch(r'\d+_\d+', version.APP_VERSION)                                  # 1_0, 1_1, 1_2 ...
    n = version.APP_VERSION
    assert version.WINDOWS_FILE == f'IBSBookWriter_v{n}.exe'
    assert version.LINUX_FILE == f'ibs-book-writer-linux-x86_64_v{n}' and version.TAG == f'v{n}'
    assert version.MACOS_FILE == f'ibs-book-writer-macos_v{n}'
    assert desktop.VERSION == n


def test_pages_show_the_version(client):
    page = client.get('/login').data.decode()
    assert f'v{version.APP_VERSION}' in page and page.count(f'v{version.APP_VERSION}') >= 2    # navbar and footer
    assert desktop.BANNER_MARK in page                                                       # is_ours() still recognises it


def test_no_build_file_hard_codes_a_name_or_number(tmp_path):
    """The scripts must take the file names from version.py, so a release is a one-line change there."""
    for name in ('build_linux.sh', 'build_windows.ps1', 'ibsbook.spec'):
        source = (ROOT / 'packaging' / name).read_text()
        executable_lines = [line for line in source.splitlines() if not line.lstrip().startswith(('#', '<#', 'Output:'))]
        code = '\n'.join(executable_lines)
        assert f'_v{version.APP_VERSION}' not in code, name
        assert 'ibs-book-writer-linux-x86_64' not in code or name == 'build_linux.sh' and 'version.LINUX_FILE' in code, name
    assert 'version.py' in (ROOT / 'packaging' / 'build_linux.sh').read_text()


def test_busy_ports_are_skipped():
    with socket.socket() as taken:
        taken.bind(('127.0.0.1', 0))
        taken.listen(1)
        busy = taken.getsockname()[1]
        assert desktop.port_is_free(busy) is False
        found = desktop.find_port(busy, tries=30)
        assert found != busy and busy < found < busy + 30 and desktop.port_is_free(found)
    assert desktop.find_port(busy) == busy or desktop.port_is_free(busy)           # free again once released
    with socket.socket() as taken:
        taken.bind(('127.0.0.1', 0))
        taken.listen(1)
        with pytest.raises(OSError):
            desktop.find_port(taken.getsockname()[1], tries=1)


class _Page(http.server.BaseHTTPRequestHandler):
    body = b'<html><title>IBS Book Writer - Log in</title></html>'

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


def serve_page(body):
    handler = type('Handler', (_Page,), {'body': body})
    server = http.server.HTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_running_copy_is_recognised_by_its_login_page_and_other_servers_are_not():
    ours, other = serve_page(_Page.body), serve_page(b'<html>something else entirely</html>')
    try:
        assert desktop.is_ours(ours.server_port) is True
        assert desktop.is_ours(other.server_port) is False
        assert desktop.is_ours(free_port(), timeout=0.3) is False
    finally:
        ours.shutdown()
        other.shutdown()


def test_instance_file_is_trusted_only_while_that_copy_really_answers(tmp_path):
    assert desktop.running_instance(tmp_path) is None                              # no file
    (tmp_path / desktop.INSTANCE_FILE).write_text('not json')
    assert desktop.running_instance(tmp_path) is None
    server = serve_page(_Page.body)
    try:
        (tmp_path / desktop.INSTANCE_FILE).write_text(json.dumps({'pid': 1, 'port': server.server_port}))
        assert desktop.running_instance(tmp_path) == server.server_port
    finally:
        server.shutdown()
        server.server_close()
    assert desktop.running_instance(tmp_path) is None                              # stale: nothing answers now


def test_record_instance_writes_pid_and_port(tmp_path):
    desktop.record_instance(tmp_path, 5123)
    info = json.loads((tmp_path / desktop.INSTANCE_FILE).read_text())
    assert info['port'] == 5123 and info['pid'] == os.getpid()


def test_fontconfig_file_lists_only_the_bundled_fonts_and_escapes_paths():
    text_ = desktop.fontconfig_text(PurePosixPath('/opt/a&b/fonts'), PurePosixPath('/home/u/<cache>'))
    assert '<dir>/opt/a&amp;b/fonts</dir>' in text_ and '<cachedir>/home/u/&lt;cache&gt;</cachedir>' in text_
    assert text_.count('<dir>') == 1 and text_.startswith('<?xml')


def test_prepare_environment_sets_desktop_mode_and_the_font_configuration(monkeypatch, tmp_path):
    for name in ('IBS_DESKTOP', 'IBS_DATA_DIR', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH'):
        monkeypatch.delenv(name, raising=False)
    data = desktop.prepare_environment(str(tmp_path / 'D'), bundled_fontconfig=True)
    assert data == tmp_path / 'D' and os.environ['IBS_DESKTOP'] == '1'
    conf = Path(os.environ['FONTCONFIG_FILE'])
    assert conf == data / 'fontconfig' / 'fonts.conf' and str(paths.fonts_dir()) in conf.read_text()
    assert (data / 'fontconfig' / 'cache').is_dir()
    for name in ('IBS_DESKTOP', 'IBS_DATA_DIR', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH'):
        monkeypatch.delenv(name, raising=False)


def start_program(data_dir, port, *extra):
    env = clean_env(HOME=str(data_dir.parent))
    return subprocess.Popen([sys.executable, str(APP / 'desktop.py'), '--no-browser', '--port', str(port),
                             '--data-dir', str(data_dir), *extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env, cwd=str(data_dir.parent))


def wait_for(port, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if desktop.is_ours(port, timeout=0.5):
            return True
        time.sleep(0.25)
    return False


def test_the_real_program_starts_serves_one_copy_and_keeps_its_data_in_its_folder(tmp_path):
    data = tmp_path / 'data'
    port = free_port()
    process = start_program(data, port)
    try:
        assert wait_for(port), process.stdout.read() if process.poll() is not None else 'did not start'
        assert (data / 'ibsbook.db').is_file() and (data / 'secret_key').is_file() and (data / desktop.INSTANCE_FILE).is_file()
        assert json.loads((data / desktop.INSTANCE_FILE).read_text())['port'] == port

        # a second launch with the same data folder opens the running copy and does not start another server
        second = start_program(data, port + 1)
        output, _ = second.communicate(timeout=60)
        assert second.returncode == 0 and 'already running' in output and f':{port}/' in output
        assert desktop.port_is_free(port + 1)

        # and the app works: register, create a book, add a chapter, generate a PDF
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        base = f'http://127.0.0.1:{port}'
        token = lambda page: re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()

        def post(path, **form):
            page = opener.open(base + (path if path.startswith('/books/new') or path in ('/register',) else '/books')).read()
            form['csrf_token'] = token(page)
            return opener.open(urllib.request.Request(base + path, urllib.parse.urlencode(form).encode()))

        post('/register', username='desk', password='correct-horse-battery', confirm_password='correct-horse-battery')
        created = post('/books/new', title='Desktop Book', author_name='Me')
        book_url = created.geturl()
        assert re.search(r'/books/\d+$', book_url)
        page = opener.open(book_url).read()
        chapter = opener.open(urllib.request.Request(
            base + f'/books/{book_url.rsplit("/", 1)[-1]}/chapters/new',
            urllib.parse.urlencode({'title': 'One', 'csrf_token': token(page)}).encode()))
        assert '/chapters/' in chapter.geturl()
        pdf = opener.open(book_url.replace('/books/', '/books/') + '/export/pdf').read()
        assert pdf.startswith(b'%PDF') and len(PdfReader(io.BytesIO(pdf)).pages) >= 3
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
    assert not (data / desktop.INSTANCE_FILE).exists() or not desktop.is_ours(port, timeout=0.3)


# ---- PostgreSQL setup ---------------------------------------------------------------------------------------------------

def test_env_writer_updates_keeps_and_protects(tmp_path):
    env = tmp_path / '.env'
    env.write_text('# comment kept\nDB_HOST=old\nOTHER=1\n')
    awkward = "p@ss 'q' \"d\" \\b $HOME #h = x"
    pgsetup.write_env(env, {'DB_HOST': 'new', 'DB_PASSWORD': awkward, 'DB_PORT': '5432'})
    values = dotenv_values(env, interpolate=False)
    assert values['DB_PASSWORD'] == awkward and values['DB_HOST'] == 'new' and values['OTHER'] == '1'
    assert env.read_text().startswith('# comment kept') and env.read_text().count('DB_HOST=') == 1
    assert has_mode(env, 0o600)


def run_setup(tmp_path, answers, password=''):
    said, asked = [], iter(answers)
    code = pgsetup.run_interactive(tmp_path, ask=lambda prompt: next(asked), ask_password=lambda prompt: password,
                                   say=lambda message='': said.append(message))
    return code, '\n'.join(said)


def test_postgres_setup_rejects_bad_input_and_failed_connections_without_saving(tmp_path):
    code, said = run_setup(tmp_path, ['localhost', 'abc', 'db', 'me'])
    assert code == 1 and 'port must be a number' in said and not (tmp_path / '.env').exists()
    code, said = run_setup(tmp_path, ['localhost', '5432', 'bad name; DROP', 'me'])
    assert code == 1 and 'letters, digits and underscores' in said and not (tmp_path / '.env').exists()
    code, said = run_setup(tmp_path, ['127.0.0.1', str(free_port()), 'books', 'me'])         # nothing listens there
    assert code == 1 and 'Could not prepare the database' in said and not (tmp_path / '.env').exists()


@pytest.mark.skipif(not os.environ.get('IBS_TEST_PG'), reason='set IBS_TEST_PG=host,port,user,password to test against a real server')
def test_postgres_setup_against_a_real_server(tmp_path):
    host, port, user, password = (os.environ['IBS_TEST_PG'].split(',') + ['', '', '', ''])[:4]
    import psycopg2
    name = f'ibs_pgsetup_test_{os.getpid()}'
    try:
        assert pgsetup.apply_schema(host, port, name, user, password) is True            # created
        assert pgsetup.apply_schema(host, port, name, user, password) is False           # again: nothing to create
        connection = psycopg2.connect(host=host, port=int(port), dbname=name, user=user, password=password or None)
        with connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'scm_bookwriter'")
            assert cursor.fetchone()[0] == 13
        connection.close()
        code, said = run_setup(tmp_path, [host, port, name, user], password)
        assert code == 0 and dotenv_values(tmp_path / '.env')['DB_NAME'] == name
    finally:
        admin = psycopg2.connect(host=host, port=int(port), dbname='postgres', user=user, password=password or None)
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS {name}')
        admin.close()


# ---- the bundled fonts --------------------------------------------------------------------------------------------------

def test_every_bundled_font_file_is_present_and_is_a_truetype_font():
    assert len(ALLOWED_FONT_FILES) == 12
    for name in ALLOWED_FONT_FILES:
        data = (paths.fonts_dir() / name).read_bytes()
        assert data[:4] == b'\x00\x01\x00\x00' and len(data) > 100_000, name
    assert (paths.fonts_dir() / 'LICENSES.txt').read_text().count('Open Font License') >= 1


def test_font_rules_cover_every_family_and_style():
    css = font_face_css()
    assert css.count('@font-face') == 12
    for family, files in BUNDLED_FONT_FILES.items():
        assert css.count(f'font-family: "{family}"') == 4
        assert all(f'{FONT_SCHEME}{name}' in css for name in files)
    assert 'font-style: italic; font-weight: 700' in css and font_face_css() in pdf_css(DEFAULTS)


def test_the_font_fetcher_serves_only_the_bundled_files(tmp_path):
    fetcher = MediaFetcher(1, tmp_path)
    for name in ALLOWED_FONT_FILES:
        response = fetcher.fetch(f'{FONT_SCHEME}{name}')
        assert response.headers['Content-Type'] == 'font/ttf'
    for bad in ('../models.py', '..%2fmodels.py', 'LiberationSerif-Regular.ttf/../../config.py', '/etc/passwd',
                'LiberationSerif-Regular.TTF', 'Unknown.ttf', 'LICENSES.txt', '', 'liberationserif-regular.ttf',
                'LiberationSerif-Regular.ttf?x=1', 'C:\\Windows\\win.ini'):
        with pytest.raises(ValueError):
            fetcher.fetch(f'{FONT_SCHEME}{bad}')
    with pytest.raises(ValueError):
        fetcher.fetch('file:///etc/passwd')


def test_the_pdf_uses_the_bundled_fonts(app):
    clear_cache()
    user = make_user()
    book, _ = make_book(user, chapters=1, paragraphs=2, settings=NO_HYPHEN)
    result = get_layout(book)
    fonts = set()
    for page in PdfReader(io.BytesIO(result.pdf)).pages:
        for ref in (page['/Resources'].get('/Font') or {}).values():
            fonts.add(str(ref.get_object().get('/BaseFont')).split('+')[-1])
    assert fonts and all(name.startswith('Liberation-Serif') for name in fonts), fonts
    clear_cache()
