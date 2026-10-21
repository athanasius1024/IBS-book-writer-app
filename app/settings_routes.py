"""Admin-only database connection settings."""
import json
import os

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

import config
from access import admin_required

bp = Blueprint('settings', __name__)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@bp.route('/settings/database', methods=['GET', 'POST'])
@login_required
@admin_required
def database_settings():
    if config.BACKEND == 'sqlite':
        return render_template('settings/sqlite.html', path=config.SQLITE_PATH, data_dir=config.DATA_DIR,
                               env_file=config.ENV_FILE)
    config_file = config.DB_CONFIG_FILE
    saved = config.load_db_config_file()

    if request.method == 'POST':
        db_config = {
            'host': (request.form.get('host') or 'localhost').strip(),
            'port': _int(request.form.get('port'), 5432),
            'database': (request.form.get('database') or '').strip(),
            'user': (request.form.get('user') or '').strip(),
            # Blank password keeps the previously saved one.
            'password': request.form.get('password') or saved.get('password', ''),
        }
        if not db_config['database'] or not db_config['user']:
            flash('Database name and user are required.', 'danger')
        else:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(config_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(db_config, handle, indent=2)
            flash('Database configuration saved. Restart the application for it to take effect. '
                  '(DB_* environment variables, if set, take precedence.)', 'success')
            return redirect(url_for('settings.database_settings'))

    form_values = {'host': 'localhost', 'port': 5432, 'database': 'db_ibs_bookwriter', 'user': 'rock'}
    form_values.update({k: v for k, v in saved.items() if k != 'password'})
    return render_template('settings/database.html', config=form_values,
                           has_password=bool(saved.get('password')))


@bp.route('/settings/database/test', methods=['POST'])
@login_required
@admin_required
def test_database_connection():
    import psycopg2

    data = request.get_json(silent=True) or {}
    password = data.get('password') or config.load_db_config_file().get('password', '')
    try:
        conn = psycopg2.connect(
            host=data.get('host') or 'localhost',
            port=_int(data.get('port'), 5432),
            dbname=data['database'],
            user=data['user'],
            password=password,
            connect_timeout=5,
        )
        with conn, conn.cursor() as cur:
            cur.execute('SELECT version();')
            version = cur.fetchone()[0]
        conn.close()
        return jsonify({'success': True, 'message': 'Connection successful!', 'version': version})
    except KeyError:
        return jsonify({'success': False, 'error': 'Database and user are required.'}), 400
    except psycopg2.Error as exc:
        current_app.logger.info('DB connection test failed: %s', exc)
        return jsonify({'success': False, 'error': f'Connection failed: {exc}'}), 400
