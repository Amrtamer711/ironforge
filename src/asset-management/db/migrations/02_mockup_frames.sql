-- =============================================================================
-- MIGRATION 02: MOCKUP FRAMES TABLE
-- =============================================================================
-- Adds mockup_frames table to each company schema for storing frame coordinate
-- data used in mockup generation.
--
-- This table stores the perspective transformation data for each location's
-- mockup photos, enabling billboard creative compositing.
-- =============================================================================

-- Function to add mockup_frames table to a company schema
CREATE OR REPLACE FUNCTION add_mockup_frames_table(v_schema TEXT) RETURNS VOID AS $$
BEGIN
    -- Check if table already exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = v_schema AND table_name = 'mockup_frames'
    ) THEN
        RAISE NOTICE 'mockup_frames table already exists in schema %', v_schema;
        RETURN;
    END IF;

    -- Create mockup_frames table
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.mockup_frames (
            id BIGSERIAL PRIMARY KEY,
            location_key TEXT NOT NULL,
            time_of_day TEXT NOT NULL DEFAULT ''day'' CHECK (time_of_day IN (''day'', ''night'')),
            finish TEXT NOT NULL DEFAULT ''gold'' CHECK (finish IN (''gold'', ''silver'', ''black'')),
            photo_filename TEXT NOT NULL,
            frames_data JSONB NOT NULL DEFAULT ''[]'',
            config JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            CONSTRAINT mockup_frames_unique UNIQUE (location_key, time_of_day, finish, photo_filename)
        )', v_schema);

    -- Create indexes
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_frames_location_key ON %I.mockup_frames(location_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_frames_lookup ON %I.mockup_frames(location_key, time_of_day, finish)', v_schema);

    RAISE NOTICE 'Created mockup_frames table in schema %', v_schema;
END;
$$ LANGUAGE plpgsql;

-- Apply to all company schemas
DO $$
DECLARE
    v_schema TEXT;
BEGIN
    FOR v_schema IN
        SELECT code FROM public.companies WHERE NOT is_group AND is_active
    LOOP
        PERFORM add_mockup_frames_table(v_schema);
    END LOOP;
END $$;

-- Drop the helper function
DROP FUNCTION IF EXISTS add_mockup_frames_table(TEXT);
