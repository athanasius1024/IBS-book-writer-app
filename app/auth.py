"""Login, registration and logout."""
import re
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db

bp = Blueprint('auth', __name__)

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,50}$')
# Used to keep login timing similar for unknown usernames.
_DUMMY_HASH = generate_password_hash('not-a-real-password')


def _safe_next(target):
    """Only allow same-site relative redirects."""
    if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return None


def _registration_open():
    return current_app.config.get('ALLOW_REGISTRATION', True) or User.query.count() == 0


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('books.dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(username_key=username.lower()).first()
        if user is not None:
            valid = user.check_password(password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            valid = False
        if valid:
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            return redirect(_safe_next(request.args.get('next')) or url_for('books.dashboard'))
        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html', registration_open=_registration_open())


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('books.dashboard'))
    if not _registration_open():
        flash('Registration is closed.', 'warning')
        return redirect(url_for('auth.login'))

    username = ''
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        min_len = current_app.config['MIN_PASSWORD_LENGTH']

        error = None
        if not USERNAME_RE.match(username):
            error = 'Username must be 3-50 characters: letters, numbers, dot, dash or underscore.'
        elif len(password) < min_len:
            error = f'Password must be at least {min_len} characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.query.filter_by(username_key=username.lower()).first():
            error = 'That username is already taken.'

        if error:
            flash(error, 'danger')
        else:
            user = User(username=username, username_key=username.lower(),
                        is_admin=User.query.count() == 0)  # first account administers the app
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('That username is already taken.', 'danger')
            else:
                login_user(user)
                flash('Welcome! Your account has been created.', 'success')
                return redirect(url_for('books.dashboard'))

    return render_template('auth/register.html', username=username,
                           min_len=current_app.config['MIN_PASSWORD_LENGTH'])


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
