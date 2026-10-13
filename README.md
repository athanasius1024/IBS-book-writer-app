# IBS Book Writer

A small multi-user web app for writing books. Each user logs in with a username and password, can keep any number of books, and edits each book's details, cover and chapters in the browser.

## Features

- **Accounts**: username + simple password (minimum 8 characters, stored hashed). The first account created is the administrator.
- **Multiple books per user**: a "My Books" dashboard; each book belongs to one user and is invisible to everyone else.
- **Book cover**: five editable panels per book - front, spine (binding), back, inside front and inside back - each with Markdown text, background/text colors and an optional image. A flat wrap-around layout view shows how the panels fit together.
- **Chapters**: ordered chapters made of Markdown content blocks (add, edit, reorder, delete).
- **Completed books**: mark a book as completed to make it read-only. To change it later, "Create Editable Copy" shows a warning and makes a new draft (cover, chapters and all); the completed original is never modified.
- **Preview**: read-only HTML preview of covers and chapters.

## Quick start

Requirements: Python 3.10+, PostgreSQL 13+ (psql client).

```bash
./setup_database.sh   # creates db_ibs_bookwriter + tables, writes connection settings to .env
./start.sh            # creates .venv, installs dependencies, starts the app
```

Open <http://127.0.0.1:5000> and create your account at `/register`.

`start.sh` generates a `SECRET_KEY` in `.env` on first run. `.env` is git-ignored and mode 600. See `.env.template` for all settings (database, `ALLOW_REGISTRATION`, `SESSION_COOKIE_SECURE`, `UPLOAD_DIR`, `HOST`, `PORT`).

## Project layout

```
app/
  ibsbook.py          application factory / entry point
  config.py           environment-based configuration
  models.py           User, Book, BookCover, Chapter, ContentBlock, MediaAsset
  auth.py             login / register / logout
  books.py            dashboard, create/edit, complete, copy, delete, preview
  covers.py           cover editor
  chapters.py         chapters and content blocks
  media.py            image upload + owner-only file serving
  settings_routes.py  admin-only database settings
  access.py           ownership checks and the completed-book edit lock
  templates/, static/
sql/schema.sql        PostgreSQL schema (schema scm_bookwriter)
scripts/set_env.py    helper used by the shell scripts to update .env
tests/                pytest suite (runs on in-memory SQLite)
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests
IBS_DEBUG=1 ./start.sh   # auto-reload + debugger (local use only)
```

## Security notes

- Passwords are hashed with Werkzeug (`scrypt`/`pbkdf2`); login errors don't reveal whether a username exists.
- All state-changing requests are CSRF-protected (including HTMX requests).
- Every book/cover/chapter/block/media lookup is filtered by the logged-in user; other users' records return 404.
- Completed books are protected on the server, not just hidden in the UI.
- Uploaded images are type-checked by extension and file signature, stored outside `static/`, and served only to their owner. User Markdown is sanitised before display.
- Serve behind HTTPS in production and set `SESSION_COOKIE_SECURE=1`. See [DEPLOYMENT.md](DEPLOYMENT.md).
