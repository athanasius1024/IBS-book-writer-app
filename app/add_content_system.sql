-- Content Management System for Terran Society
-- Adds support for rich content (text, tables, charts, images, icons)

-- Media assets (images, icons, documents)
CREATE TABLE scm_terran_society.media_asset (
    asset_id SERIAL PRIMARY KEY,
    asset_name TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('image', 'icon', 'document', 'chart')),
    file_path TEXT NOT NULL,
    file_size INTEGER,
    mime_type TEXT,
    alt_text TEXT,
    caption TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_media_asset_type ON scm_terran_society.media_asset(asset_type);

CREATE TRIGGER media_asset_modified 
    BEFORE UPDATE ON scm_terran_society.media_asset 
    FOR EACH ROW EXECUTE FUNCTION scm_terran_society.update_modified_column();

-- Content blocks (paragraphs, tables, charts, etc.)
CREATE TABLE scm_terran_society.content_block (
    block_id SERIAL PRIMARY KEY,
    block_type TEXT NOT NULL CHECK(block_type IN ('text', 'table', 'chart', 'image', 'icon', 'heading', 'list')),
    content_text TEXT,  -- Markdown text content
    content_data JSONB, -- Structured data for tables/charts
    asset_id INTEGER REFERENCES scm_terran_society.media_asset(asset_id) ON DELETE SET NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_content_block_type ON scm_terran_society.content_block(block_type);
CREATE INDEX idx_content_block_asset ON scm_terran_society.content_block(asset_id);

CREATE TRIGGER content_block_modified 
    BEFORE UPDATE ON scm_terran_society.content_block 
    FOR EACH ROW EXECUTE FUNCTION scm_terran_society.update_modified_column();

-- Entity-Content relationships (links content to tiers, branches, institutions, roles, duties, processes)
CREATE TABLE scm_terran_society.entity_content (
    entity_content_id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('tier', 'branch', 'institution', 'role', 'duty', 'process')),
    entity_id INTEGER NOT NULL,
    block_id INTEGER NOT NULL REFERENCES scm_terran_society.content_block(block_id) ON DELETE CASCADE,
    section_name TEXT, -- Optional section grouping (e.g., "Overview", "Details", "Examples")
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, entity_id, block_id)
);

CREATE INDEX idx_entity_content_lookup ON scm_terran_society.entity_content(entity_type, entity_id);
CREATE INDEX idx_entity_content_block ON scm_terran_society.entity_content(block_id);
CREATE INDEX idx_entity_content_sort ON scm_terran_society.entity_content(entity_type, entity_id, sort_order);

-- Add comments
COMMENT ON TABLE scm_terran_society.media_asset IS 'Stores uploaded media files (images, icons, documents)';
COMMENT ON TABLE scm_terran_society.content_block IS 'Stores content blocks of various types (text, tables, charts, images)';
COMMENT ON TABLE scm_terran_society.entity_content IS 'Links content blocks to entities (tiers, branches, institutions, roles, duties, processes)';

COMMENT ON COLUMN scm_terran_society.content_block.content_text IS 'Markdown-formatted text content';
COMMENT ON COLUMN scm_terran_society.content_block.content_data IS 'JSON data for structured content like tables and charts';
COMMENT ON COLUMN scm_terran_society.entity_content.section_name IS 'Optional section grouping for organizing content';
