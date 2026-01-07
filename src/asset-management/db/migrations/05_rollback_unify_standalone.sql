-- =============================================================================
-- MIGRATION 03: ROLLBACK - RESTORE STANDALONE ASSETS
-- =============================================================================
-- This migration reverses the unified architecture if needed.
-- It restores the standalone_assets table and reverts package_items constraints.
--
-- USE WITH CAUTION: Only run this if you need to revert to the old architecture.
-- Data migration back to standalone_assets requires manual verification.
-- =============================================================================

-- =============================================================================
-- HELPER: Rollback function for each company schema
-- =============================================================================

CREATE OR REPLACE FUNCTION public.rollback_unified_networks(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
    v_standalone_count INTEGER;
BEGIN
    RAISE NOTICE 'Starting rollback for schema: %', v_schema;

    -- =========================================================================
    -- STEP 1: Restore standalone_assets table from archive (if exists)
    -- =========================================================================
    RAISE NOTICE '  Step 1: Restoring standalone_assets table...';

    -- Check if archived table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = v_schema AND table_name = '_standalone_assets_archived'
    ) THEN
        -- Rename archived back to active
        EXECUTE format('
            ALTER TABLE IF EXISTS %I._standalone_assets_archived
            RENAME TO standalone_assets
        ', v_schema);

        -- Recreate indexes
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_key ON %I.standalone_assets(asset_key)', v_schema);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_active ON %I.standalone_assets(is_active)', v_schema);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_city ON %I.standalone_assets(city)', v_schema);

        -- Recreate trigger
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_standalone_assets_updated_at ON %I.standalone_assets;
            CREATE TRIGGER update_standalone_assets_updated_at
                BEFORE UPDATE ON %I.standalone_assets
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
        ', v_schema, v_schema);

        -- Re-enable RLS
        EXECUTE format('ALTER TABLE %I.standalone_assets ENABLE ROW LEVEL SECURITY', v_schema);
        EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.standalone_assets', v_schema);
        EXECUTE format('CREATE POLICY "Service role full access" ON %I.standalone_assets FOR ALL USING (true)', v_schema);

        RAISE NOTICE '    Restored standalone_assets from archive';
    ELSE
        -- Create fresh standalone_assets table
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.standalone_assets (
                id BIGSERIAL PRIMARY KEY,
                asset_key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                display_type TEXT NOT NULL CHECK (display_type IN (''digital'', ''static'')),
                series TEXT,
                height TEXT,
                width TEXT,
                number_of_faces INTEGER DEFAULT 1,
                spot_duration INTEGER,
                loop_duration INTEGER,
                sov_percent DECIMAL(5,2),
                upload_fee DECIMAL(10,2),
                city TEXT,
                area TEXT,
                address TEXT,
                gps_lat DECIMAL(10,7),
                gps_lng DECIMAL(10,7),
                template_path TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_by TEXT,
                notes TEXT
            )
        ', v_schema);

        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_key ON %I.standalone_assets(asset_key)', v_schema);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_active ON %I.standalone_assets(is_active)', v_schema);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_city ON %I.standalone_assets(city)', v_schema);

        -- Migrate standalone networks back to standalone_assets
        EXECUTE format('
            INSERT INTO %I.standalone_assets (
                asset_key, display_name, display_type, series, height, width,
                number_of_faces, spot_duration, loop_duration, sov_percent, upload_fee,
                city, area, address, gps_lat, gps_lng,
                template_path, is_active, created_at, updated_at, created_by, notes
            )
            SELECT
                n.network_key,
                n.name,
                n.display_type,
                n.series,
                n.height,
                n.width,
                n.number_of_faces,
                n.spot_duration,
                n.loop_duration,
                n.sov_percent,
                n.upload_fee,
                n.city,
                n.area,
                n.address,
                n.gps_lat,
                n.gps_lng,
                n.template_path,
                n.is_active,
                n.created_at,
                n.updated_at,
                n.created_by,
                n.notes
            FROM %I.networks n
            WHERE n.standalone = true
        ', v_schema, v_schema);

        GET DIAGNOSTICS v_standalone_count = ROW_COUNT;
        RAISE NOTICE '    Migrated % standalone networks back to standalone_assets', v_standalone_count;

        -- Setup RLS and triggers
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_standalone_assets_updated_at ON %I.standalone_assets;
            CREATE TRIGGER update_standalone_assets_updated_at
                BEFORE UPDATE ON %I.standalone_assets
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
        ', v_schema, v_schema);

        EXECUTE format('ALTER TABLE %I.standalone_assets ENABLE ROW LEVEL SECURITY', v_schema);
        EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.standalone_assets', v_schema);
        EXECUTE format('CREATE POLICY "Service role full access" ON %I.standalone_assets FOR ALL USING (true)', v_schema);
    END IF;

    RAISE NOTICE '  Step 1: Complete';

    -- =========================================================================
    -- STEP 2: Add standalone_asset_id column to package_items
    -- =========================================================================
    RAISE NOTICE '  Step 2: Updating package_items constraints...';

    -- Add standalone_asset_id column
    EXECUTE format('
        ALTER TABLE %I.package_items
        ADD COLUMN IF NOT EXISTS standalone_asset_id BIGINT REFERENCES %I.standalone_assets(id) ON DELETE CASCADE
    ', v_schema, v_schema);

    -- Update package_items that reference standalone networks
    EXECUTE format('
        UPDATE %I.package_items pi SET
            item_type = ''standalone'',
            standalone_asset_id = (
                SELECT sa.id FROM %I.standalone_assets sa
                WHERE sa.asset_key = (
                    SELECT n.network_key FROM %I.networks n
                    WHERE n.id = pi.network_id AND n.standalone = true
                )
            ),
            network_id = NULL
        WHERE pi.network_id IN (
            SELECT n.id FROM %I.networks n WHERE n.standalone = true
        )
    ', v_schema, v_schema, v_schema, v_schema);

    -- Drop new constraint
    EXECUTE format('
        ALTER TABLE %I.package_items
        DROP CONSTRAINT IF EXISTS package_items_network_only
    ', v_schema);

    -- Restore old constraint
    EXECUTE format('
        ALTER TABLE %I.package_items
        ADD CONSTRAINT package_items_type_check CHECK (
            (item_type = ''network'' AND network_id IS NOT NULL AND standalone_asset_id IS NULL) OR
            (item_type = ''standalone'' AND standalone_asset_id IS NOT NULL AND network_id IS NULL)
        )
    ', v_schema);

    RAISE NOTICE '  Step 2: Complete';

    -- =========================================================================
    -- STEP 3: Restore locations VIEW with UNION
    -- =========================================================================
    RAISE NOTICE '  Step 3: Restoring locations VIEW with UNION...';

    EXECUTE format('
        CREATE OR REPLACE VIEW %I.locations AS
        -- Networks (sellable as complete units)
        SELECT
            n.id,
            n.network_key AS location_key,
            n.name AS display_name,
            NULL::TEXT AS display_type,
            n.id AS network_id,
            NULL::BIGINT AS type_id,
            n.series,
            NULL::TEXT AS height,
            NULL::TEXT AS width,
            n.number_of_faces,
            n.spot_duration,
            n.loop_duration,
            n.sov_percent,
            n.upload_fee,
            NULL::TEXT AS city,
            NULL::TEXT AS area,
            NULL::TEXT AS address,
            NULL::DECIMAL(10,7) AS gps_lat,
            NULL::DECIMAL(10,7) AS gps_lng,
            n.template_path,
            n.is_active,
            n.created_at,
            n.updated_at,
            n.created_by,
            n.notes,
            ''network''::TEXT AS asset_source
        FROM %I.networks n
        WHERE n.standalone = false  -- Only traditional networks in VIEW

        UNION ALL

        -- Standalone assets (sellable individually)
        SELECT
            sa.id,
            sa.asset_key AS location_key,
            sa.display_name,
            sa.display_type,
            NULL::BIGINT AS network_id,
            NULL::BIGINT AS type_id,
            sa.series,
            sa.height,
            sa.width,
            sa.number_of_faces,
            sa.spot_duration,
            sa.loop_duration,
            sa.sov_percent,
            sa.upload_fee,
            sa.city,
            sa.area,
            sa.address,
            sa.gps_lat,
            sa.gps_lng,
            sa.template_path,
            sa.is_active,
            sa.created_at,
            sa.updated_at,
            sa.created_by,
            sa.notes,
            ''standalone''::TEXT AS asset_source
        FROM %I.standalone_assets sa
    ', v_schema, v_schema, v_schema);

    RAISE NOTICE '  Step 3: Complete';

    -- =========================================================================
    -- STEP 4: Delete standalone networks from networks table
    -- =========================================================================
    RAISE NOTICE '  Step 4: Removing standalone networks from networks table...';

    EXECUTE format('
        DELETE FROM %I.networks WHERE standalone = true
    ', v_schema);

    RAISE NOTICE '  Step 4: Complete';

    -- =========================================================================
    -- STEP 5: Remove standalone columns from networks table
    -- =========================================================================
    RAISE NOTICE '  Step 5: Removing unified columns from networks table...';

    EXECUTE format('DROP INDEX IF EXISTS %I.idx_networks_standalone', v_schema);
    EXECUTE format('DROP INDEX IF EXISTS %I.idx_networks_standalone_active', v_schema);

    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS standalone', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS display_type', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS height', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS width', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS city', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS area', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS address', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS gps_lat', v_schema);
    EXECUTE format('ALTER TABLE %I.networks DROP COLUMN IF EXISTS gps_lng', v_schema);

    RAISE NOTICE '  Step 5: Complete';

    -- =========================================================================
    -- STEP 6: Remove environment column from network_assets
    -- =========================================================================
    RAISE NOTICE '  Step 6: Removing environment column from network_assets...';

    EXECUTE format('DROP INDEX IF EXISTS %I.idx_network_assets_environment', v_schema);
    EXECUTE format('ALTER TABLE %I.network_assets DROP COLUMN IF EXISTS environment', v_schema);

    RAISE NOTICE '  Step 6: Complete';

    RAISE NOTICE 'Rollback complete for schema: %', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- EXECUTE ROLLBACK FOR ALL COMPANY SCHEMAS
-- =============================================================================
-- UNCOMMENT THESE LINES TO EXECUTE THE ROLLBACK:

-- SELECT public.rollback_unified_networks('backlite_dubai');
-- SELECT public.rollback_unified_networks('backlite_uk');
-- SELECT public.rollback_unified_networks('backlite_abudhabi');
-- SELECT public.rollback_unified_networks('viola');

-- =============================================================================
-- RESTORE CROSS-SCHEMA VIEWS
-- =============================================================================
-- UNCOMMENT THESE LINES AFTER EXECUTING THE ROLLBACK:

-- CREATE OR REPLACE VIEW public.all_standalone_assets AS
-- SELECT 'backlite_dubai' as company_code, a.* FROM backlite_dubai.standalone_assets a
-- UNION ALL
-- SELECT 'backlite_uk' as company_code, a.* FROM backlite_uk.standalone_assets a
-- UNION ALL
-- SELECT 'backlite_abudhabi' as company_code, a.* FROM backlite_abudhabi.standalone_assets a
-- UNION ALL
-- SELECT 'viola' as company_code, a.* FROM viola.standalone_assets a;

-- =============================================================================
-- CLEANUP: Drop rollback function (optional)
-- =============================================================================
-- DROP FUNCTION IF EXISTS public.rollback_unified_networks(TEXT);

RAISE NOTICE '=== Migration 03: Rollback script ready ===';
RAISE NOTICE 'IMPORTANT: Uncomment the SELECT statements above to execute rollback.';
RAISE NOTICE 'This script is designed to be run manually after verification.';
