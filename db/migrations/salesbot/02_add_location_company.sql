-- =============================================================================
-- MIGRATION: Add location_company columns to existing tables
-- =============================================================================
-- Run this if you have an existing database and got the error:
-- "column 'location_company' does not exist"
--
-- This adds the new location_company column to tables that track which
-- company schema owns referenced locations.
-- =============================================================================

-- Add location_company to proposal_locations (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'proposal_locations'
        AND column_name = 'location_company'
    ) THEN
        ALTER TABLE public.proposal_locations
        ADD COLUMN location_company TEXT;

        CREATE INDEX IF NOT EXISTS idx_proposal_locations_company
        ON public.proposal_locations(location_company);

        RAISE NOTICE 'Added location_company to proposal_locations';
    ELSE
        RAISE NOTICE 'location_company already exists in proposal_locations';
    END IF;
END $$;

-- Add location_company to bo_locations (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'bo_locations'
        AND column_name = 'location_company'
    ) THEN
        ALTER TABLE public.bo_locations
        ADD COLUMN location_company TEXT;

        CREATE INDEX IF NOT EXISTS idx_bo_locations_company
        ON public.bo_locations(location_company);

        RAISE NOTICE 'Added location_company to bo_locations';
    ELSE
        RAISE NOTICE 'location_company already exists in bo_locations';
    END IF;
END $$;

-- Add location_company to mockup_files (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'mockup_files'
        AND column_name = 'location_company'
    ) THEN
        ALTER TABLE public.mockup_files
        ADD COLUMN location_company TEXT;

        CREATE INDEX IF NOT EXISTS idx_mockup_files_company
        ON public.mockup_files(location_company);

        RAISE NOTICE 'Added location_company to mockup_files';
    ELSE
        RAISE NOTICE 'location_company already exists in mockup_files';
    END IF;
END $$;

-- =============================================================================
-- DONE! The location_company columns have been added.
-- =============================================================================
--
-- Now you can run the full schema (01_schema.sql) which will:
-- - Skip tables that already exist (no changes)
-- - Create any missing tables
-- - Create company schemas and their tables
-- - Create helper functions and views
--
-- =============================================================================
