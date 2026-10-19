# IBS Book Writer

A small multi-user web app for writing books. Each user logs in with a username and password, can keep any number of books, and edits each book's details, cover and chapters in the browser.

## Features

- **Accounts**: username + simple password (minimum 8 characters, stored hashed). The first account created is the administrator.
- **Dashboard**: stat cards (books, drafts, completed, chapters, content blocks, images), recently modified books, status of your latest book (chapters, blocks, word count) and quick actions.
- **Multiple books per user**: a "My Books" page; each book belongs to one user and is invisible to everyone else.
- **Book cover**: five editable panels per book - front, spine (binding), back, inside front and inside back - each with Markdown text, background/text colors and an optional image. A flat wrap-around layout view shows how the panels fit together.
- **Chapters and content blocks**: ordered chapters made of typed blocks - Markdown text, heading (3 sizes), bulleted/numbered list, table (`a | b` rows with optional header row), image (with caption) and icon. Add, edit, reorder and delete blocks; deleting offers **Undo** (button or Ctrl+Z) for 10 seconds.
- **Media library**: every image you upload (cover panels or Image/Icon blocks) is kept in your private library, where you can reuse it, see where it is used, and delete unused images.
- **Completed books**: mark a book as completed to make it read-only. To change it later, "Create Editable Copy" shows a warning and makes a new draft (cover, chapters and all); the completed original is never modified.
- **Dedication and Quote pages**: each on its own page after the title page, with its own alignment, position, size and italics. A Quote page holds a verse or epigraph with its source (for example a Tao Teh Ching passage); a book can have several.
- **Authors**: every book has its own authors, each with a bio and photo that are kept *with the book* (so a completed or copied book keeps the bio as written). Shown on an About the Author page.
- **Glossary and Index**: one Terms screen manages both. Glossary words in the text link to their entry, glossary entries list the pages where the word is used, and the Index lists every term with its page numbers. Whole-word matching (hyphenated compounds don't match), optional plurals, extra spellings, and the longest term wins.
- **Layout and Page view**: trim size, margins, one or two columns, font, spacing, page numbering and more. The Page view is the real PDF layout, so Index and Glossary page numbers match what you see.
- **Export**: download the book as **EPUB 3** (validated with EPUBCheck, with contents, glossary links, index and a print page list) or as a **PDF**.
- **Preview**: read-only HTML preview of covers, front matter, chapters and authors.

## Quick start

Requirements: Python 3.10+, PostgreSQL 13+ (psql client), and for PDF/EPUB export the Pango text libraries
that WeasyPrint uses (on Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 fontconfig fonts-liberation`).

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
  books.py            dashboard, My Books, create/edit, complete, copy, delete, preview
  covers.py           cover editor
  chapters.py         chapters and content-block routes
  blocks.py           parsing/validation of every block type
  media.py            image upload, media library, owner-only file serving
  matter.py           Dedication/Quote pages and authors
  terms.py            term matching for the Glossary and Index
  terms_routes.py     the Terms screen
  layout.py           page layout settings and the PDF/EPUB stylesheets
  bookdoc.py          the book as one document (feeds PDF and EPUB)
  render.py           PDF layout and the real page numbers
  epub.py             EPUB 3 builder
  exports.py          layout screen, Page view, PDF/EPUB downloads
  settings_routes.py  admin-only database settings
  access.py           ownership checks and the completed-book edit lock
  templates/, static/
sql/schema.sql        PostgreSQL schema (schema scm_bookwriter), safe to re-run to upgrade
scripts/set_env.py    helper used by the shell scripts to update .env
scripts/import_terran_book.py   one-off import of the Terran Society manuscript
scripts/upgrade_terran_book.py  one-off move of that book onto front matter, terms and authors
tests/                pytest suite (runs on in-memory SQLite; EPUBCheck tests need Java)
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
- The PDF renderer can only read the book owner's own media files; every other URL and local file is refused.
- Uploaded images are type-checked by extension and file signature, stored outside `static/`, and served only to their owner. User Markdown is sanitised before display.
- Serve behind HTTPS in production and set `SESSION_COOKIE_SECURE=1`. See [DEPLOYMENT.md](DEPLOYMENT.md).
