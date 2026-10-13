import pytest

from conftest import PASSWORD, make_app, register
from ibsbook import create_app
from models import User, db


def test_login_required_redirects(client):
    for path in ('/', '/books/new', '/books/1', '/settings/database'):
        resp = client.get(path)
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']


def test_register_logs_in_and_first_user_is_admin(app, client):
    resp = register(client, 'alice')
    assert b'My Books' in resp.data
    other = app.test_client()
    register(other, 'bob')
    assert User.query.filter_by(username_key='alice').one().is_admin is True
    assert User.query.filter_by(username_key='bob').one().is_admin is False


def test_password_is_hashed(app, client):
    register(client, 'alice')
    user = User.query.filter_by(username_key='alice').one()
    assert user.password_hash != PASSWORD
    assert PASSWORD not in user.password_hash
    assert user.check_password(PASSWORD)


@pytest.mark.parametrize('username,password,confirm,fragment', [
    ('ab', PASSWORD, PASSWORD, b'Username must be'),
    ('bad name!', PASSWORD, PASSWORD, b'Username must be'),
    ('carol', 'short', 'short', b'at least 8'),
    ('carol', PASSWORD, 'different-password', b'do not match'),
])
def test_register_validation(client, username, password, confirm, fragment):
    resp = client.post('/register', data={
        'username': username, 'password': password, 'confirm_password': confirm})
    assert resp.status_code == 200
    assert fragment in resp.data
    assert User.query.count() == 0


def test_duplicate_username_case_insensitive(app, client):
    register(client, 'Alice')
    resp = register(app.test_client(), 'aLiCe')
    assert b'already taken' in resp.data
    assert User.query.count() == 1


def test_login_logout_flow(app, client):
    register(client, 'alice')
    client.post('/logout')
    assert client.get('/').status_code == 302

    bad = client.post('/login', data={'username': 'alice', 'password': 'wrong-password'})
    assert b'Invalid username or password' in bad.data
    assert client.get('/').status_code == 302

    unknown = client.post('/login', data={'username': 'nobody', 'password': PASSWORD})
    assert b'Invalid username or password' in unknown.data

    ok = client.post('/login', data={'username': 'ALICE', 'password': PASSWORD})
    assert ok.status_code == 302
    assert client.get('/').status_code == 200
    assert User.query.filter_by(username_key='alice').one().last_login_at is not None


def test_logout_requires_post(client):
    register(client, 'alice')
    assert client.get('/logout').status_code == 405
    assert client.get('/').status_code == 200  # still logged in


@pytest.mark.parametrize('target', ['//evil.example', 'https://evil.example', '/\\evil.example'])
def test_login_does_not_redirect_off_site(client, target):
    register(client, 'alice')
    client.post('/logout')
    resp = client.post('/login?next=' + target, data={'username': 'alice', 'password': PASSWORD})
    assert resp.status_code == 302
    assert 'evil.example' not in resp.headers['Location']


def test_login_next_relative_path_is_honoured(client):
    register(client, 'alice')
    client.post('/logout')
    resp = client.post('/login?next=/books/new', data={'username': 'alice', 'password': PASSWORD})
    assert resp.headers['Location'].endswith('/books/new')


def test_registration_can_be_closed_after_first_user(tmp_path):
    app = make_app(tmp_path, ALLOW_REGISTRATION=False)
    with app.app_context():
        db.create_all()
        first = app.test_client()
        assert register(first, 'admin').status_code == 200  # bootstrap account allowed
        second = app.test_client()
        resp = second.post('/register', data={'username': 'late', 'password': PASSWORD,
                                              'confirm_password': PASSWORD})
        assert resp.status_code == 302 and '/login' in resp.headers['Location']
        assert User.query.count() == 1


def test_csrf_enforced_when_enabled(tmp_path):
    app = make_app(tmp_path, WTF_CSRF_ENABLED=True)
    with app.app_context():
        db.create_all()
        client = app.test_client()
        resp = client.post('/register', data={'username': 'alice', 'password': PASSWORD,
                                              'confirm_password': PASSWORD})
        assert resp.status_code == 400
        assert User.query.count() == 0


def test_missing_secret_key_is_an_error(monkeypatch):
    monkeypatch.delenv('IBS_DEV', raising=False)
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app({'SECRET_KEY': None, 'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
