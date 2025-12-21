-- =============================================================================
-- MMG TEST DATA: Test Users (Personas)
-- =============================================================================
-- Run THIRD after companies and teams
--
-- IMPORTANT: These users need to exist in Supabase Auth first!
-- Use the CLI tool or Supabase dashboard to create auth users,
-- then run this script to set up their RBAC data.
--
-- Default password for all test users: TestUser123!
-- =============================================================================

-- Helper function to get profile ID by name
CREATE OR REPLACE FUNCTION get_profile_id(p_name TEXT) RETURNS BIGINT AS $$
    SELECT id FROM profiles WHERE name = p_name;
$$ LANGUAGE SQL;

-- Helper function to get company ID by code
CREATE OR REPLACE FUNCTION get_company_id(p_code TEXT) RETURNS BIGINT AS $$
    SELECT id FROM companies WHERE code = p_code;
$$ LANGUAGE SQL;

-- Helper function to get team ID by name
CREATE OR REPLACE FUNCTION get_team_id(t_name TEXT) RETURNS BIGINT AS $$
    SELECT id FROM teams WHERE name = t_name;
$$ LANGUAGE SQL;

-- =============================================================================
-- TEST USER IDs (UUIDs - must match auth.users)
-- =============================================================================
-- Generate these by creating users in Supabase Auth first, then update here
-- Or use the CLI tool which handles both

DO $$
DECLARE
    -- Admin users
    v_admin_id TEXT := 'test-admin-00000000-0000-0000-0000-000000000001';

    -- Managers (HoS)
    v_hos_backlite_id TEXT := 'test-hos-backlite-0000-0000-0000-000000000002';
    v_hos_viola_id TEXT := 'test-hos-viola-0000-0000-0000-000000000003';

    -- Sales Reps
    v_rep_dubai_1_id TEXT := 'test-rep-dubai1-0000-0000-0000-000000000004';
    v_rep_dubai_2_id TEXT := 'test-rep-dubai2-0000-0000-0000-000000000005';
    v_rep_uk_1_id TEXT := 'test-rep-uk1-0000-0000-0000-000000000006';
    v_rep_abudhabi_1_id TEXT := 'test-rep-abudhabi-0000-0000-0000-000000000007';
    v_rep_viola_1_id TEXT := 'test-rep-viola1-0000-0000-0000-000000000008';
    v_rep_multi_id TEXT := 'test-rep-multi-0000-0000-0000-000000000009';

    -- Coordinators & Finance
    v_coordinator_1_id TEXT := 'test-coordinator1-0000-0000-0000-000000000010';
    v_finance_1_id TEXT := 'test-finance1-0000-0000-0000-000000000011';

    -- Edge cases
    v_viewer_id TEXT := 'test-viewer-0000-0000-0000-000000000012';
    v_no_perms_id TEXT := 'test-noperms-0000-0000-0000-000000000013';
    v_no_company_id TEXT := 'test-nocompany-0000-0000-0000-000000000014';
    v_wrong_company_id TEXT := 'test-wrongcompany-0000-0000-0000-000000000015';

