-- =============================================================================
-- MMG TEST DATA: Companies & Teams
-- =============================================================================
-- Run SECOND after profiles
-- =============================================================================

-- Create company hierarchy
-- MMG (root)
INSERT INTO companies (code, name, parent_id, country, currency, is_group, is_active) VALUES
    ('mmg', 'MMG', NULL, NULL, 'AED', true, true)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_active = true;

-- Backlite Group
INSERT INTO companies (code, name, parent_id, country, currency, is_group, is_active) VALUES
    ('backlite', 'Backlite', (SELECT id FROM companies WHERE code = 'mmg'), NULL, 'AED', true, true)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_active = true;

-- Operating companies
INSERT INTO companies (code, name, parent_id, country, currency, is_group, is_active) VALUES
    ('backlite_dubai', 'Backlite Dubai', (SELECT id FROM companies WHERE code = 'backlite'), 'UAE', 'AED', false, true),
    ('backlite_uk', 'Backlite UK', (SELECT id FROM companies WHERE code = 'backlite'), 'UK', 'GBP', false, true),
    ('backlite_abudhabi', 'Backlite Abu Dhabi', (SELECT id FROM companies WHERE code = 'backlite'), 'UAE', 'AED', false, true),
    ('viola', 'Viola', (SELECT id FROM companies WHERE code = 'mmg'), 'UAE', 'AED', false, true)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    currency = EXCLUDED.currency,
    is_active = true;

-- Create teams
INSERT INTO teams (name, display_name, description, is_active) VALUES
    ('backlite_sales_dubai', 'Backlite Sales - Dubai', 'Dubai sales team', true),
    ('backlite_sales_uk', 'Backlite Sales - UK', 'UK sales team', true),
    ('backlite_sales_abudhabi', 'Backlite Sales - Abu Dhabi', 'Abu Dhabi sales team', true),
    ('viola_sales', 'Viola Sales', 'Viola sales team', true),
    ('coordinators', 'Coordinators', 'Sales coordinators (cross-company)', true),
    ('finance_team', 'Finance Team', 'Finance team (cross-company)', true)
ON CONFLICT DO NOTHING;

SELECT 'Companies and teams seeded successfully' AS status;
