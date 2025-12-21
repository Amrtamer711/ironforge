-- =============================================================================
-- MMG TEST DATA: Profiles & Permissions
-- =============================================================================
-- Run this FIRST to set up base profiles
-- =============================================================================

-- Ensure profiles exist
INSERT INTO profiles (name, display_name, description, is_system) VALUES
    ('system_admin', 'System Administrator', 'Full system access to everything', true),
    ('sales_manager', 'Sales Manager', 'Sales team manager with team oversight', true),
    ('sales_rep', 'Sales Representative', 'Standard sales team member', true),
    ('coordinator', 'Sales Coordinator', 'Booking order processing and coordination', true),
    ('finance', 'Finance', 'Financial review and approval', true),
    ('viewer', 'View Only', 'Read-only access for reporting', true)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description;

-- System Admin: Full access
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY['*:*:*']) AS perm
WHERE p.name = 'system_admin'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Sales Manager permissions
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY[
    'sales:*:*',
    'assets:locations:read',
    'assets:networks:read',
    'assets:packages:read',
    'core:teams:read',
    'core:users:read'
]) AS perm
WHERE p.name = 'sales_manager'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Sales Rep permissions
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY[
    'sales:proposals:read',
    'sales:proposals:create',
    'sales:proposals:update',
    'sales:proposals:delete',
    'sales:mockups:read',
    'sales:mockups:generate',
    'sales:booking_orders:read',
    'sales:booking_orders:create',
    'sales:chat:use',
    'assets:locations:read',
    'assets:networks:read',
    'assets:packages:read'
]) AS perm
WHERE p.name = 'sales_rep'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Coordinator permissions
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY[
    'sales:booking_orders:read',
    'sales:booking_orders:create',
    'sales:booking_orders:update',
    'sales:proposals:read',
    'assets:locations:read'
]) AS perm
WHERE p.name = 'coordinator'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Finance permissions
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY[
    'sales:booking_orders:read',
    'sales:booking_orders:update',
    'core:ai_costs:read',
    'sales:reports:read',
    'sales:reports:export'
]) AS perm
WHERE p.name = 'finance'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Viewer permissions (read-only)
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY[
    'sales:proposals:read',
    'sales:booking_orders:read',
    'assets:locations:read'
]) AS perm
WHERE p.name = 'viewer'
ON CONFLICT (profile_id, permission) DO NOTHING;

-- Create permission sets
INSERT INTO permission_sets (name, display_name, description, is_active) VALUES
    ('api_access', 'API Access', 'Programmatic API access for integrations', true),
    ('data_export', 'Data Export', 'Export data to CSV/Excel', true),
    ('bulk_operations', 'Bulk Operations', 'Bulk update and delete', true),
    ('rate_card_editor', 'Rate Card Editor', 'Edit rate cards', true)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    is_active = true;

-- Permission set permissions
INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, perm
FROM permission_sets ps, unnest(ARRAY['core:api:access']) AS perm
WHERE ps.name = 'api_access'
ON CONFLICT (permission_set_id, permission) DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, perm
FROM permission_sets ps, unnest(ARRAY['sales:proposals:export', 'sales:reports:export']) AS perm
WHERE ps.name = 'data_export'
ON CONFLICT (permission_set_id, permission) DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, perm
FROM permission_sets ps, unnest(ARRAY['sales:proposals:bulk_update', 'sales:proposals:bulk_delete']) AS perm
WHERE ps.name = 'bulk_operations'
ON CONFLICT (permission_set_id, permission) DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, perm
FROM permission_sets ps, unnest(ARRAY['sales:rate_cards:read', 'sales:rate_cards:update']) AS perm
WHERE ps.name = 'rate_card_editor'
ON CONFLICT (permission_set_id, permission) DO NOTHING;

SELECT 'Profiles and permissions seeded successfully' AS status;
