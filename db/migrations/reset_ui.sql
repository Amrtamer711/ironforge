-- =============================================================================
-- RESET UI SUPABASE - Enterprise RBAC Architecture
-- =============================================================================
-- Run this FIRST to drop all existing tables, then run ui_schema.sql
-- =============================================================================

-- Drop functions first (CASCADE handles dependent triggers and policies)
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS public.sync_user_from_auth() CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;

-- =============================================================================
-- Drop all tables (CASCADE handles dependencies)
-- =============================================================================

-- Level 4: Record Sharing
DROP TABLE IF EXISTS record_shares CASCADE;
DROP TABLE IF EXISTS sharing_rules CASCADE;

-- Level 3: Teams
DROP TABLE IF EXISTS team_members CASCADE;
DROP TABLE IF EXISTS teams CASCADE;

-- Level 2: Permission Sets
DROP TABLE IF EXISTS user_permission_sets CASCADE;
DROP TABLE IF EXISTS permission_set_permissions CASCADE;
DROP TABLE IF EXISTS permission_sets CASCADE;

-- Level 1: Profiles
DROP TABLE IF EXISTS profile_permissions CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;

-- System tables
DROP TABLE IF EXISTS api_key_usage CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS invite_tokens CASCADE;
DROP TABLE IF EXISTS user_modules CASCADE;
DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS permissions CASCADE;

-- Legacy RBAC tables (for cleanup of old installs)
DROP TABLE IF EXISTS role_permissions CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS roles CASCADE;

-- Core
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Old table names (cleanup)
DROP TABLE IF EXISTS user_profiles CASCADE;

-- =============================================================================
-- Done! Now run ui_schema.sql
-- =============================================================================
