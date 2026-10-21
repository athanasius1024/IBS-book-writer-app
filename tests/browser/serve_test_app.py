"""A throwaway copy of the app for the browser test: its own SQLite database and upload folder in a
temporary directory, nothing shared with your real data. Stop it with Ctrl+C.

    python tests/browser/serve_test_app.py          # serves http://127.0.0.1:5099
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
work = Path(tempfile.mkdtemp(prefix='ibs-browser-test-'))
(work / 'uploads').mkdir()
os.environ.update({'BOOKWRITER_SCHEMA': '', 'DATABASE_URL': f'sqlite:///{work / "test.db"}',
                   'SECRET_KEY': 'browser-test-key', 'UPLOAD_DIR': str(work / 'uploads')})
sys.path.insert(0, str(ROOT / 'app'))

from ibsbook import create_app  # noqa: E402
from models import db  # noqa: E402

app = create_app()
with app.app_context():
    db.create_all()
print(f'Test app: data in {work}')
app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5099')), debug=False, threaded=True)
