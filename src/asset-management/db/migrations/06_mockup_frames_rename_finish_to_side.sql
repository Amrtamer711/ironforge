-- =============================================================================
-- MIGRATION 06: RENAME FINISH TO SIDE IN MOCKUP_FRAMES
-- =============================================================================
-- Updates the mockup_frames table to:
-- 1. Add environment column (indoor/outdoor)
-- 2. Rename finish column to side
-- 3. Update valid values from ('gold', 'silver', 'black') to ('gold', 'silver', 'single_side')
-- 4. Update unique constraint to include environment
-- =============================================================================

-- =============================================================================
-- HELPER: Migration function for each company schema
-- =============================================================================

CREATE OR REPLACE FUNCTION public.migrate_mockup_frames_finish_to_side(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
    v_has_environment BOOLEAN;
    v_has_finish BOOLEAN;
    v_has_side BOOLEAN;
BEGIN
    RAISE NOTICE 'Starting mockup_frames migration for schema: %', v_schema;

    -- Check if mockup_frames table exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = v_schema AND table_name = 'mockup_frames'
    ) THEN
        RAISE NOTICE '  mockup_frames table does not exist in schema %, skipping...', v_schema;
        RETURN;
    END IF;

    -- =========================================================================
    -- STEP 1: Add environment column if not exists
    -- =========================================================================
    RAISE NOTICE '  Step 1: Adding environment column...';

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = v_schema AND table_name = 'mockup_frames' AND column_name = 'environment'
    ) INTO v_has_environment;

    IF NOT v_has_environment THEN
        EXECUTE format('
            ALTER TABLE %I.mockup_frames
            ADD COLUMN environment TEXT NOT NULL DEFAULT ''outdoor''
                CHECK (environment IN (''indoor'', ''outdoor''))
        ', v_schema);
        RAISE NOTICE '    Added environment column';
    ELSE
        RAISE NOTICE '    environment column already exists';
    END IF;

    -- =========================================================================
    -- STEP 2: Rename finish to side
    -- =========================================================================
    RAISE NOTICE '  Step 2: Renaming finish to side...';

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = v_schema AND table_name = 'mockup_frames' AND column_name = 'finish'
    ) INTO v_has_finish;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = v_schema AND table_name = 'mockup_frames' AND column_name = 'side'
    ) INTO v_has_side;

    IF v_has_finish AND NOT v_has_side THEN
        -- Drop old constraint
        EXECUTE format('
            ALTER TABLE %I.mockup_frames
            DROP CONSTRAINT IF EXISTS mockup_frames_finish_check
        ', v_schema);

        -- Rename column
        EXECUTE format('
            ALTER TABLE %I.mockup_frames
            RENAME COLUMN finish TO side
        ', v_schema);

        RAISE NOTICE '    Renamed finish to side';
    ELSIF v_has_side THEN
        RAISE NOTICE '    side column already exists, skipping rename';
    ELSE
        RAISE NOTICE '    WARNING: Neither finish nor side column found!';
    END IF;

    -- =========================================================================
    -- STEP 3: Update existing 'black' values to 'single_side'
    -- =========================================================================
    RAISE NOTICE '  Step 3: Updating black values to single_side...';

    EXECUTE format('
        UPDATE %I.mockup_frames
        SET side = ''single_side''
        WHERE side = ''black''
    ', v_schema);

    RAISE NOTICE '    Updated black values to single_side';

    -- =========================================================================
    -- STEP 4: Add new CHECK constraint for side
    -- =========================================================================
    RAISE NOTICE '  Step 4: Adding new CHECK constraint...';

    -- Drop any existing side constraint
    EXECUTE format('
        ALTER TABLE %I.mockup_frames
        DROP CONSTRAINT IF EXISTS mockup_frames_side_check
    ', v_schema);

    -- Add new constraint with updated values
    EXECUTE format('
        ALTER TABLE %I.mockup_frames
        ADD CONSTRAINT mockup_frames_side_check
            CHECK (side IN (''gold'', ''silver'', ''single_side''))
    ', v_schema);

    RAISE NOTICE '    Added new CHECK constraint for side';

    -- =========================================================================
    -- STEP 5: Update unique constraint to include environment
    -- =========================================================================
    RAISE NOTICE '  Step 5: Updating unique constraint...';

    -- Drop old unique constraint
    EXECUTE format('
        ALTER TABLE %I.mockup_frames
        DROP CONSTRAINT IF EXISTS mockup_frames_unique
    ', v_schema);

    -- Add new unique constraint with environment
    EXECUTE format('
        ALTER TABLE %I.mockup_frames
        ADD CONSTRAINT mockup_frames_unique
            UNIQUE (location_key, environment, time_of_day, side, photo_filename)
    ', v_schema);

    RAISE NOTICE '    Updated unique constraint to include environment';

    -- =========================================================================
    -- STEP 6: Update indexes
    -- =========================================================================
    RAISE NOTICE '  Step 6: Updating indexes...';

    -- Drop old lookup index
    EXECUTE format('
        DROP INDEX IF EXISTS %I.idx_mockup_frames_lookup
    ', v_schema);

    -- Create new lookup index with environment
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_mockup_frames_lookup
        ON %I.mockup_frames(location_key, environment, time_of_day, side)
    ', v_schema);

    -- Create environment index
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_mockup_frames_environment
        ON %I.mockup_frames(environment)
    ', v_schema);

    RAISE NOTICE '    Updated indexes';

    RAISE NOTICE 'Migration complete for schema: %', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- EXECUTE MIGRATION FOR ALL COMPANY SCHEMAS
-- =============================================================================

SELECT public.migrate_mockup_frames_finish_to_side('backlite_dubai');
SELECT public.migrate_mockup_frames_finish_to_side('backlite_uk');
SELECT public.migrate_mockup_frames_finish_to_side('backlite_abudhabi');
SELECT public.migrate_mockup_frames_finish_to_side('viola');

-- =============================================================================
-- CLEANUP: Drop migration function
-- =============================================================================
DROP FUNCTION IF EXISTS public.migrate_mockup_frames_finish_to_side(TEXT);

-- =============================================================================
-- VERIFICATION QUERIES (for manual validation)
-- =============================================================================
-- Run these after migration to verify:
--
-- 1. Check columns exist:
--    SELECT column_name, data_type, column_default
--    FROM information_schema.columns
--    WHERE table_schema = 'backlite_dubai' AND table_name = 'mockup_frames'
--    ORDER BY ordinal_position;
--
-- 2. Check constraint values:
--    SELECT conname, pg_get_constraintdef(oid)
--    FROM pg_constraint
--    WHERE conrelid = 'backlite_dubai.mockup_frames'::regclass;
--
-- 3. Check no 'black' values remain:
--    SELECT COUNT(*) FROM backlite_dubai.mockup_frames WHERE side = 'black';
--
-- 4. Check side values distribution:
--    SELECT side, COUNT(*) FROM backlite_dubai.mockup_frames GROUP BY side;
--
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '=== Migration 06: Mockup frames finish->side complete! ===';
    RAISE NOTICE 'IMPORTANT: Run verification queries to confirm migration success.';
END $$;
