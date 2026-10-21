-- IBS Book Writer: PostgreSQL schema.
-- Usage: psql -d db_ibs_bookwriter -f sql/schema.sql
-- Idempotent: safe to re-run.

CREATE SCHEMA IF NOT EXISTS scm_bookwriter;
SET search_path TO scm_bookwriter;

CREATE TABLE IF NOT EXISTS app_user (
    user_id        SERIAL PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL,
    username_key   VARCHAR(50)  NOT NULL UNIQUE,   -- lower-cased, for case-insensitive uniqueness
    password_hash  TEXT         NOT NULL,
    is_admin       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media_asset (
    asset_id    SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    asset_name  TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,                  -- relative to UPLOAD_DIR
    file_size   INTEGER,
    mime_type   TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_media_asset_user_id ON media_asset(user_id);

CREATE TABLE IF NOT EXISTS book (
    book_id               SERIAL PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    title                 TEXT    NOT NULL,
    subtitle              TEXT,
    author_name           TEXT,
    copyright_holder      TEXT,
    copyright_year        INTEGER,
    version               VARCHAR(20) NOT NULL DEFAULT '0.1',
    status                VARCHAR(20) NOT NULL DEFAULT 'draft',
    completed_at          TIMESTAMP,
    derived_from_book_id  INTEGER REFERENCES book(book_id) ON DELETE SET NULL,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_book_status CHECK (status IN ('draft', 'completed'))
);
CREATE INDEX IF NOT EXISTS ix_book_user_id ON book(user_id);

CREATE TABLE IF NOT EXISTS book_cover (
    cover_id          SERIAL PRIMARY KEY,
    book_id           INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    panel             VARCHAR(20) NOT NULL,
    content_text      TEXT DEFAULT '',
    asset_id          INTEGER REFERENCES media_asset(asset_id) ON DELETE SET NULL,
    background_color  VARCHAR(7) NOT NULL DEFAULT '#ffffff',
    text_color        VARCHAR(7) NOT NULL DEFAULT '#000000',
    modified_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_book_cover_panel UNIQUE (book_id, panel),
    CONSTRAINT ck_book_cover_panel CHECK (panel IN ('front', 'spine', 'back', 'inside_front', 'inside_back'))
);
CREATE INDEX IF NOT EXISTS ix_book_cover_book_id ON book_cover(book_id);

CREATE TABLE IF NOT EXISTS chapter (
    chapter_id   SERIAL PRIMARY KEY,
    book_id      INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    epigraph_text    TEXT,                          -- Markdown, line breaks kept as written
    epigraph_source  TEXT,                          -- attribution
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_chapter_book_id ON chapter(book_id);

CREATE TABLE IF NOT EXISTS content_block (
    block_id      SERIAL PRIMARY KEY,
    chapter_id    INTEGER NOT NULL REFERENCES chapter(chapter_id) ON DELETE CASCADE,
    block_type    VARCHAR(20) NOT NULL DEFAULT 'text',
    content_text  TEXT    NOT NULL DEFAULT '',     -- markdown / list items / table source / caption
    content_data  JSON,                            -- heading level, list style, parsed table
    asset_id      INTEGER REFERENCES media_asset(asset_id) ON DELETE SET NULL,  -- image / icon
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Upgrade path for databases created before block types existed (no-ops on fresh installs).
ALTER TABLE content_block ADD COLUMN IF NOT EXISTS block_type   VARCHAR(20) NOT NULL DEFAULT 'text';
ALTER TABLE content_block ADD COLUMN IF NOT EXISTS content_data JSON;
ALTER TABLE content_block ADD COLUMN IF NOT EXISTS asset_id     INTEGER REFERENCES media_asset(asset_id) ON DELETE SET NULL;
ALTER TABLE content_block DROP CONSTRAINT IF EXISTS ck_content_block_type;
ALTER TABLE content_block ADD CONSTRAINT ck_content_block_type
    CHECK (block_type IN ('text', 'heading', 'list', 'table', 'image', 'icon'));

CREATE INDEX IF NOT EXISTS ix_content_block_chapter_id ON content_block(chapter_id);
CREATE INDEX IF NOT EXISTS ix_content_block_asset_id ON content_block(asset_id);

-- Page layout settings, front matter pages, authors and glossary/index terms.
CREATE TABLE IF NOT EXISTS book_layout (
    layout_id    SERIAL PRIMARY KEY,
    book_id      INTEGER NOT NULL UNIQUE REFERENCES book(book_id) ON DELETE CASCADE,
    settings     JSON,
    modified_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS book_page (
    page_id      SERIAL PRIMARY KEY,
    book_id      INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    page_type    VARCHAR(20) NOT NULL,
    body         TEXT NOT NULL DEFAULT '',          -- markdown
    attribution  TEXT,
    style        JSON,                              -- align, valign, italic, size
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_book_page_type CHECK (page_type IN ('dedication', 'quote'))
);
CREATE INDEX IF NOT EXISTS ix_book_page_book_id ON book_page(book_id);

CREATE TABLE IF NOT EXISTS book_author (
    author_id       SERIAL PRIMARY KEY,
    book_id         INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    role            TEXT,
    bio             TEXT,                           -- markdown; belongs to the book
    photo_asset_id  INTEGER REFERENCES media_asset(asset_id) ON DELETE SET NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_book_author_book_id ON book_author(book_id);

CREATE TABLE IF NOT EXISTS book_term (
    term_id       SERIAL PRIMARY KEY,
    book_id       INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    term          TEXT NOT NULL,
    definition    TEXT,
    variants      TEXT,                             -- extra spellings, one per line
    match_plural  BOOLEAN NOT NULL DEFAULT TRUE,
    match_case    BOOLEAN NOT NULL DEFAULT FALSE,
    in_index      BOOLEAN NOT NULL DEFAULT TRUE,
    in_glossary   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_book_term_book_id ON book_term(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_book_term_name ON book_term(book_id, lower(term));

-- Chapter epigraphs (additive).
ALTER TABLE chapter ADD COLUMN IF NOT EXISTS epigraph_text   TEXT;
ALTER TABLE chapter ADD COLUMN IF NOT EXISTS epigraph_source TEXT;

-- Edited Contents page: a book with no rows here uses the automatic Contents.
CREATE TABLE IF NOT EXISTS book_toc_entry (
    entry_id     SERIAL PRIMARY KEY,
    book_id      INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    kind         VARCHAR(20) NOT NULL,
    chapter_id   INTEGER REFERENCES chapter(chapter_id) ON DELETE CASCADE,
    block_id     INTEGER REFERENCES content_block(block_id) ON DELETE CASCADE,
    section_key  VARCHAR(20),
    label        TEXT,
    level        INTEGER NOT NULL DEFAULT 0,
    visible      BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_toc_kind    CHECK (kind IN ('chapter', 'heading', 'section', 'part')),
    CONSTRAINT ck_toc_level   CHECK (level BETWEEN 0 AND 2),
    CONSTRAINT ck_toc_section CHECK (section_key IS NULL OR section_key IN ('glossary', 'index', 'about'))
);
CREATE INDEX IF NOT EXISTS ix_book_toc_entry_book_id    ON book_toc_entry(book_id);
CREATE INDEX IF NOT EXISTS ix_book_toc_entry_chapter_id ON book_toc_entry(chapter_id);
CREATE INDEX IF NOT EXISTS ix_book_toc_entry_block_id   ON book_toc_entry(block_id);

-- Cached cropped / downsized copies of media assets (crop in ten-thousandths of the original).
CREATE TABLE IF NOT EXISTS media_derivative (
    derivative_id  SERIAL PRIMARY KEY,
    asset_id       INTEGER NOT NULL REFERENCES media_asset(asset_id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    crop_x         INTEGER NOT NULL DEFAULT 0,
    crop_y         INTEGER NOT NULL DEFAULT 0,
    crop_w         INTEGER NOT NULL DEFAULT 10000,
    crop_h         INTEGER NOT NULL DEFAULT 10000,
    max_px         INTEGER NOT NULL DEFAULT 2000,
    file_path      TEXT    NOT NULL,                  -- relative to UPLOAD_DIR
    mime_type      TEXT,
    file_size      INTEGER,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_media_derivative_spec UNIQUE (asset_id, crop_x, crop_y, crop_w, crop_h, max_px)
);
CREATE INDEX IF NOT EXISTS ix_media_derivative_asset_id ON media_derivative(asset_id);
CREATE INDEX IF NOT EXISTS ix_media_derivative_user_id  ON media_derivative(user_id);

-- Stored generated books (PDF, EPUB, HTML, ODT) that the author keeps, replaces or deletes.
CREATE TABLE IF NOT EXISTS rendered_book (
    render_id         SERIAL PRIMARY KEY,
    book_id           INTEGER NOT NULL REFERENCES book(book_id) ON DELETE CASCADE,
    user_id           INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    format            VARCHAR(10) NOT NULL,
    file_path         TEXT    NOT NULL,               -- relative to UPLOAD_DIR
    file_name         TEXT    NOT NULL,               -- name offered on download
    file_size         INTEGER,
    sha256            VARCHAR(64),
    book_version      VARCHAR(20),
    book_modified_at  TIMESTAMP,                      -- the book's edit time when this was built
    page_count        INTEGER,                        -- PDF only
    generated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_rendered_book_format CHECK (format IN ('pdf', 'epub', 'html', 'odt'))
);
CREATE INDEX IF NOT EXISTS ix_rendered_book_book_id ON rendered_book(book_id);
CREATE INDEX IF NOT EXISTS ix_rendered_book_user_id ON rendered_book(user_id);
