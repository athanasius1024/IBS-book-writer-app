-- ============================================================================
-- Terran Society PostgreSQL Database Schema
-- ============================================================================
-- Run as user 'rock'
-- psql -U rock -d terran_society -f scripts/pg_schema.sql
-- ============================================================================

SET search_path TO ts_data, ts_books, ts_app, public;

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Function to update modified timestamp
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ts_data SCHEMA: Core Organizational Data
-- ============================================================================

-- Metadata table
CREATE TABLE ts_data.meta (
    schema_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    PRIMARY KEY (schema_version)
);

INSERT INTO ts_data.meta VALUES ('2.0', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Terran Society PostgreSQL Database');

-- Tiers
CREATE TABLE ts_data.tier (
    tier_id SERIAL PRIMARY KEY,
    tier_name TEXT UNIQUE NOT NULL,
    tier_code TEXT UNIQUE NOT NULL,
    sort_order INTEGER NOT NULL,
    doc_loc TEXT,
    is_example BOOLEAN DEFAULT FALSE,
    example_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tier_name ON ts_data.tier(tier_name);
CREATE INDEX idx_tier_sort ON ts_data.tier(sort_order);

CREATE TRIGGER tier_modified 
    BEFORE UPDATE ON ts_data.tier 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Tier explanations
CREATE TABLE ts_data.tier_explain (
    explain_id SERIAL PRIMARY KEY,
    tier_id INTEGER NOT NULL REFERENCES ts_data.tier(tier_id) ON DELETE CASCADE,
    explain_header TEXT,
    explain_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tier_explain_tier ON ts_data.tier_explain(tier_id);

-- Branches
CREATE TABLE ts_data.branch (
    branch_id SERIAL PRIMARY KEY,
    branch_name TEXT UNIQUE NOT NULL,
    branch_code TEXT UNIQUE NOT NULL,
    branch_header TEXT,
    branch_desc TEXT,
    sort_order INTEGER NOT NULL,
    doc_loc TEXT,
    is_example BOOLEAN DEFAULT FALSE,
    example_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_branch_name ON ts_data.branch(branch_name);
CREATE INDEX idx_branch_sort ON ts_data.branch(sort_order);

CREATE TRIGGER branch_modified 
    BEFORE UPDATE ON ts_data.branch 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Branch explanations
CREATE TABLE ts_data.branch_explain (
    explain_id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL REFERENCES ts_data.branch(branch_id) ON DELETE CASCADE,
    explain_header TEXT,
    explain_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Institutions
CREATE TABLE ts_data.institution (
    institution_id SERIAL PRIMARY KEY,
    institution_name TEXT NOT NULL,
    tier_id INTEGER NOT NULL REFERENCES ts_data.tier(tier_id),
    branch_id INTEGER NOT NULL REFERENCES ts_data.branch(branch_id),
    institution_header TEXT,
    institution_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    is_example BOOLEAN DEFAULT FALSE,
    example_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_name, tier_id, branch_id)
);

CREATE INDEX idx_institution_tier ON ts_data.institution(tier_id);
CREATE INDEX idx_institution_branch ON ts_data.institution(branch_id);
CREATE INDEX idx_institution_name ON ts_data.institution(institution_name);
CREATE INDEX idx_institution_sort ON ts_data.institution(tier_id, branch_id, sort_order);

CREATE TRIGGER institution_modified 
    BEFORE UPDATE ON ts_data.institution 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Institution details
CREATE TABLE ts_data.institution_dtl (
    dtl_id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES ts_data.institution(institution_id) ON DELETE CASCADE,
    dtl_header TEXT,
    dtl_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Institution explanations
CREATE TABLE ts_data.institution_explain (
    explain_id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES ts_data.institution(institution_id) ON DELETE CASCADE,
    explain_header TEXT,
    explain_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Roles
CREATE TABLE ts_data.role (
    role_id SERIAL PRIMARY KEY,
    role_name TEXT NOT NULL,
    institution_id INTEGER NOT NULL REFERENCES ts_data.institution(institution_id) ON DELETE CASCADE,
    role_title TEXT,
    role_desc TEXT,
    term_length_years INTEGER,
    has_term_limit BOOLEAN DEFAULT FALSE,
    term_limit_years INTEGER,
    max_consecutive_terms INTEGER,
    election_method TEXT CHECK(election_method IN ('Direct', 'Appointed', 'Internal', 'Mixed')),
    doc_loc TEXT,
    sort_order INTEGER,
    is_example BOOLEAN DEFAULT FALSE,
    example_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_name, institution_id)
);

CREATE INDEX idx_role_institution ON ts_data.role(institution_id);
CREATE INDEX idx_role_name ON ts_data.role(role_name);
CREATE INDEX idx_role_election ON ts_data.role(election_method);

CREATE TRIGGER role_modified 
    BEFORE UPDATE ON ts_data.role 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Role duties
CREATE TABLE ts_data.role_duty (
    duty_id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES ts_data.role(role_id) ON DELETE CASCADE,
    duty_header TEXT,
    duty_desc TEXT NOT NULL,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_role_duty_role ON ts_data.role_duty(role_id);
CREATE INDEX idx_role_duty_sort ON ts_data.role_duty(role_id, sort_order);

-- Role explanations
CREATE TABLE ts_data.role_explain (
    explain_id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES ts_data.role(role_id) ON DELETE CASCADE,
    explain_header TEXT,
    explain_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Processes
CREATE TABLE ts_data.process (
    process_id SERIAL PRIMARY KEY,
    process_name TEXT UNIQUE NOT NULL,
    process_scope TEXT,
    process_header TEXT,
    process_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    is_example BOOLEAN DEFAULT FALSE,
    example_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_process_name ON ts_data.process(process_name);
CREATE INDEX idx_process_scope ON ts_data.process(process_scope);

CREATE TRIGGER process_modified 
    BEFORE UPDATE ON ts_data.process 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Process details
CREATE TABLE ts_data.process_dtl (
    dtl_id SERIAL PRIMARY KEY,
    process_id INTEGER NOT NULL REFERENCES ts_data.process(process_id) ON DELETE CASCADE,
    dtl_header TEXT,
    dtl_desc TEXT NOT NULL,
    step_number INTEGER,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_process_dtl_process ON ts_data.process_dtl(process_id);

-- Process explanations
CREATE TABLE ts_data.process_explain (
    explain_id SERIAL PRIMARY KEY,
    process_id INTEGER NOT NULL REFERENCES ts_data.process(process_id) ON DELETE CASCADE,
    explain_header TEXT,
    explain_desc TEXT,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Process-Institution relationship
CREATE TABLE ts_data.process_institution (
    proc_inst_id SERIAL PRIMARY KEY,
    process_id INTEGER NOT NULL REFERENCES ts_data.process(process_id) ON DELETE CASCADE,
    institution_id INTEGER NOT NULL REFERENCES ts_data.institution(institution_id) ON DELETE CASCADE,
    relationship_type TEXT CHECK(relationship_type IN ('Primary', 'Secondary', 'Oversight', 'Support')),
    UNIQUE(process_id, institution_id)
);

CREATE INDEX idx_proc_inst_process ON ts_data.process_institution(process_id);
CREATE INDEX idx_proc_inst_institution ON ts_data.process_institution(institution_id);

-- Glossary
CREATE TABLE ts_data.glossary (
    glossary_id SERIAL PRIMARY KEY,
    term TEXT UNIQUE NOT NULL,
    short_def TEXT NOT NULL,
    long_def TEXT,
    category TEXT CHECK(category IN ('Role', 'Institution', 'Branch', 'Tier', 'Process', 'General')),
    related_id INTEGER,
    doc_loc TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_glossary_term ON ts_data.glossary(term);
CREATE INDEX idx_glossary_category ON ts_data.glossary(category);
CREATE INDEX idx_glossary_term_trgm ON ts_data.glossary USING gin(term gin_trgm_ops);

-- ============================================================================
-- ts_books SCHEMA: Book Versioning and Content
-- ============================================================================

-- Book versions
CREATE TABLE ts_books.book_version (
    version_id SERIAL PRIMARY KEY,
    version_number TEXT UNIQUE NOT NULL,
    version_name TEXT,
    status TEXT CHECK(status IN ('draft', 'review', 'approved', 'published', 'archived')) DEFAULT 'draft',
    created_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by TEXT,
    published_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    metadata JSONB
);

CREATE INDEX idx_book_version_status ON ts_books.book_version(status);
CREATE INDEX idx_book_version_created ON ts_books.book_version(created_at);

-- Book chapters
CREATE TABLE ts_books.book_chapter (
    chapter_id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES ts_books.book_version(version_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    chapter_title TEXT NOT NULL,
    chapter_type TEXT CHECK(chapter_type IN ('introduction', 'principles', 'rights', 'district', 'region', 'world', 'processes', 'glossary', 'appendix')),
    sort_order INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(version_id, chapter_number)
);

CREATE INDEX idx_chapter_version ON ts_books.book_chapter(version_id);
CREATE INDEX idx_chapter_type ON ts_books.book_chapter(chapter_type);
CREATE INDEX idx_chapter_sort ON ts_books.book_chapter(version_id, sort_order);

CREATE TRIGGER chapter_modified 
    BEFORE UPDATE ON ts_books.book_chapter 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Book sections
CREATE TABLE ts_books.book_section (
    section_id SERIAL PRIMARY KEY,
    chapter_id INTEGER NOT NULL REFERENCES ts_books.book_chapter(chapter_id) ON DELETE CASCADE,
    section_number TEXT,
    section_title TEXT NOT NULL,
    section_level INTEGER DEFAULT 1,
    content_text TEXT,
    content_markdown TEXT,
    content_html TEXT,
    sort_order INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_section_chapter ON ts_books.book_section(chapter_id);
CREATE INDEX idx_section_sort ON ts_books.book_section(chapter_id, sort_order);
CREATE INDEX idx_section_content_trgm ON ts_books.book_section USING gin(content_text gin_trgm_ops);

CREATE TRIGGER section_modified 
    BEFORE UPDATE ON ts_books.book_section 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Book data references (links sections to database entities)
CREATE TABLE ts_books.book_data_ref (
    ref_id SERIAL PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES ts_books.book_section(section_id) ON DELETE CASCADE,
    ref_type TEXT CHECK(ref_type IN ('tier', 'branch', 'institution', 'role', 'process', 'glossary')),
    ref_id_value INTEGER NOT NULL,
    ref_context TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_data_ref_section ON ts_books.book_data_ref(section_id);
CREATE INDEX idx_data_ref_type ON ts_books.book_data_ref(ref_type, ref_id_value);

-- Generated documents (full exports)
CREATE TABLE ts_books.generated_document (
    doc_id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES ts_books.book_version(version_id) ON DELETE CASCADE,
    format TEXT CHECK(format IN ('markdown', 'html', 'pdf', 'odt', 'docx', 'epub')) NOT NULL,
    file_path TEXT,
    file_size BIGINT,
    checksum TEXT,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    generated_by TEXT,
    metadata JSONB
);

CREATE INDEX idx_gen_doc_version ON ts_books.generated_document(version_id);
CREATE INDEX idx_gen_doc_format ON ts_books.generated_document(format);

-- ============================================================================
-- ts_app SCHEMA: Application Metadata
-- ============================================================================

-- Application settings
CREATE TABLE ts_app.setting (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT,
    setting_type TEXT CHECK(setting_type IN ('string', 'integer', 'boolean', 'json')),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER setting_modified 
    BEFORE UPDATE ON ts_app.setting 
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- User sessions (for web app)
CREATE TABLE ts_app.user_session (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT,
    metadata JSONB
);

CREATE INDEX idx_session_user ON ts_app.user_session(user_name);
CREATE INDEX idx_session_activity ON ts_app.user_session(last_activity);

-- Activity log
CREATE TABLE ts_app.activity_log (
    log_id BIGSERIAL PRIMARY KEY,
    log_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_name TEXT,
    action_type TEXT,
    table_name TEXT,
    record_id INTEGER,
    details JSONB,
    ip_address INET
);

CREATE INDEX idx_activity_timestamp ON ts_app.activity_log(log_timestamp);
CREATE INDEX idx_activity_user ON ts_app.activity_log(user_name);
CREATE INDEX idx_activity_type ON ts_app.activity_log(action_type);
CREATE INDEX idx_activity_table ON ts_app.activity_log(table_name);

-- ============================================================================
-- ts_audit SCHEMA: Audit Trail
-- ============================================================================

-- Audit log for data changes
CREATE TABLE ts_audit.data_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    audit_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    operation TEXT CHECK(operation IN ('INSERT', 'UPDATE', 'DELETE')) NOT NULL,
    user_name TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[]
);

CREATE INDEX idx_audit_timestamp ON ts_audit.data_audit(audit_timestamp);
CREATE INDEX idx_audit_table ON ts_audit.data_audit(schema_name, table_name);
CREATE INDEX idx_audit_user ON ts_audit.data_audit(user_name);
CREATE INDEX idx_audit_operation ON ts_audit.data_audit(operation);

-- ============================================================================
-- VIEWS FOR EASY QUERYING
-- ============================================================================

-- Full role view with hierarchy
CREATE VIEW ts_data.v_role_full AS
SELECT 
    r.role_id,
    r.role_name,
    r.role_title,
    r.role_desc,
    r.term_length_years,
    r.has_term_limit,
    r.term_limit_years,
    r.max_consecutive_terms,
    r.election_method,
    i.institution_name,
    i.institution_id,
    t.tier_name,
    t.tier_id,
    b.branch_name,
    b.branch_id,
    r.doc_loc,
    r.is_example,
    r.created_at,
    r.modified_at
FROM ts_data.role r
JOIN ts_data.institution i ON r.institution_id = i.institution_id
JOIN ts_data.tier t ON i.tier_id = t.tier_id
JOIN ts_data.branch b ON i.branch_id = b.branch_id
ORDER BY t.sort_order, b.sort_order, i.sort_order, r.sort_order;

-- Full institution view
CREATE VIEW ts_data.v_institution_full AS
SELECT 
    i.institution_id,
    i.institution_name,
    i.institution_header,
    i.institution_desc,
    t.tier_name,
    t.tier_id,
    b.branch_name,
    b.branch_id,
    i.doc_loc,
    i.is_example,
    COUNT(DISTINCT r.role_id) as role_count,
    i.created_at,
    i.modified_at
FROM ts_data.institution i
JOIN ts_data.tier t ON i.tier_id = t.tier_id
JOIN ts_data.branch b ON i.branch_id = b.branch_id
LEFT JOIN ts_data.role r ON i.institution_id = r.institution_id
GROUP BY i.institution_id, i.institution_name, i.institution_header, i.institution_desc,
         t.tier_name, t.tier_id, b.branch_name, b.branch_id, i.doc_loc, i.is_example,
         i.created_at, i.modified_at
ORDER BY t.sort_order, b.sort_order, i.sort_order;

-- Process with institutions
CREATE VIEW ts_data.v_process_full AS
SELECT 
    p.process_id,
    p.process_name,
    p.process_scope,
    p.process_header,
    p.process_desc,
    string_agg(DISTINCT i.institution_name, ', ' ORDER BY i.institution_name) as institutions,
    p.doc_loc,
    p.is_example,
    p.created_at,
    p.modified_at
FROM ts_data.process p
LEFT JOIN ts_data.process_institution pi ON p.process_id = pi.process_id
LEFT JOIN ts_data.institution i ON pi.institution_id = i.institution_id
GROUP BY p.process_id, p.process_name, p.process_scope, p.process_header, p.process_desc,
         p.doc_loc, p.is_example, p.created_at, p.modified_at
ORDER BY p.sort_order;

-- Book version with chapter count
CREATE VIEW ts_books.v_book_summary AS
SELECT 
    bv.version_id,
    bv.version_number,
    bv.version_name,
    bv.status,
    bv.created_by,
    bv.created_at,
    bv.approved_at,
    bv.published_at,
    COUNT(DISTINCT bc.chapter_id) as chapter_count,
    COUNT(DISTINCT bs.section_id) as section_count
FROM ts_books.book_version bv
LEFT JOIN ts_books.book_chapter bc ON bv.version_id = bc.version_id
LEFT JOIN ts_books.book_section bs ON bc.chapter_id = bs.chapter_id
GROUP BY bv.version_id, bv.version_number, bv.version_name, bv.status,
         bv.created_by, bv.created_at, bv.approved_at, bv.published_at
ORDER BY bv.created_at DESC;

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================

-- Grant SELECT on all tables to overlook
GRANT SELECT ON ALL TABLES IN SCHEMA ts_data TO overlook;
GRANT SELECT ON ALL TABLES IN SCHEMA ts_books TO overlook;
GRANT SELECT ON ALL TABLES IN SCHEMA ts_app TO overlook;
GRANT SELECT ON ALL TABLES IN SCHEMA ts_audit TO overlook;

-- Grant usage on sequences to overlook
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ts_data TO overlook;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ts_books TO overlook;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ts_app TO overlook;

-- Grant ALL to rock
GRANT ALL ON ALL TABLES IN SCHEMA ts_data TO rock;
GRANT ALL ON ALL TABLES IN SCHEMA ts_books TO rock;
GRANT ALL ON ALL TABLES IN SCHEMA ts_app TO rock;
GRANT ALL ON ALL TABLES IN SCHEMA ts_audit TO rock;

GRANT ALL ON ALL SEQUENCES IN SCHEMA ts_data TO rock;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ts_books TO rock;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ts_app TO rock;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ts_audit TO rock;

-- Set ownership
ALTER TABLE ts_data.meta OWNER TO rock;
ALTER TABLE ts_data.tier OWNER TO rock;
ALTER TABLE ts_data.tier_explain OWNER TO rock;
ALTER TABLE ts_data.branch OWNER TO rock;
ALTER TABLE ts_data.branch_explain OWNER TO rock;
ALTER TABLE ts_data.institution OWNER TO rock;
ALTER TABLE ts_data.institution_dtl OWNER TO rock;
ALTER TABLE ts_data.institution_explain OWNER TO rock;
ALTER TABLE ts_data.role OWNER TO rock;
ALTER TABLE ts_data.role_duty OWNER TO rock;
ALTER TABLE ts_data.role_explain OWNER TO rock;
ALTER TABLE ts_data.process OWNER TO rock;
ALTER TABLE ts_data.process_dtl OWNER TO rock;
ALTER TABLE ts_data.process_explain OWNER TO rock;
ALTER TABLE ts_data.process_institution OWNER TO rock;
ALTER TABLE ts_data.glossary OWNER TO rock;

ALTER TABLE ts_books.book_version OWNER TO rock;
ALTER TABLE ts_books.book_chapter OWNER TO rock;
ALTER TABLE ts_books.book_section OWNER TO rock;
ALTER TABLE ts_books.book_data_ref OWNER TO rock;
ALTER TABLE ts_books.generated_document OWNER TO rock;

ALTER TABLE ts_app.setting OWNER TO rock;
ALTER TABLE ts_app.user_session OWNER TO rock;
ALTER TABLE ts_app.activity_log OWNER TO rock;

ALTER TABLE ts_audit.data_audit OWNER TO rock;

\echo ''
\echo '============================================================================'
\echo 'PostgreSQL Schema Created Successfully!'
\echo '============================================================================'
\echo 'Schemas populated:'
\echo '  - ts_data   : 16 tables + 3 views (organizational data)'
\echo '  - ts_books  : 5 tables + 1 view (book versioning)'
\echo '  - ts_app    : 3 tables (application metadata)'
\echo '  - ts_audit  : 1 table (audit trail)'
\echo ''
\echo 'Next step: Run migration script to import SQLite data'
\echo '  python scripts/migrate_to_postgres.py'
\echo '============================================================================'
\echo ''
