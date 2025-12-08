-- =============================================================================
-- DEVELOPMENT SEED DATA
-- =============================================================================
-- Run this in Sales-Module-Dev Supabase project AFTER running salesbot_schema.sql
-- This creates test data so you can immediately start testing the platform
-- =============================================================================

-- =============================================================================
-- 1. CREATE TEST USERS (these match users you'll create in UI Supabase Auth)
-- =============================================================================
-- NOTE: The 'id' must match the UUID from Supabase Auth when you sign up
-- For now, we'll use placeholder UUIDs - update these after creating real users

-- =============================================================================
-- IMPORTANT: After creating a user in UI-Module-Dev Supabase Auth,
-- copy their UUID and run this UPDATE to link them:
--
-- UPDATE users SET id = 'YOUR-UUID-FROM-SUPABASE-AUTH' WHERE email = 'a.tamer@mmg.global';
-- UPDATE user_roles SET user_id = 'YOUR-UUID-FROM-SUPABASE-AUTH' WHERE user_id LIKE 'admin-placeholder%';
-- =============================================================================

-- Admin User (Amr Tamer)
INSERT INTO users (id, email, name, is_active, created_at, updated_at)
VALUES (
    'admin-placeholder-0001-0001-000000000001',
    'a.tamer@mmg.global',
    'Amr Tamer',
    1,
    NOW()::TEXT,
    NOW()::TEXT
) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name;

-- Test Regular User
INSERT INTO users (id, email, name, is_active, created_at, updated_at)
VALUES (
    'user-placeholder-0002-0002-000000000002',
    'testuser@mmg.global',
    'Test User',
    1,
    NOW()::TEXT,
    NOW()::TEXT
) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name;

-- =============================================================================
-- 2. ASSIGN ROLES TO TEST USERS
-- =============================================================================

-- Make a.tamer@mmg.global an admin
INSERT INTO user_roles (user_id, role_id, granted_by, granted_at)
SELECT
    'admin-placeholder-0001-0001-000000000001',
    r.id,
    'system',
    NOW()::TEXT
FROM roles r WHERE r.name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Make testuser@mmg.global a regular user
INSERT INTO user_roles (user_id, role_id, granted_by, granted_at)
SELECT
    'user-placeholder-0002-0002-000000000002',
    r.id,
    'system',
    NOW()::TEXT
FROM roles r WHERE r.name = 'user'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- =============================================================================
-- 3. CREATE SAMPLE PERMISSIONS
-- =============================================================================

INSERT INTO permissions (name, description, resource, action, created_at) VALUES
    ('proposals:create', 'Create proposals', 'proposals', 'create', NOW()::TEXT),
    ('proposals:read', 'View proposals', 'proposals', 'read', NOW()::TEXT),
    ('proposals:update', 'Update proposals', 'proposals', 'update', NOW()::TEXT),
    ('proposals:delete', 'Delete proposals', 'proposals', 'delete', NOW()::TEXT),
    ('mockups:create', 'Create mockups', 'mockups', 'create', NOW()::TEXT),
    ('mockups:read', 'View mockups', 'mockups', 'read', NOW()::TEXT),
    ('bookings:create', 'Create booking orders', 'bookings', 'create', NOW()::TEXT),
    ('bookings:read', 'View booking orders', 'bookings', 'read', NOW()::TEXT),
    ('bookings:approve', 'Approve booking orders', 'bookings', 'approve', NOW()::TEXT),
    ('admin:users', 'Manage users', 'admin', 'users', NOW()::TEXT),
    ('admin:settings', 'Manage settings', 'admin', 'settings', NOW()::TEXT)
ON CONFLICT (resource, action) DO NOTHING;

-- =============================================================================
-- 4. ASSIGN PERMISSIONS TO ROLES
-- =============================================================================

-- Admin gets all permissions
INSERT INTO role_permissions (role_id, permission_id, granted_at)
SELECT r.id, p.id, NOW()::TEXT
FROM roles r, permissions p
WHERE r.name = 'admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- User role gets basic permissions
INSERT INTO role_permissions (role_id, permission_id, granted_at)
SELECT r.id, p.id, NOW()::TEXT
FROM roles r, permissions p
WHERE r.name = 'user'
  AND p.name IN ('proposals:create', 'proposals:read', 'mockups:create', 'mockups:read', 'bookings:create', 'bookings:read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Viewer role gets read-only permissions
INSERT INTO role_permissions (role_id, permission_id, granted_at)
SELECT r.id, p.id, NOW()::TEXT
FROM roles r, permissions p
WHERE r.name = 'viewer'
  AND p.name IN ('proposals:read', 'mockups:read', 'bookings:read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- =============================================================================
-- 5. SAMPLE PROPOSAL LOG ENTRY
-- =============================================================================

INSERT INTO proposals_log (user_id, submitted_by, client_name, date_generated, package_type, locations, total_amount)
VALUES (
    'admin-placeholder-0001-0001-000000000001',
    'Amr Tamer',
    'Sample Client Corp',
    NOW()::TEXT,
    'Premium',
    'Dubai Mall, Mall of Emirates',
    '150000'
);

-- =============================================================================
-- 6. SAMPLE MOCKUP FRAME CONFIG
-- =============================================================================

INSERT INTO mockup_frames (user_id, location_key, time_of_day, finish, photo_filename, frames_data, created_at, created_by)
VALUES (
    'admin-placeholder-0001-0001-000000000001',
    'dubai_mall_entrance',
    'day',
    'gold',
    'sample_photo.jpg',
    '[{"x": 100, "y": 200, "width": 300, "height": 400}]',
    NOW()::TEXT,
    'Amr Tamer'
) ON CONFLICT (location_key, time_of_day, finish, photo_filename) DO NOTHING;

-- =============================================================================
-- DONE! Your dev database now has:
-- - 2 test users (admin@test.com, user@test.com)
-- - Role assignments (admin has admin role, user has user role)
-- - All permissions defined
-- - Role-permission mappings
-- - Sample proposal and mockup data
-- =============================================================================

SELECT 'Seed data inserted successfully!' as status;
