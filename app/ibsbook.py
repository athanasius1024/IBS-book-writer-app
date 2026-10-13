"""IBS Book Writer - Flask application factory.

Run locally:   python3 ibsbook.py
WSGI servers:  gunicorn "ibsbook:create_app()"
"""
import os
import secrets

import bleach
import markdown as md
from flask import Flask, render_template, request
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup

import config
from models import COVER_PANELS, User, db

login_manager = LoginManager()
csrf = CSRFProtect()

_MD_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'hr', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'sup', 'sub',
]
_MD_ATTRS = {'a': ['href', 'title'], 'abbr': ['title'], 'acronym': ['title']}


def render_markdown(text):
    """Render user markdown to sanitised HTML (raw HTML/script is stripped)."""
    html = md.markdown(text or '', extensions=['extra', 'sane_lists'])
    clean = bleach.clean(html, tags=_MD_TAGS, attributes=_MD_ATTRS,
                         protocols=['http', 'https', 'mailto'], strip=True)
    return Markup(clean)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(config)
    app.config['SQLALCHEMY_DATABASE_URI'] = config.build_database_uri()
    if overrides:
        app.config.update(overrides)

    if not app.config.get('SECRET_KEY'):
        if app.config.get('TESTING') or os.environ.get('IBS_DEV') == '1':
            app.config['SECRET_KEY'] = secrets.token_hex(32)  # ephemeral, dev/test only
        else:
            raise RuntimeError(
                'SECRET_KEY is not set. Set it in the environment or in .env '
                '(start.sh generates one for you on first run).')

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    from auth import bp as auth_bp
    from books import bp as books_bp
    from covers import bp as covers_bp
    from chapters import bp as chapters_bp
    from media import bp as media_bp
    from settings_routes import bp as settings_bp
    for blueprint in (auth_bp, books_bp, covers_bp, chapters_bp, media_bp, settings_bp):
        app.register_blueprint(blueprint)

    app.jinja_env.filters['markdown'] = render_markdown

    @app.context_processor
    def inject_globals():
        return {'COVER_PANELS': COVER_PANELS,
                'allow_registration': app.config.get('ALLOW_REGISTRATION', True)}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        if current_user.is_authenticated and not request.path.startswith('/static/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    @app.errorhandler(404)
    def not_found(_error):
        return render_template('error.html', code=404, message='Page not found.'), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template('error.html', code=413, message='That file is too large.'), 413

    return app


if __name__ == '__main__':
    debug = os.environ.get('IBS_DEBUG') == '1'
    if debug:
        os.environ.setdefault('IBS_DEV', '1')
    create_app().run(host=os.environ.get('HOST', '127.0.0.1'),
                     port=int(os.environ.get('PORT', '5000')), debug=debug)
