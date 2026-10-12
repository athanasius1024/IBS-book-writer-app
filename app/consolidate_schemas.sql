-- Consolidate all schemas into scm_terran_society
-- This moves tables from ts_data, ts_books, ts_app, ts_audit

-- Move ts_app tables
ALTER TABLE ts_app.activity_log SET SCHEMA scm_terran_society;
ALTER TABLE ts_app.setting SET SCHEMA scm_terran_society;

-- Move ts_audit tables
ALTER TABLE ts_audit.data_audit SET SCHEMA scm_terran_society;

-- Move ts_books tables
ALTER TABLE ts_books.book_chapter SET SCHEMA scm_terran_society;
ALTER TABLE ts_books.book_data_ref SET SCHEMA scm_terran_society;
ALTER TABLE ts_books.book_section SET SCHEMA scm_terran_society;
ALTER TABLE ts_books.book_version SET SCHEMA scm_terran_society;
ALTER TABLE ts_books.generated_document SET SCHEMA scm_terran_society;

-- Move ts_data tables (in dependency order to avoid FK issues)
ALTER TABLE ts_data.meta SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.glossary SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.tier SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.tier_explain SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.branch SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.branch_explain SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.institution SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.institution_dtl SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.institution_explain SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.role SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.role_duty SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.role_explain SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.process SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.process_dtl SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.process_explain SET SCHEMA scm_terran_society;
ALTER TABLE ts_data.process_institution SET SCHEMA scm_terran_society;
