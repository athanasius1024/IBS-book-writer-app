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
- **Editable Contents**: the Contents page is automatic until you click *Customize contents*. Then you can rename, hide, indent and reorder lines, list the headings inside chapters, add part dividers such as "Part One", and reset to automatic at any time. Page numbers are always filled in automatically.
- **Pictures inside chapter text**: *Insert image* in a text block opens your media library. Drag on the picture to **crop** it, set its **width** (10-100% of the text width), its placement (left, centre, right) and a caption. Your original file is never changed; cropped copies are made once and cached. Reopen a picture reference in the editor to adjust it.
- **Chapter epigraphs**: an optional quotation and its source under each chapter title, in one book-wide style (placement, size, italics) set on the layout page. Quoted words are not linked as glossary words and do not appear in the Index.
- **Version and date stamp**: a small line, `Version 0.3 - Generated October 20, 2026`, at the bottom of the Contents of every generated book.
- **Stored books**: generate **PDF, EPUB, HTML and ODT** copies and keep them (up to 10 per format). Each copy shows its version, date and whether the book has changed since (*Out of date*). **Download** any copy (your browser's Save dialog picks the folder or drive), **download several as one zip**, **print** a PDF or HTML copy (your browser's print dialog lists your printers), **replace** a copy with a freshly generated version, or **delete** it. Optionally set `EXPORT_DIR` to also offer one-click *Save to the export folder*.
- **Export formats**: **EPUB 3** (validated with EPUBCheck, with contents, glossary links, index and a print page list), **PDF**, one-file **HTML** (pictures embedded, works offline) and **ODT** (OpenDocument text for LibreOffice or Word, validated with the ODF validator; its Index and Glossary point at chapters because an editable document reflows).
- **Preview**: read-only HTML preview of covers, front matter, chapters (with epigraphs and pictures) and authors.

## Quick start

Requirements: Python 3.10+, PostgreSQL 13+ (psql client), and for PDF/EPUB export the Pango text libraries
that WeasyPrint uses (on Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 fontconfig fonts-liberation`).

```bash
./setup_database.sh   # creates db_ibs_bookwriter + tables, writes connection settings to .env
./start.sh            # creates .venv, installs dependencies, starts the app
```

Open <http://127.0.0.1:5000> and create your account at `/register`.

`start.sh` generates a `SECRET_KEY` in `.env` on first run. `.env` is git-ignored and mode 600. See `.env.template` for all settings (database, `ALLOW_REGISTRATION`, `SESSION_COOKIE_SECURE`, `UPLOAD_DIR`, `EXPORT_DIR`, `HOST`, `PORT`).

**Upgrading an existing installation:** back up, pull the new code, then re-run `psql -d db_ibs_bookwriter -f sql/schema.sql` (it only adds what is missing) and restart. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Project layout

```
app/
  ibsbook.py          application factory / entry point
  config.py           environment-based configuration
  models.py           User, Book, BookCover, Chapter, ContentBlock, MediaAsset, BookTocEntry, MediaDerivative, RenderedBook
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
  bookdoc.py          the book as one document (feeds every format)
  toc.py, contents.py the Contents: automatic and edited lists, the stamp, the editor
  imagespec.py, imaging.py  inline pictures: crop/width parsing, cached cropped copies, HTML finishing
  render.py           PDF layout and the real page numbers
  epub.py, html_export.py, odt.py   EPUB 3, one-file HTML and OpenDocument text builders
  renders.py          stored books: generate, replace, delete, download, view, print, zip, export folder
  exports.py          layout screen, Page view, PDF/EPUB downloads
  settings_routes.py  admin-only database settings
  access.py           ownership checks and the completed-book edit lock
  templates/, static/
sql/schema.sql        PostgreSQL schema (schema scm_bookwriter), safe to re-run to upgrade
scripts/set_env.py    helper used by the shell scripts to update .env
scripts/import_terran_book.py   one-off import of the Terran Society manuscript
scripts/upgrade_terran_book.py  one-off move of that book onto front matter, terms and authors
tests/                pytest suite (runs on in-memory SQLite). EPUBCheck, ODF validator and LibreOffice tests
                      run when Java / the validator jar / LibreOffice are installed and are skipped otherwise;
                      tests/js has the Node unit tests for the crop maths; tests/browser drives the image
                      dialog in a real Chromium (optional, see the file header)
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
- The PDF renderer, the EPUB, HTML and ODT builders can only read the book owner's own media files (including cropped copies); every other URL and local file is refused. A picture reference in chapter text that points anywhere else is removed.
- Stored books are served only to their owner under generated file names. A stored HTML book is shown with a locked-down Content-Security-Policy (no network, no scripts, sandboxed); printing allows exactly one nonce-protected script.
- Uploaded images are type-checked by extension and file signature, stored outside `static/`, and served only to their owner. User Markdown is sanitised before display.
- Serve behind HTTPS in production (gunicorn + systemd + nginx) and set `SESSION_COOKIE_SECURE=1`. [DEPLOYMENT.md](DEPLOYMENT.md) documents the current setup and gives step-by-step production instructions, with ready-made files in `deploy/`.