BEGIN
    -- =========================================================================
    -- INSERT USERS
    -- =========================================================================

    -- Admin
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_admin_id, 'test.admin@mmg.ae', 'Test Admin', true,
         get_profile_id('system_admin'), get_company_id('backlite_dubai'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- HoS Backlite
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_hos_backlite_id, 'hos.backlite@mmg.ae', 'Ahmed Test (HoS Backlite)', true,
         get_profile_id('sales_manager'), get_company_id('backlite_dubai'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- HoS Viola
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_hos_viola_id, 'hos.viola@mmg.ae', 'Manel Test (HoS Viola)', true,
         get_profile_id('sales_manager'), get_company_id('viola'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- Sales Reps
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id, manager_id) VALUES
        (v_rep_dubai_1_id, 'rep.dubai1@mmg.ae', 'Sales Rep Dubai 1', true,
         get_profile_id('sales_rep'), get_company_id('backlite_dubai'), v_hos_backlite_id),
        (v_rep_dubai_2_id, 'rep.dubai2@mmg.ae', 'Sales Rep Dubai 2', true,
         get_profile_id('sales_rep'), get_company_id('backlite_dubai'), v_hos_backlite_id),
        (v_rep_uk_1_id, 'rep.uk1@mmg.ae', 'Sales Rep UK', true,
         get_profile_id('sales_rep'), get_company_id('backlite_uk'), v_hos_backlite_id),
        (v_rep_abudhabi_1_id, 'rep.abudhabi1@mmg.ae', 'Sales Rep Abu Dhabi', true,
         get_profile_id('sales_rep'), get_company_id('backlite_abudhabi'), v_hos_backlite_id),
        (v_rep_viola_1_id, 'rep.viola1@mmg.ae', 'Sales Rep Viola', true,
         get_profile_id('sales_rep'), get_company_id('viola'), v_hos_viola_id),
        (v_rep_multi_id, 'rep.multi@mmg.ae', 'Multi-Company Rep', true,
         get_profile_id('sales_rep'), get_company_id('backlite_dubai'), NULL)
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id,
        manager_id = EXCLUDED.manager_id;

    -- Coordinator
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_coordinator_1_id, 'coordinator1@mmg.ae', 'Richelle Test (Coordinator)', true,
         get_profile_id('coordinator'), get_company_id('backlite_dubai'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- Finance
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_finance_1_id, 'finance1@mmg.ae', 'Finance User 1', true,
         get_profile_id('finance'), get_company_id('backlite_dubai'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- Edge case users
    INSERT INTO users (id, email, name, is_active, profile_id, primary_company_id) VALUES
        (v_viewer_id, 'viewer@mmg.ae', 'View Only User', true,
         get_profile_id('viewer'), get_company_id('backlite_dubai')),
        (v_no_perms_id, 'noperms@mmg.ae', 'No Permissions', true,
         NULL, get_company_id('backlite_dubai')),  -- No profile!
        (v_no_company_id, 'nocompany@mmg.ae', 'No Company Access', true,
         get_profile_id('sales_rep'), NULL),  -- No company!
        (v_wrong_company_id, 'wrongcompany@mmg.ae', 'Wrong Company User', true,
         get_profile_id('sales_rep'), get_company_id('viola'))
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        is_active = true,
        profile_id = EXCLUDED.profile_id;

    -- =========================================================================
    -- COMPANY ASSIGNMENTS
    -- =========================================================================

    -- Admin: All companies
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_admin_id, get_company_id('backlite_dubai'), true),
        (v_admin_id, get_company_id('backlite_uk'), false),
        (v_admin_id, get_company_id('backlite_abudhabi'), false),
        (v_admin_id, get_company_id('viola'), false)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- HoS Backlite: All Backlite companies
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_hos_backlite_id, get_company_id('backlite_dubai'), true),
        (v_hos_backlite_id, get_company_id('backlite_uk'), false),
        (v_hos_backlite_id, get_company_id('backlite_abudhabi'), false)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- HoS Viola: Only Viola
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_hos_viola_id, get_company_id('viola'), true)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Reps: Single companies
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_rep_dubai_1_id, get_company_id('backlite_dubai'), true),
        (v_rep_dubai_2_id, get_company_id('backlite_dubai'), true),
        (v_rep_uk_1_id, get_company_id('backlite_uk'), true),
        (v_rep_abudhabi_1_id, get_company_id('backlite_abudhabi'), true),
        (v_rep_viola_1_id, get_company_id('viola'), true)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Multi-company rep
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_rep_multi_id, get_company_id('backlite_dubai'), true),
        (v_rep_multi_id, get_company_id('viola'), false)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Coordinator: All companies
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_coordinator_1_id, get_company_id('backlite_dubai'), true),
        (v_coordinator_1_id, get_company_id('backlite_uk'), false),
        (v_coordinator_1_id, get_company_id('backlite_abudhabi'), false),
        (v_coordinator_1_id, get_company_id('viola'), false)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Finance: All companies
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_finance_1_id, get_company_id('backlite_dubai'), true),
        (v_finance_1_id, get_company_id('backlite_uk'), false),
        (v_finance_1_id, get_company_id('backlite_abudhabi'), false),
        (v_finance_1_id, get_company_id('viola'), false)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Viewer: Single company
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_viewer_id, get_company_id('backlite_dubai'), true)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- No perms user: Has company but no profile
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_no_perms_id, get_company_id('backlite_dubai'), true)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- Wrong company user: Only Viola (will try to access Dubai)
    INSERT INTO user_companies (user_id, company_id, is_primary) VALUES
        (v_wrong_company_id, get_company_id('viola'), true)
    ON CONFLICT (user_id, company_id) DO NOTHING;

    -- No company user: No company assignments (already has none)

    -- =========================================================================
    -- TEAM MEMBERSHIPS
    -- =========================================================================

    -- HoS Backlite: Leader of all Backlite teams
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('backlite_sales_dubai'), v_hos_backlite_id, 'leader'),
        (get_team_id('backlite_sales_uk'), v_hos_backlite_id, 'leader'),
        (get_team_id('backlite_sales_abudhabi'), v_hos_backlite_id, 'leader')
    ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role;

    -- HoS Viola: Leader of Viola team
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('viola_sales'), v_hos_viola_id, 'leader')
    ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role;

    -- Reps: Team members
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('backlite_sales_dubai'), v_rep_dubai_1_id, 'member'),
        (get_team_id('backlite_sales_dubai'), v_rep_dubai_2_id, 'member'),
        (get_team_id('backlite_sales_uk'), v_rep_uk_1_id, 'member'),
        (get_team_id('backlite_sales_abudhabi'), v_rep_abudhabi_1_id, 'member'),
        (get_team_id('viola_sales'), v_rep_viola_1_id, 'member')
    ON CONFLICT (team_id, user_id) DO NOTHING;

    -- Multi-company rep: Member of multiple teams
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('backlite_sales_dubai'), v_rep_multi_id, 'member'),
        (get_team_id('viola_sales'), v_rep_multi_id, 'member')
    ON CONFLICT (team_id, user_id) DO NOTHING;

    -- Coordinator: Coordinators team
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('coordinators'), v_coordinator_1_id, 'member')
    ON CONFLICT (team_id, user_id) DO NOTHING;

    -- Finance: Finance team
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('finance_team'), v_finance_1_id, 'member')
    ON CONFLICT (team_id, user_id) DO NOTHING;

    -- Viewer: Team member
    INSERT INTO team_members (team_id, user_id, role) VALUES
        (get_team_id('backlite_sales_dubai'), v_viewer_id, 'member')
    ON CONFLICT (team_id, user_id) DO NOTHING;

    -- =========================================================================
    -- PERMISSION SET ASSIGNMENTS
    -- =========================================================================

    -- Give HoS rate card editor permission
    INSERT INTO user_permission_sets (user_id, permission_set_id, granted_by) VALUES
        (v_hos_backlite_id, (SELECT id FROM permission_sets WHERE name = 'rate_card_editor'), v_admin_id),
        (v_hos_viola_id, (SELECT id FROM permission_sets WHERE name = 'rate_card_editor'), v_admin_id)
    ON CONFLICT (user_id, permission_set_id) DO NOTHING;

    -- Give rep_dubai_2 extra permissions (bulk ops + export)
    INSERT INTO user_permission_sets (user_id, permission_set_id, granted_by) VALUES
        (v_rep_dubai_2_id, (SELECT id FROM permission_sets WHERE name = 'bulk_operations'), v_admin_id),
        (v_rep_dubai_2_id, (SELECT id FROM permission_sets WHERE name = 'data_export'), v_admin_id)
    ON CONFLICT (user_id, permission_set_id) DO NOTHING;

    RAISE NOTICE 'Test users seeded successfully!';
END $$;

-- Cleanup helper functions
DROP FUNCTION IF EXISTS get_profile_id(TEXT);
DROP FUNCTION IF EXISTS get_company_id(TEXT);
DROP FUNCTION IF EXISTS get_team_id(TEXT);

SELECT 'Test users seeded successfully' AS status;
