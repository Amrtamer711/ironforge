-- =============================================================================
-- MIGRATION 03: Add country column to networks and network_assets
-- =============================================================================
-- Run this migration to add the country field which was in models but not in DB.
-- =============================================================================

-- Helper function to add country column and update VIEW
CREATE OR REPLACE FUNCTION public.add_country_to_schema(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
BEGIN
    -- Add country column to networks table (if not exists)
    EXECUTE format('
        ALTER TABLE %I.networks
        ADD COLUMN IF NOT EXISTS country TEXT
    ', v_schema);

    -- Add country column to network_assets table (if not exists)
    EXECUTE format('
        ALTER TABLE %I.network_assets
        ADD COLUMN IF NOT EXISTS country TEXT
    ', v_schema);

    -- Recreate the locations VIEW with country field
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
            n.country,
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

    RAISE NOTICE 'Added country column to % schema', v_schema;
END;
$$ LANGUAGE plpgsql;

-- Apply to all company schemas
SELECT public.add_country_to_schema('backlite_dubai');
SELECT public.add_country_to_schema('backlite_uk');
SELECT public.add_country_to_schema('backlite_abudhabi');
SELECT public.add_country_to_schema('viola');

-- Clean up helper function
DROP FUNCTION IF EXISTS public.add_country_to_schema(TEXT);

-- =============================================================================
-- Update the base schema function for new companies
-- =============================================================================
-- The main create_company_asset_schema function should also be updated
-- to include country in future company creations. See 01_schema.sql.
