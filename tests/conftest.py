"""Test fixtures. The suite runs against in-memory SQLite (no Postgres needed)."""
import os
import sys
from pathlib import Path

# Must be set before the app modules are imported.
os.environ['BOOKWRITER_SCHEMA'] = ''
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.pop('SECRET_KEY', None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))

import pytest  # noqa: E402
from flask import g  # noqa: E402

from ibsbook import create_app  # noqa: E402
from models import Book, db  # noqa: E402

PASSWORD = 'correct-horse-battery'


def make_app(tmp_path, **overrides):
    config = {
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'UPLOAD_DIR': tmp_path / 'uploads',
    }
    config.update(overrides)
    application = create_app(config)

    # Tests keep one app context open so they can query the DB directly. Flask reuses
    # that context for every test-client request, which would leak per-request state
    # (Flask-Login's cached user, CSRF token) and the SQLAlchemy identity map between
    # clients. Reset both around each request to mimic production.
    @application.before_request
    def _reset_request_state():
        g.pop('_login_user', None)
        g.pop('csrf_token', None)

    @application.teardown_request
    def _expire_session(_exc):
        db.session.expire_all()

    return application


@pytest.fixture()
def app(tmp_path):
    application = make_app(tmp_path)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, username, password=PASSWORD):
    return client.post('/register', data={
        'username': username, 'password': password, 'confirm_password': password,
    }, follow_redirects=True)


@pytest.fixture()
def make_client(app):
    """Factory returning a new client already registered + logged in as ``username``."""
    def factory(username):
        c = app.test_client()
        resp = register(c, username)
        assert resp.status_code == 200
        return c
    return factory


@pytest.fixture()
def alice(make_client):
    return make_client('alice')


@pytest.fixture()
def bob(make_client, alice):  # alice first so she is the admin
    return make_client('bob')


def create_book(client, title='My Book', **extra):
    data = {'title': title, 'author_name': 'A. Writer'}
    data.update(extra)
    resp = client.post('/books/new', data=data)
    assert resp.status_code == 302, resp.data
    return int(resp.headers['Location'].rstrip('/').rsplit('/', 1)[-1])


def get_book(book_id):
    return db.session.get(Book, book_id)


PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
