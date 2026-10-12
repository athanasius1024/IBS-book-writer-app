-- Migration: Add book metadata tables for front matter
-- Date: 2025-12-28

-- Book metadata (global settings for the book)
CREATE TABLE IF NOT EXISTS scm_terran_society.book_metadata (
    metadata_id SERIAL PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Terran Society: A New Social Contract',
    subtitle TEXT,
    copyright_holder TEXT DEFAULT 'Terran Society',
    copyright_year INTEGER DEFAULT EXTRACT(YEAR FROM CURRENT_DATE),
    dedication_text TEXT,
    dedication_attribution TEXT,
    current_version TEXT DEFAULT '0.1',
    version_date DATE DEFAULT CURRENT_DATE,
    draft_watermark BOOLEAN DEFAULT TRUE,
    header_odd_template TEXT DEFAULT 'Terran Society: A New Social Contract    {chapter_title}',
    header_even_template TEXT DEFAULT '{section_title}    Terran Society',
    footer_template TEXT DEFAULT '{page_number}    Draft v{version} – {date}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT single_metadata CHECK (metadata_id = 1)
);

-- Book authors
CREATE TABLE IF NOT EXISTS scm_terran_society.book_author (
    author_id SERIAL PRIMARY KEY,
    author_name TEXT NOT NULL,
    author_bio TEXT,
    author_role TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create trigger for modified_at
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS book_metadata_modified ON scm_terran_society.book_metadata;
CREATE TRIGGER book_metadata_modified
    BEFORE UPDATE ON scm_terran_society.book_metadata
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS book_author_modified ON scm_terran_society.book_author;
CREATE TRIGGER book_author_modified
    BEFORE UPDATE ON scm_terran_society.book_author
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Insert default metadata row
INSERT INTO scm_terran_society.book_metadata (
    title,
    subtitle,
    copyright_holder,
    copyright_year,
    dedication_text,
    dedication_attribution,
    current_version,
    draft_watermark
) VALUES (
    'Terran Society: A New Social Contract',
    NULL,
    'Terran Society',
    EXTRACT(YEAR FROM CURRENT_DATE),
    E'Those who know do not speak.\nThose who speak do not know.',
    'Lao Tzu',
    '0.1',
    TRUE
) ON CONFLICT (metadata_id) DO NOTHING;

-- Insert default author
INSERT INTO scm_terran_society.book_author (
    author_name,
    author_role,
    sort_order
) VALUES (
    'Terran Society Contributors',
    'Primary Authors',
    1
);

COMMENT ON TABLE scm_terran_society.book_metadata IS 'Global book settings for manuscript generation including headers, footers, and front matter';
COMMENT ON TABLE scm_terran_society.book_author IS 'Authors and contributors to the book manuscript';
