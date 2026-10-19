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
