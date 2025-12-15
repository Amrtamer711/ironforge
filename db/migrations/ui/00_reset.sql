-- =============================================================================
-- UI DATABASE RESET (COMPLETE)
-- =============================================================================
-- WARNING: This will DELETE ALL DATA in the UI database!
-- Only use for fresh installations or complete resets.
--
-- Run this in: UI-Module-Dev or UI-Module-Prod Supabase SQL Editor
-- =============================================================================

-- First, drop triggers on auth.users (these reference public schema)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_sync ON auth.users;

-- Drop everything in public schema (tables, views, functions, triggers)
-- CASCADE ensures all dependent objects are also dropped
DROP TABLE IF EXISTS api_key_usage CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS invite_tokens CASCADE;
DROP TABLE IF EXISTS user_modules CASCADE;
DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS permissions CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS channel_identities CASCADE;
DROP TABLE IF EXISTS slack_identities CASCADE;
DROP TABLE IF EXISTS record_shares CASCADE;
DROP TABLE IF EXISTS sharing_rules CASCADE;
DROP TABLE IF EXISTS team_members CASCADE;
DROP TABLE IF EXISTS user_permission_sets CASCADE;
DROP TABLE IF EXISTS user_companies CASCADE;
DROP TABLE IF EXISTS permission_set_permissions CASCADE;
DROP TABLE IF EXISTS permission_sets CASCADE;
DROP TABLE IF EXISTS profile_permissions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS teams CASCADE;
DROP TABLE IF EXISTS companies CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;

-- Drop all views
DROP VIEW IF EXISTS channel_identities_full CASCADE;
DROP VIEW IF EXISTS channel_pending_links CASCADE;
DROP VIEW IF EXISTS user_companies_detailed CASCADE;
DROP VIEW IF EXISTS companies_with_hierarchy CASCADE;

-- Drop all functions (CASCADE handles dependent triggers)
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS public.sync_user_from_auth() CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;
DROP FUNCTION IF EXISTS public.get_user_accessible_companies(TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.user_can_access_company(TEXT, BIGINT) CASCADE;
DROP FUNCTION IF EXISTS public.get_company_hierarchy(BIGINT) CASCADE;
DROP FUNCTION IF EXISTS public.record_channel_interaction(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.check_channel_authorization(TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.link_channel_identity(TEXT, TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.auto_link_channel_by_email(TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.create_audit_log(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB, JSONB) CASCADE;
DROP FUNCTION IF EXISTS public.audit_profile_change() CASCADE;
DROP FUNCTION IF EXISTS public.ensure_single_primary_company() CASCADE;
DROP FUNCTION IF EXISTS public.auto_set_primary_company() CASCADE;

-- Legacy slack functions
DROP FUNCTION IF EXISTS public.record_slack_interaction(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.check_slack_authorization(TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.link_slack_identity(TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.auto_link_slack_by_email() CASCADE;
DROP FUNCTION IF EXISTS public.unlink_slack_identity(TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.set_slack_blocked(TEXT, BOOLEAN, TEXT, TEXT) CASCADE;

-- =============================================================================
-- Database is now clean. Run 01_schema.sql to recreate.
-- =============================================================================
