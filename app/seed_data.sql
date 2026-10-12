-- Seed data for testing the Terran Society web app

-- Insert Tiers
INSERT INTO ts_data.tier (tier_name, tier_code, sort_order) VALUES
('District', 'DST', 1),
('Region', 'RGN', 2),
('World', 'WLD', 3);

-- Insert Branches
INSERT INTO ts_data.branch (branch_name, branch_code, branch_header, sort_order) VALUES
('Executive', 'EXEC', 'Executive Branch', 1),
('Legislative', 'LEG', 'Legislative Branch', 2),
('Judicial', 'JUD', 'Judicial Branch', 3),
('Fair Witness', 'FW', 'Fair Witness Branch', 4),
('Military', 'MIL', 'Military Branch', 5);

-- Insert a few sample institutions
INSERT INTO ts_data.institution (institution_name, tier_id, branch_id, institution_desc, sort_order) VALUES
('District Council', 1, 2, 'Primary legislative body at the district level', 1),
('District Court', 1, 3, 'Judicial body handling district-level cases', 2),
('Regional Assembly', 2, 2, 'Legislative assembly for regional governance', 1);

-- Insert a sample role
INSERT INTO ts_data.role (role_name, institution_id, role_desc, sort_order) VALUES
('Council Member', 1, 'Elected member of the District Council', 1),
('District Judge', 2, 'Presiding judge in district court', 1);

-- Insert sample duties
INSERT INTO ts_data.role_duty (role_id, duty_header, duty_desc, sort_order) VALUES
(1, 'Legislative Duties', 'Participate in legislative sessions and vote on proposals', 1),
(1, 'Constituent Service', 'Represent and serve district constituents', 2),
(2, 'Judicial Review', 'Hear and rule on cases within district jurisdiction', 1);
