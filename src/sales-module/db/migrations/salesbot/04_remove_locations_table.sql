-- =============================================================================
-- MIGRATION: Remove Locations Table from Sales-Module
-- =============================================================================
-- Locations now live in Asset-Management Supabase.
-- Sales-Module references locations via location_key (text), not location_id (FK).
--
-- This migration:
-- 1. Drops FK constraints from mockup_frames, mockup_usage, location_photos
-- 2. Drops the locations table (moved to Asset-Management)
-- 3. Keeps location_key as the cross-service reference
--
-- ARCHITECTURE AFTER THIS MIGRATION:
-- - Asset-Management Supabase: {company}.standalone_assets, networks, packages
-- - Sales-Module Supabase: mockup_frames, mockup_usage (link via location_key)
-- =============================================================================

DO $$
DECLARE
    v_schema TEXT;
    v_schemas TEXT[] := ARRAY['backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola'];
BEGIN
    FOREACH v_schema IN ARRAY v_schemas
    LOOP
        -- Check if schema exists
        IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = v_schema) THEN

            -- =================================================================
            -- DROP location_id COLUMN FROM mockup_frames
            -- (location_key remains as the reference)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = v_schema
                AND table_name = 'mockup_frames'
                AND column_name = 'location_id'
            ) THEN
                EXECUTE format('ALTER TABLE %I.mockup_frames DROP COLUMN location_id', v_schema);
                RAISE NOTICE 'Dropped location_id from %.mockup_frames', v_schema;
            END IF;

            -- =================================================================
            -- DROP location_id COLUMN FROM mockup_usage
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = v_schema
                AND table_name = 'mockup_usage'
                AND column_name = 'location_id'
            ) THEN
                EXECUTE format('ALTER TABLE %I.mockup_usage DROP COLUMN location_id', v_schema);
                RAISE NOTICE 'Dropped location_id from %.mockup_usage', v_schema;
            END IF;

            -- =================================================================
            -- DROP location_id COLUMN FROM location_photos
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = v_schema
                AND table_name = 'location_photos'
                AND column_name = 'location_id'
            ) THEN
                EXECUTE format('ALTER TABLE %I.location_photos DROP COLUMN location_id', v_schema);
                RAISE NOTICE 'Dropped location_id from %.location_photos', v_schema;
            END IF;

            -- =================================================================
            -- DROP network_id and type_id FROM locations (if networks migration ran)
            -- These now live in Asset-Management
            -- =================================================================

            -- =================================================================
            -- DROP LOCATIONS TABLE
            -- (Data now lives in Asset-Management Supabase)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = v_schema
                AND table_name = 'locations'
            ) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I.locations CASCADE', v_schema);
                RAISE NOTICE 'Dropped %.locations table (moved to Asset-Management)', v_schema;
            END IF;

            -- =================================================================
            -- DROP NETWORKS TABLE (if exists)
            -- (Networks now live in Asset-Management)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = v_schema
                AND table_name = 'networks'
            ) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I.networks CASCADE', v_schema);
                RAISE NOTICE 'Dropped %.networks table (moved to Asset-Management)', v_schema;
            END IF;

            -- =================================================================
            -- DROP ASSET_TYPES TABLE (if exists)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = v_schema
                AND table_name = 'asset_types'
            ) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I.asset_types CASCADE', v_schema);
                RAISE NOTICE 'Dropped %.asset_types table (moved to Asset-Management)', v_schema;
            END IF;

            -- =================================================================
            -- DROP PACKAGES TABLE (if exists)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = v_schema
                AND table_name = 'packages'
            ) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I.packages CASCADE', v_schema);
                RAISE NOTICE 'Dropped %.packages table (moved to Asset-Management)', v_schema;
            END IF;

            -- =================================================================
            -- DROP PACKAGE_ITEMS TABLE (if exists)
            -- =================================================================
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = v_schema
                AND table_name = 'package_items'
            ) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I.package_items CASCADE', v_schema);
                RAISE NOTICE 'Dropped %.package_items table (moved to Asset-Management)', v_schema;
            END IF;

            -- =================================================================
            -- ADD INDEX ON location_key for mockup tables (if not exists)
            -- =================================================================
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_frames_location_key ON %I.mockup_frames(location_key)', v_schema);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_location_key ON %I.mockup_usage(location_key)', v_schema);

            RAISE NOTICE 'Schema % updated - locations moved to Asset-Management', v_schema;
        ELSE
            RAISE NOTICE 'Schema % does not exist, skipping', v_schema;
        END IF;
    END LOOP;
END $$;

-- =============================================================================
-- DROP CROSS-SCHEMA VIEWS (moved to Asset-Management)
-- =============================================================================
DROP VIEW IF EXISTS public.all_locations;
DROP VIEW IF EXISTS public.all_networks;
DROP VIEW IF EXISTS public.all_asset_types;
DROP VIEW IF EXISTS public.all_packages;

-- =============================================================================
-- DROP HELPER FUNCTIONS (moved to Asset-Management)
-- =============================================================================
DROP FUNCTION IF EXISTS public.get_network_locations(TEXT, BIGINT);
DROP FUNCTION IF EXISTS public.expand_package_to_locations(TEXT, BIGINT);

-- =============================================================================
-- DONE!
-- =============================================================================
--
-- TABLES REMOVED FROM SALES-MODULE:
--   {company}.locations -> Asset-Management.{company}.standalone_assets
--   {company}.networks -> Asset-Management.{company}.networks
--   {company}.asset_types -> Asset-Management.{company}.asset_types
--   {company}.packages -> Asset-Management.{company}.packages
--
-- TABLES UPDATED:
--   {company}.mockup_frames - location_id column removed, uses location_key
--   {company}.mockup_usage - location_id column removed, uses location_key
--   {company}.location_photos - location_id column removed, uses location_key
--
-- CROSS-SERVICE LINKING:
--   Sales-Module.mockup_frames.location_key -> Asset-Management.standalone_assets.asset_key
--   Sales-Module.proposal_locations.location_key -> Asset-Management.standalone_assets.asset_key
--
-- =============================================================================
