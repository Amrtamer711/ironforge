-- =============================================================================
-- RESET SALES BOT SUPABASE
-- =============================================================================
-- Run this FIRST to drop all existing tables, then run salesbot_schema.sql
-- =============================================================================

-- Drop functions first (CASCADE will handle dependent triggers)
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;

-- Drop all tables (CASCADE handles dependencies)
DROP TABLE IF EXISTS ai_costs CASCADE;
DROP TABLE IF EXISTS bo_approval_workflows CASCADE;
DROP TABLE IF EXISTS booking_orders CASCADE;
DROP TABLE IF EXISTS mockup_usage CASCADE;
DROP TABLE IF EXISTS mockup_frames CASCADE;
DROP TABLE IF EXISTS proposals_log CASCADE;

-- Also drop any old auth/RBAC tables that shouldn't be here
-- (These belong in UI Supabase, not SalesBot)
DROP TABLE IF EXISTS api_key_usage CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS invite_tokens CASCADE;
DROP TABLE IF EXISTS user_modules CASCADE;
DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS permissions CASCADE;

-- Legacy RBAC tables (role-based, now replaced by profile-based)
DROP TABLE IF EXISTS role_permissions CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS roles CASCADE;

-- New profile-based RBAC tables (belong in UI Supabase, not SalesBot)
DROP TABLE IF EXISTS record_shares CASCADE;
DROP TABLE IF EXISTS sharing_rules CASCADE;
DROP TABLE IF EXISTS team_members CASCADE;
DROP TABLE IF EXISTS teams CASCADE;
DROP TABLE IF EXISTS user_permission_sets CASCADE;
DROP TABLE IF EXISTS permission_set_permissions CASCADE;
DROP TABLE IF EXISTS permission_sets CASCADE;
DROP TABLE IF EXISTS profile_permissions CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;

-- Core user tables
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS user_profiles CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;

-- =============================================================================
-- Done! Now run salesbot_schema.sql
-- =============================================================================
