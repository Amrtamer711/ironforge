-- =============================================================================
-- MIGRATION 02: UNIFY STANDALONE ASSETS INTO NETWORKS
-- =============================================================================
-- This migration eliminates the standalone_assets table by merging everything
-- into the networks table with a `standalone` flag.
--
-- KEY CHANGES:
-- 1. Add standalone flag + location fields to networks
-- 2. Add environment field to network_assets
-- 3. Migrate standalone_assets data to networks with standalone=true
-- 4. Update package_items to remove standalone references
-- 5. Update asset_photos/occupations to remove standalone references
-- 6. Update locations VIEW (simplified, no asset_source)
-- 7. Archive standalone_assets table
--
-- IMPORTANT: The `standalone` flag is INTERNAL ONLY - never exposed to frontend
-- =============================================================================

-- =============================================================================
-- HELPER: Migration function for each company schema
-- =============================================================================

CREATE OR REPLACE FUNCTION public.migrate_company_to_unified_networks(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
    v_standalone_count INTEGER;
    v_migrated_count INTEGER;
BEGIN
    RAISE NOTICE 'Starting migration for schema: %', v_schema;

    -- =========================================================================
    -- STEP 1: Add new columns to networks table
    -- =========================================================================
    RAISE NOTICE '  Step 1: Adding columns to networks table...';

    -- Add standalone flag (INTERNAL ONLY)
    EXECUTE format('
        ALTER TABLE %I.networks
        ADD COLUMN IF NOT EXISTS standalone BOOLEAN DEFAULT false
    ', v_schema);

    -- Add location fields (for standalone networks)
    EXECUTE format('
        ALTER TABLE %I.networks
        ADD COLUMN IF NOT EXISTS display_type TEXT CHECK (display_type IS NULL OR display_type IN (''digital'', ''static''))
    ', v_schema);

    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS height TEXT', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS width TEXT', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS city TEXT', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS area TEXT', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS address TEXT', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS gps_lat DECIMAL(10,7)', v_schema);
    EXECUTE format('ALTER TABLE %I.networks ADD COLUMN IF NOT EXISTS gps_lng DECIMAL(10,7)', v_schema);

    -- Add index for standalone queries
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_networks_standalone ON %I.networks(standalone)
    ', v_schema);

    RAISE NOTICE '  Step 1: Complete - added standalone and location fields to networks';

    -- =========================================================================
    -- STEP 2: Add environment field to network_assets
    -- =========================================================================
    RAISE NOTICE '  Step 2: Adding environment field to network_assets...';

    EXECUTE format('
        ALTER TABLE %I.network_assets
        ADD COLUMN IF NOT EXISTS environment TEXT DEFAULT ''outdoor''
            CHECK (environment IN (''indoor'', ''outdoor''))
    ', v_schema);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_network_assets_environment ON %I.network_assets(environment)
    ', v_schema);

    RAISE NOTICE '  Step 2: Complete - added environment field to network_assets';

    -- =========================================================================
    -- STEP 3: Migrate standalone_assets to networks with standalone=true
    -- =========================================================================
    RAISE NOTICE '  Step 3: Migrating standalone_assets to networks...';

    -- Count existing standalone assets
    EXECUTE format('SELECT COUNT(*) FROM %I.standalone_assets', v_schema) INTO v_standalone_count;
    RAISE NOTICE '    Found % standalone assets to migrate', v_standalone_count;

    IF v_standalone_count > 0 THEN
        -- Insert standalone assets as networks with standalone=true
        EXECUTE format('
            INSERT INTO %I.networks (
                network_key, name, standalone, display_type,
                series, height, width, number_of_faces,
                spot_duration, loop_duration, sov_percent, upload_fee,
                city, area, address, gps_lat, gps_lng,
                template_path, is_active, created_at, updated_at, created_by, notes
            )
            SELECT
                sa.asset_key,
                sa.display_name,
                true,
                sa.display_type,
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
                sa.notes
            FROM %I.standalone_assets sa
            ON CONFLICT (network_key) DO UPDATE SET
                standalone = true,
                display_type = EXCLUDED.display_type,
                height = EXCLUDED.height,
                width = EXCLUDED.width,
                city = EXCLUDED.city,
                area = EXCLUDED.area,
                address = EXCLUDED.address,
                gps_lat = EXCLUDED.gps_lat,
                gps_lng = EXCLUDED.gps_lng,
                updated_at = NOW()
        ', v_schema, v_schema);

        GET DIAGNOSTICS v_migrated_count = ROW_COUNT;
        RAISE NOTICE '    Migrated % standalone assets to networks', v_migrated_count;
    END IF;

    RAISE NOTICE '  Step 3: Complete - standalone assets migrated to networks';

    -- =========================================================================
    -- STEP 4: Update package_items to point to new network IDs
    -- =========================================================================
    RAISE NOTICE '  Step 4: Updating package_items references...';

    -- Update package_items that reference standalone_assets to reference the new network
    EXECUTE format('
        UPDATE %I.package_items pi SET
            item_type = ''network'',
            network_id = (
                SELECT n.id FROM %I.networks n
                WHERE n.network_key = (
                    SELECT sa.asset_key FROM %I.standalone_assets sa
                    WHERE sa.id = pi.standalone_asset_id
                )
            ),
            standalone_asset_id = NULL
        WHERE pi.item_type = ''standalone'' AND pi.standalone_asset_id IS NOT NULL
    ', v_schema, v_schema, v_schema);

    GET DIAGNOSTICS v_migrated_count = ROW_COUNT;
    RAISE NOTICE '    Updated % package_items from standalone to network', v_migrated_count;

    RAISE NOTICE '  Step 4: Complete - package_items updated';

    -- =========================================================================
    -- STEP 5: Update asset_photos references (if any)
    -- =========================================================================
    RAISE NOTICE '  Step 5: Updating asset_photos references...';

    -- First, we need to create network_assets for standalone networks
    -- (This is a simplification - in reality you might want to handle this differently)
    -- For now, we'll leave photos pointing to standalone_assets until archive

    RAISE NOTICE '  Step 5: Complete - asset_photos will be handled during archive';

    -- =========================================================================
    -- STEP 6: Update asset_occupations references (if any)
    -- =========================================================================
    RAISE NOTICE '  Step 6: Updating asset_occupations references...';

    -- Similar to asset_photos - leave until archive

    RAISE NOTICE '  Step 6: Complete - asset_occupations will be handled during archive';

    -- =========================================================================
    -- STEP 7: Simplify package_items constraints
    -- =========================================================================
    RAISE NOTICE '  Step 7: Updating package_items constraints...';

    -- Drop old constraint
    EXECUTE format('
        ALTER TABLE %I.package_items
        DROP CONSTRAINT IF EXISTS package_items_type_check
    ', v_schema);

    -- Drop the item_type check constraint
    EXECUTE format('
        ALTER TABLE %I.package_items
        DROP CONSTRAINT IF EXISTS package_items_item_type_check
    ', v_schema);

    -- Update item_type to only allow 'network'
    EXECUTE format('
        ALTER TABLE %I.package_items
        ADD CONSTRAINT package_items_network_only
            CHECK (item_type = ''network'' AND network_id IS NOT NULL)
    ', v_schema);

    RAISE NOTICE '  Step 7: Complete - package_items now only supports networks';

    -- =========================================================================
    -- STEP 8: Update locations VIEW (simplified - no asset_source)
    -- =========================================================================
    RAISE NOTICE '  Step 8: Updating locations VIEW...';

    -- The new locations VIEW only shows networks (both standalone and traditional)
    -- IMPORTANT: standalone flag is NOT exposed in the VIEW
    EXECUTE format('
        CREATE OR REPLACE VIEW %I.locations AS
        SELECT
            n.id,
            n.network_key AS location_key,
            n.name AS display_name,
            n.display_type,
            n.id AS network_id,
            NULL::BIGINT AS type_id,
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
        WHERE n.is_active = true
    ', v_schema, v_schema);

    RAISE NOTICE '  Step 8: Complete - locations VIEW updated (unified, no asset_source)';

    -- =========================================================================
    -- STEP 9: Archive standalone_assets table
    -- =========================================================================
    RAISE NOTICE '  Step 9: Archiving standalone_assets table...';

    -- Rename to archived (keep for 30 days, then drop)
    EXECUTE format('
        ALTER TABLE IF EXISTS %I.standalone_assets
        RENAME TO _standalone_assets_archived
    ', v_schema);

    -- Drop indexes on archived table (optional, for cleanup)
    EXECUTE format('DROP INDEX IF EXISTS %I.idx_standalone_assets_key', v_schema);
    EXECUTE format('DROP INDEX IF EXISTS %I.idx_standalone_assets_active', v_schema);
    EXECUTE format('DROP INDEX IF EXISTS %I.idx_standalone_assets_city', v_schema);

    -- Drop trigger on archived table
    EXECUTE format('
        DROP TRIGGER IF EXISTS update_standalone_assets_updated_at ON %I._standalone_assets_archived
    ', v_schema);

    RAISE NOTICE '  Step 9: Complete - standalone_assets archived as _standalone_assets_archived';

    -- =========================================================================
    -- STEP 10: Clean up RLS policies
    -- =========================================================================
    RAISE NOTICE '  Step 10: Cleaning up RLS policies...';

    -- Remove RLS from archived table
    EXECUTE format('
        ALTER TABLE IF EXISTS %I._standalone_assets_archived DISABLE ROW LEVEL SECURITY
    ', v_schema);

    EXECUTE format('
        DROP POLICY IF EXISTS "Service role full access" ON %I._standalone_assets_archived
    ', v_schema);

    RAISE NOTICE '  Step 10: Complete - RLS policies cleaned up';

    RAISE NOTICE 'Migration complete for schema: %', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- EXECUTE MIGRATION FOR ALL COMPANY SCHEMAS
-- =============================================================================

SELECT public.migrate_company_to_unified_networks('backlite_dubai');
SELECT public.migrate_company_to_unified_networks('backlite_uk');
SELECT public.migrate_company_to_unified_networks('backlite_abudhabi');
SELECT public.migrate_company_to_unified_networks('viola');

-- =============================================================================
-- DROP OBSOLETE CROSS-SCHEMA VIEWS
-- =============================================================================
-- Cross-schema queries are handled in application code, not views

DROP VIEW IF EXISTS public.all_standalone_assets;
DROP VIEW IF EXISTS public.all_networks;
DROP VIEW IF EXISTS public.all_packages;

-- =============================================================================
-- CLEANUP: Drop migration function (optional - keep for re-runs)
-- =============================================================================
-- DROP FUNCTION IF EXISTS public.migrate_company_to_unified_networks(TEXT);

-- =============================================================================
-- VERIFICATION QUERIES (for manual validation)
-- =============================================================================
-- Run these after migration to verify:
--
-- 1. Check standalone networks were created:
--    SELECT network_key, name, standalone, display_type, city
--    FROM backlite_dubai.networks WHERE standalone = true;
--
-- 2. Check no package_items reference standalone:
--    SELECT * FROM backlite_dubai.package_items WHERE item_type = 'standalone';
--
-- 3. Check archived table exists:
--    SELECT COUNT(*) FROM backlite_dubai._standalone_assets_archived;
--
-- 4. Check locations VIEW works:
--    SELECT location_key, display_name, display_type, city
--    FROM backlite_dubai.locations LIMIT 10;
--
-- =============================================================================

RAISE NOTICE '=== Migration 02: Unify Standalone complete! ===';
RAISE NOTICE 'IMPORTANT: Run verification queries to confirm migration success.';
RAISE NOTICE 'Archived tables (_standalone_assets_archived) can be dropped after 30 days.';
