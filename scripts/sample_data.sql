-- Sample Data for Terran Society Book Manager
-- This file provides example data to help users understand the application structure
-- Replace this with your own organizational data

-- Insert sample tiers (organizational levels)
INSERT INTO scm_terran_society.tier (tier_name, sort_order) VALUES
    ('Local', 1),
    ('Regional', 2),
    ('Global', 3)
ON CONFLICT DO NOTHING;

-- Insert sample branches (organizational divisions)
INSERT INTO scm_terran_society.branch (branch_name, branch_header, branch_desc, sort_order) VALUES
    ('Executive', 'Executive Branch', 'Responsible for day-to-day operations and implementation', 1),
    ('Legislative', 'Legislative Branch', 'Responsible for policy-making and governance', 2),
    ('Judicial', 'Judicial Branch', 'Responsible for dispute resolution and justice', 3)
ON CONFLICT DO NOTHING;

-- Insert sample institutions
INSERT INTO scm_terran_society.institution (institution_name, institution_header, institution_desc, tier_id, branch_id, sort_order)
SELECT 
    'Local Council',
    'Local Governance Council',
    'Primary decision-making body at the local level',
    t.tier_id,
    b.branch_id,
    1
FROM scm_terran_society.tier t, scm_terran_society.branch b
WHERE t.tier_name = 'Local' AND b.branch_name = 'Executive'
ON CONFLICT DO NOTHING;

INSERT INTO scm_terran_society.institution (institution_name, institution_header, institution_desc, tier_id, branch_id, sort_order)
SELECT 
    'Local Assembly',
    'Local Legislative Assembly',
    'Representative body for local policy decisions',
    t.tier_id,
    b.branch_id,
    2
FROM scm_terran_society.tier t, scm_terran_society.branch b
WHERE t.tier_name = 'Local' AND b.branch_name = 'Legislative'
ON CONFLICT DO NOTHING;

-- Insert sample roles
INSERT INTO scm_terran_society.role (role_name, role_desc, institution_id, sort_order)
SELECT 
    'Council Chair',
    'Leads council meetings and coordinates activities',
    i.institution_id,
    1
FROM scm_terran_society.institution i
WHERE i.institution_name = 'Local Council'
ON CONFLICT DO NOTHING;

INSERT INTO scm_terran_society.role (role_name, role_desc, institution_id, sort_order)
SELECT 
    'Council Member',
    'Participates in council decisions and represents community interests',
    i.institution_id,
    2
FROM scm_terran_society.institution i
WHERE i.institution_name = 'Local Council'
ON CONFLICT DO NOTHING;

INSERT INTO scm_terran_society.role (role_name, role_desc, institution_id, sort_order)
SELECT 
    'Assembly Representative',
    'Elected representative who votes on local policies',
    i.institution_id,
    1
FROM scm_terran_society.institution i
WHERE i.institution_name = 'Local Assembly'
ON CONFLICT DO NOTHING;

-- Insert sample duties for Council Chair
INSERT INTO scm_terran_society.role_duty (role_id, duty_header, duty_desc, sort_order)
SELECT 
    r.role_id,
    'Facilitate Meetings',
    'Lead and facilitate all council meetings, ensuring productive dialogue and decision-making',
    1
FROM scm_terran_society.role r
WHERE r.role_name = 'Council Chair'
ON CONFLICT DO NOTHING;

INSERT INTO scm_terran_society.role_duty (role_id, duty_header, duty_desc, sort_order)
SELECT 
    r.role_id,
    'Coordinate Activities',
    'Coordinate between different council members and community stakeholders',
    2
FROM scm_terran_society.role r
WHERE r.role_name = 'Council Chair'
ON CONFLICT DO NOTHING;

-- Insert sample duties for Council Member
INSERT INTO scm_terran_society.role_duty (role_id, duty_header, duty_desc, sort_order)
SELECT 
    r.role_id,
    'Attend Meetings',
    'Regularly attend and participate in all scheduled council meetings',
    1
FROM scm_terran_society.role r
WHERE r.role_name = 'Council Member'
ON CONFLICT DO NOTHING;

INSERT INTO scm_terran_society.role_duty (role_id, duty_header, duty_desc, sort_order)
SELECT 
    r.role_id,
    'Represent Community',
    'Represent and advocate for community interests in council decisions',
    2
FROM scm_terran_society.role r
WHERE r.role_name = 'Council Member'
ON CONFLICT DO NOTHING;

-- Insert sample process
INSERT INTO scm_terran_society.process (process_name, process_header, process_desc, sort_order) VALUES
    ('Decision Making', 'Collaborative Decision Process', 'How the organization makes decisions collaboratively', 1)
ON CONFLICT DO NOTHING;

-- Insert sample book metadata
INSERT INTO scm_terran_society.book_metadata (title, subtitle, edition, copyright_year, copyright_holder) VALUES
    ('Sample Organizational Handbook', 'A Guide to Our Structure', '1.0', EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER, 'Your Organization Name')
ON CONFLICT (metadata_id) DO UPDATE SET
    title = EXCLUDED.title,
    subtitle = EXCLUDED.subtitle,
    modified_at = CURRENT_TIMESTAMP;

-- Insert sample author
INSERT INTO scm_terran_society.book_author (author_name, author_bio, sort_order) VALUES
    ('Sample Author', 'Author biography goes here', 1)
ON CONFLICT DO NOTHING;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Sample data inserted successfully!';
    RAISE NOTICE 'You can now:';
    RAISE NOTICE '  1. Start the application: ./start.sh';
    RAISE NOTICE '  2. View the sample data in the web interface';
    RAISE NOTICE '  3. Replace this sample data with your own organizational structure';
END $$;
