-- ============================================================================
-- Terran Society PostgreSQL Database Setup
-- ============================================================================
-- This script creates the database, users, and access controls
-- Run as PostgreSQL superuser (postgres)
-- ============================================================================

-- Drop existing database if it exists (be careful with this in production!)
DROP DATABASE IF EXISTS terran_society;

-- Create the database
CREATE DATABASE terran_society
    WITH 
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Connect to the new database
\c terran_society

-- ============================================================================
-- CREATE USERS AND ROLES
-- ============================================================================

-- Drop existing users if they exist
DROP USER IF EXISTS dba;
DROP USER IF EXISTS rock;
DROP USER IF EXISTS overlook;

-- Create root DBA user
CREATE USER dba WITH
    SUPERUSER
    CREATEDB
    CREATEROLE
    LOGIN
    PASSWORD 'sql';

COMMENT ON ROLE dba IS 'Root database administrator with full privileges';

-- Create administrator user 'rock'
CREATE USER rock WITH
    LOGIN
    PASSWORD 'river'
    CREATEDB
    CREATEROLE;

COMMENT ON ROLE rock IS 'Database administrator with full privileges on Terran Society database';

-- Create read-only user 'overlook'
CREATE USER overlook WITH
    LOGIN
    PASSWORD 'river';

COMMENT ON ROLE overlook IS 'Read-only user for querying Terran Society data';

-- Grant connection privileges
GRANT CONNECT ON DATABASE terran_society TO rock;
GRANT CONNECT ON DATABASE terran_society TO overlook;

-- ============================================================================
-- CREATE SCHEMAS FOR ORGANIZATION
-- ============================================================================

-- Main data schema
CREATE SCHEMA IF NOT EXISTS ts_data;
COMMENT ON SCHEMA ts_data IS 'Core Terran Society organizational data';

-- Book versioning schema
CREATE SCHEMA IF NOT EXISTS ts_books;
COMMENT ON SCHEMA ts_books IS 'Book versions, chapters, and generated content';

-- Application schema
CREATE SCHEMA IF NOT EXISTS ts_app;
COMMENT ON SCHEMA ts_app IS 'Application metadata, logs, and settings';

-- Audit schema
CREATE SCHEMA IF NOT EXISTS ts_audit;
COMMENT ON SCHEMA ts_audit IS 'Audit trail for all data changes';

-- Set ownership of schemas to 'rock'
ALTER SCHEMA ts_data OWNER TO rock;
ALTER SCHEMA ts_books OWNER TO rock;
ALTER SCHEMA ts_app OWNER TO rock;
ALTER SCHEMA ts_audit OWNER TO rock;

-- Set default search path
ALTER DATABASE terran_society SET search_path TO ts_data, ts_books, ts_app, public;

-- Grant usage on schemas
GRANT USAGE ON SCHEMA ts_data TO rock, overlook;
GRANT USAGE ON SCHEMA ts_books TO rock, overlook;
GRANT USAGE ON SCHEMA ts_app TO rock, overlook;
GRANT USAGE ON SCHEMA ts_audit TO rock, overlook;

-- Grant all privileges to rock
GRANT ALL ON SCHEMA ts_data TO rock;
GRANT ALL ON SCHEMA ts_books TO rock;
GRANT ALL ON SCHEMA ts_app TO rock;
GRANT ALL ON SCHEMA ts_audit TO rock;

-- ============================================================================
-- ENABLE EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
COMMENT ON EXTENSION "uuid-ossp" IS 'Generate UUIDs';

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
COMMENT ON EXTENSION "pgcrypto" IS 'Cryptographic functions';

CREATE EXTENSION IF NOT EXISTS "btree_gin";
COMMENT ON EXTENSION "btree_gin" IS 'GIN operator classes for faster text search';

CREATE EXTENSION IF NOT EXISTS "pg_trgm";
COMMENT ON EXTENSION "pg_trgm" IS 'Trigram matching for text search';

-- ============================================================================
-- GRANT DEFAULT PRIVILEGES
-- ============================================================================

-- For future tables created by rock in ts_data
ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_data
    GRANT SELECT ON TABLES TO overlook;

ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_data
    GRANT ALL ON TABLES TO rock;

ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_data
    GRANT USAGE, SELECT ON SEQUENCES TO rock, overlook;

-- For future tables in ts_books
ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_books
    GRANT SELECT ON TABLES TO overlook;

ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_books
    GRANT ALL ON TABLES TO rock;

-- For future tables in ts_app
ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_app
    GRANT SELECT ON TABLES TO overlook;

ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_app
    GRANT ALL ON TABLES TO rock;

-- For audit (read-only for everyone)
ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_audit
    GRANT SELECT ON TABLES TO overlook;

ALTER DEFAULT PRIVILEGES FOR ROLE rock IN SCHEMA ts_audit
    GRANT ALL ON TABLES TO rock;

-- ============================================================================
-- SETUP COMPLETE
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'PostgreSQL Setup Complete!'
\echo '============================================================================'
\echo 'Database: terran_society'
\echo ''
\echo 'Users created:'
\echo '  - dba       (password: sql)   - Superuser'
\echo '  - rock      (password: river) - Administrator (owner of all objects)'
\echo '  - overlook  (password: river) - Read-only access'
\echo ''
\echo 'Schemas created:'
\echo '  - ts_data   - Core organizational data'
\echo '  - ts_books  - Book versioning and content'
\echo '  - ts_app    - Application metadata'
\echo '  - ts_audit  - Audit trails'
\echo ''
\echo 'Next steps:'
\echo '  1. Run: psql -U rock -d terran_society -f scripts/pg_schema.sql'
\echo '  2. Run: python scripts/migrate_to_postgres.py'
\echo '============================================================================'
\echo ''
