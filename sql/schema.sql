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
    content_text  TEXT    NOT NULL DEFAULT '',     -- markdown
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_content_block_chapter_id ON content_block(chapter_id);
