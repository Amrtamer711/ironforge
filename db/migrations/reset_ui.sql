-- =============================================================================
-- RESET UI SUPABASE
-- =============================================================================
-- Run this FIRST to drop all existing tables, then run ui_schema.sql
-- =============================================================================

-- Drop all policies first
DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
DROP POLICY IF EXISTS "Service role has full access to profiles" ON user_profiles;
DROP POLICY IF EXISTS "Service role has full access to users" ON users;
DROP POLICY IF EXISTS "Authenticated can view users" ON users;
DROP POLICY IF EXISTS "Authenticated can view roles" ON roles;
DROP POLICY IF EXISTS "Service role manages roles" ON roles;
DROP POLICY IF EXISTS "Users can view own roles" ON user_roles;
DROP POLICY IF EXISTS "Service role manages user_roles" ON user_roles;
DROP POLICY IF EXISTS "Authenticated can view permissions" ON permissions;
DROP POLICY IF EXISTS "Service role manages permissions" ON permissions;
DROP POLICY IF EXISTS "Authenticated can view role_permissions" ON role_permissions;
DROP POLICY IF EXISTS "Service role manages role_permissions" ON role_permissions;
DROP POLICY IF EXISTS "Authenticated can view active modules" ON modules;
DROP POLICY IF EXISTS "Service role manages modules" ON modules;
DROP POLICY IF EXISTS "Users can view own modules" ON user_modules;
DROP POLICY IF EXISTS "Service role manages user_modules" ON user_modules;
DROP POLICY IF EXISTS "Service role manages invite_tokens" ON invite_tokens;
DROP POLICY IF EXISTS "Service role manages audit_log" ON audit_log;
DROP POLICY IF EXISTS "Service role manages api_keys" ON api_keys;
DROP POLICY IF EXISTS "Service role manages api_key_usage" ON api_key_usage;

-- Drop triggers
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_sync ON auth.users;
DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;

-- Drop functions
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS public.sync_user_from_auth() CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;

-- Drop all tables (CASCADE handles dependencies)
DROP TABLE IF EXISTS api_key_usage CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS invite_tokens CASCADE;
DROP TABLE IF EXISTS user_modules CASCADE;
DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS role_permissions CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS permissions CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS user_profiles CASCADE;

-- =============================================================================
-- Done! Now run ui_schema.sql
-- =============================================================================
