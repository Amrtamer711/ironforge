-- =============================================================================
-- SALES BOT SUPABASE - COMPLETE RESET (MULTI-SCHEMA)
-- =============================================================================
-- Run this in: Sales-Bot-Dev or Sales-Bot-Prod Supabase SQL Editor
--
-- WARNING: This will DELETE ALL DATA in the Sales Bot database!
-- This includes all company schemas and their data.
--
-- Only use this for:
-- - Fresh installations
-- - Complete schema rebuilds
-- - Development/testing environments
--
-- After running this, run: salesbot/01_schema.sql
-- =============================================================================

-- Drop cross-schema views first
DROP VIEW IF EXISTS public.all_locations CASCADE;
DROP VIEW IF EXISTS public.all_proposals CASCADE;
DROP VIEW IF EXISTS public.all_booking_orders CASCADE;
DROP VIEW IF EXISTS public.all_ai_costs CASCADE;

-- Drop company schemas (this drops ALL tables, views, functions in each schema)
DROP SCHEMA IF EXISTS backlite_dubai CASCADE;
DROP SCHEMA IF EXISTS backlite_uk CASCADE;
DROP SCHEMA IF EXISTS backlite_abudhabi CASCADE;
DROP SCHEMA IF EXISTS viola CASCADE;

-- Drop public schema functions
DROP FUNCTION IF EXISTS public.create_company_schema(TEXT) CASCADE;
DROP FUNCTION IF EXISTS public.get_company_and_children(BIGINT) CASCADE;
DROP FUNCTION IF EXISTS public.get_accessible_schemas(BIGINT[]) CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;

-- Drop public schema tables
DROP TABLE IF EXISTS public.companies CASCADE;

-- =============================================================================
-- RESET COMPLETE
-- =============================================================================
-- The database is now empty. Run salesbot/01_schema.sql to recreate:
-- - public.companies (reference table)
-- - public.* helper functions
-- - backlite_dubai.* schema
-- - backlite_uk.* schema
-- - backlite_abudhabi.* schema
-- - viola.* schema
-- - public.all_* cross-schema views
-- =============================================================================
