-- =============================================================================
-- RESET SALES BOT SUPABASE
-- =============================================================================
-- Run this FIRST to drop all existing tables, then run salesbot_schema.sql
-- =============================================================================

-- Drop all policies first
DROP POLICY IF EXISTS "Service role full access to proposals" ON proposals_log;
DROP POLICY IF EXISTS "Service role full access to mockup_frames" ON mockup_frames;
DROP POLICY IF EXISTS "Service role full access to mockup_usage" ON mockup_usage;
DROP POLICY IF EXISTS "Service role full access to booking_orders" ON booking_orders;
DROP POLICY IF EXISTS "Service role full access to bo_workflows" ON bo_approval_workflows;
DROP POLICY IF EXISTS "Service role full access to ai_costs" ON ai_costs;

-- Drop old policies that might exist from previous schema
DROP POLICY IF EXISTS "proposals_select_own" ON proposals_log;
DROP POLICY IF EXISTS "proposals_insert_own" ON proposals_log;
DROP POLICY IF EXISTS "proposals_admin_all" ON proposals_log;

-- Drop triggers
DROP TRIGGER IF EXISTS update_bo_workflows_updated_at ON bo_approval_workflows;

-- Drop functions
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;

-- Drop all tables (CASCADE handles dependencies)
DROP TABLE IF EXISTS ai_costs CASCADE;
DROP TABLE IF EXISTS bo_approval_workflows CASCADE;
DROP TABLE IF EXISTS booking_orders CASCADE;
DROP TABLE IF EXISTS mockup_usage CASCADE;
DROP TABLE IF EXISTS mockup_frames CASCADE;
DROP TABLE IF EXISTS proposals_log CASCADE;

-- Also drop any old auth tables that shouldn't be here
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
-- Done! Now run salesbot_schema.sql
-- =============================================================================
