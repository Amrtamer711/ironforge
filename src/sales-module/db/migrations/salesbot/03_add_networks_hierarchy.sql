-- =============================================================================
-- MIGRATION: Add Networks, Asset Types & Packages Hierarchy
-- =============================================================================
-- This migration adds support for:
-- - Networks: Groups of assets (sellable as a whole)
-- - Asset Types: Organizational categories within networks (NOT sellable)
-- - Packages: Company-specific bundles of networks/assets (sellable)
--
-- HIERARCHY:
--   Network (sellable) → Asset Type (organizational) → Location (sellable)
--   Locations can also be standalone (no network/type)
--   Packages can include networks and/or individual assets
--
-- RUN ORDER:
--   1. 01_schema.sql (base schema)
--   2. 02_add_location_company.sql (if needed)
--   3. 03_add_networks_hierarchy.sql (this file)
-- =============================================================================

-- =============================================================================
-- PART 1: ADD COLUMNS TO EXISTING LOCATIONS TABLES
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
            -- NETWORKS TABLE
            -- =================================================================
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.networks (
                    id BIGSERIAL PRIMARY KEY,
                    network_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    created_by TEXT
                )', v_schema);

            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_key ON %I.networks(network_key)', v_schema);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_active ON %I.networks(is_active)', v_schema);

            -- =================================================================
            -- ASSET TYPES TABLE
            -- =================================================================
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.asset_types (
                    id BIGSERIAL PRIMARY KEY,
                    network_id BIGINT NOT NULL REFERENCES %I.networks(id) ON DELETE CASCADE,
                    type_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    specs JSONB DEFAULT ''{}'',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    created_by TEXT,
                    CONSTRAINT asset_types_unique UNIQUE (network_id, type_key)
                )', v_schema, v_schema);

            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_asset_types_network ON %I.asset_types(network_id)', v_schema);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_asset_types_key ON %I.asset_types(type_key)', v_schema);

            -- =================================================================
            -- PACKAGES TABLE (per-company)
            -- =================================================================
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.packages (
                    id BIGSERIAL PRIMARY KEY,
                    package_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    created_by TEXT
                )', v_schema);

            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_packages_key ON %I.packages(package_key)', v_schema);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_packages_active ON %I.packages(is_active)', v_schema);

            -- =================================================================
            -- PACKAGE ITEMS TABLE (junction)
            -- =================================================================
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.package_items (
                    id BIGSERIAL PRIMARY KEY,
                    package_id BIGINT NOT NULL REFERENCES %I.packages(id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL CHECK (item_type IN (''network'', ''asset'')),
                    network_id BIGINT REFERENCES %I.networks(id) ON DELETE CASCADE,
                    location_id BIGINT REFERENCES %I.locations(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT package_items_type_check CHECK (
                        (item_type = ''network'' AND network_id IS NOT NULL AND location_id IS NULL) OR
                        (item_type = ''asset'' AND location_id IS NOT NULL AND network_id IS NULL)
                    )
                )', v_schema, v_schema, v_schema, v_schema);

            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_package_items_package ON %I.package_items(package_id)', v_schema);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_package_items_type ON %I.package_items(item_type)', v_schema);

            -- =================================================================
            -- ADD network_id TO LOCATIONS
            -- =================================================================
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = v_schema
                AND table_name = 'locations'
                AND column_name = 'network_id'
            ) THEN
                EXECUTE format('
                    ALTER TABLE %I.locations
                    ADD COLUMN network_id BIGINT REFERENCES %I.networks(id) ON DELETE SET NULL
                ', v_schema, v_schema);

                EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_network ON %I.locations(network_id)', v_schema);
                RAISE NOTICE 'Added network_id to %.locations', v_schema;
            END IF;

            -- =================================================================
            -- ADD type_id TO LOCATIONS
            -- =================================================================
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = v_schema
                AND table_name = 'locations'
                AND column_name = 'type_id'
            ) THEN
                EXECUTE format('
                    ALTER TABLE %I.locations
                    ADD COLUMN type_id BIGINT REFERENCES %I.asset_types(id) ON DELETE SET NULL
                ', v_schema, v_schema);

                EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_asset_type ON %I.locations(type_id)', v_schema);
                RAISE NOTICE 'Added type_id to %.locations', v_schema;
            END IF;

            -- =================================================================
            -- RLS & POLICIES
            -- =================================================================
            EXECUTE format('ALTER TABLE %I.networks ENABLE ROW LEVEL SECURITY', v_schema);
            EXECUTE format('ALTER TABLE %I.asset_types ENABLE ROW LEVEL SECURITY', v_schema);
            EXECUTE format('ALTER TABLE %I.packages ENABLE ROW LEVEL SECURITY', v_schema);
            EXECUTE format('ALTER TABLE %I.package_items ENABLE ROW LEVEL SECURITY', v_schema);

            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.networks', v_schema);
            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.asset_types', v_schema);
            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.packages', v_schema);
            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.package_items', v_schema);

            EXECUTE format('CREATE POLICY "Service role full access" ON %I.networks FOR ALL USING (true)', v_schema);
            EXECUTE format('CREATE POLICY "Service role full access" ON %I.asset_types FOR ALL USING (true)', v_schema);
            EXECUTE format('CREATE POLICY "Service role full access" ON %I.packages FOR ALL USING (true)', v_schema);
            EXECUTE format('CREATE POLICY "Service role full access" ON %I.package_items FOR ALL USING (true)', v_schema);

            -- =================================================================
            -- TRIGGERS
            -- =================================================================
            EXECUTE format('
                DROP TRIGGER IF EXISTS update_networks_updated_at ON %I.networks;
                CREATE TRIGGER update_networks_updated_at
                    BEFORE UPDATE ON %I.networks
                    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
            ', v_schema, v_schema);

            EXECUTE format('
                DROP TRIGGER IF EXISTS update_asset_types_updated_at ON %I.asset_types;
                CREATE TRIGGER update_asset_types_updated_at
                    BEFORE UPDATE ON %I.asset_types
                    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
            ', v_schema, v_schema);

            EXECUTE format('
                DROP TRIGGER IF EXISTS update_packages_updated_at ON %I.packages;
                CREATE TRIGGER update_packages_updated_at
                    BEFORE UPDATE ON %I.packages
                    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
            ', v_schema, v_schema);

            -- =================================================================
            -- GRANTS
            -- =================================================================
            EXECUTE format('GRANT ALL ON %I.networks TO service_role', v_schema);
            EXECUTE format('GRANT ALL ON %I.asset_types TO service_role', v_schema);
            EXECUTE format('GRANT ALL ON %I.packages TO service_role', v_schema);
            EXECUTE format('GRANT ALL ON %I.package_items TO service_role', v_schema);
            EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO service_role', v_schema);

            RAISE NOTICE 'Updated schema % with networks, asset_types, packages', v_schema;
        ELSE
            RAISE NOTICE 'Schema % does not exist, skipping', v_schema;
        END IF;
    END LOOP;
END $$;

-- =============================================================================
-- PART 2: MODIFY proposal_locations TO SUPPORT ITEM TYPES
-- =============================================================================

DO $$
BEGIN
    -- Add item_type column if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'proposal_locations'
        AND column_name = 'item_type'
    ) THEN
        ALTER TABLE public.proposal_locations
        ADD COLUMN item_type TEXT DEFAULT 'asset' CHECK (item_type IN ('network', 'asset', 'package'));
        RAISE NOTICE 'Added item_type to proposal_locations';
    END IF;

    -- Add network_id column if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'proposal_locations'
        AND column_name = 'network_id'
    ) THEN
        ALTER TABLE public.proposal_locations ADD COLUMN network_id BIGINT;
        RAISE NOTICE 'Added network_id to proposal_locations';
    END IF;

    -- Add package_id column if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'proposal_locations'
        AND column_name = 'package_id'
    ) THEN
        ALTER TABLE public.proposal_locations ADD COLUMN package_id BIGINT;
        RAISE NOTICE 'Added package_id to proposal_locations';
    END IF;
END $$;

-- =============================================================================
-- PART 3: CROSS-SCHEMA VIEWS
-- =============================================================================

-- All networks across all companies
CREATE OR REPLACE VIEW public.all_networks AS
SELECT 'backlite_dubai' as company_code, n.* FROM backlite_dubai.networks n
UNION ALL
SELECT 'backlite_uk' as company_code, n.* FROM backlite_uk.networks n
UNION ALL
SELECT 'backlite_abudhabi' as company_code, n.* FROM backlite_abudhabi.networks n
UNION ALL
SELECT 'viola' as company_code, n.* FROM viola.networks n;

-- All asset types across all companies
CREATE OR REPLACE VIEW public.all_asset_types AS
SELECT 'backlite_dubai' as company_code, t.* FROM backlite_dubai.asset_types t
UNION ALL
SELECT 'backlite_uk' as company_code, t.* FROM backlite_uk.asset_types t
UNION ALL
SELECT 'backlite_abudhabi' as company_code, t.* FROM backlite_abudhabi.asset_types t
UNION ALL
SELECT 'viola' as company_code, t.* FROM viola.asset_types t;

-- All packages across all companies
CREATE OR REPLACE VIEW public.all_packages AS
SELECT 'backlite_dubai' as company_code, p.* FROM backlite_dubai.packages p
UNION ALL
SELECT 'backlite_uk' as company_code, p.* FROM backlite_uk.packages p
UNION ALL
SELECT 'backlite_abudhabi' as company_code, p.* FROM backlite_abudhabi.packages p
UNION ALL
SELECT 'viola' as company_code, p.* FROM viola.packages p;

-- =============================================================================
-- PART 4: HELPER FUNCTIONS
-- =============================================================================

-- Get all locations in a network
CREATE OR REPLACE FUNCTION public.get_network_locations(
    p_company_code TEXT,
    p_network_id BIGINT
)
RETURNS TABLE(
    location_id BIGINT,
    location_key TEXT,
    display_name TEXT,
    type_id BIGINT,
    type_name TEXT
) AS $$
BEGIN
    RETURN QUERY EXECUTE format('
        SELECT
            l.id as location_id,
            l.location_key,
            l.display_name,
            l.type_id,
            t.name as type_name
        FROM %I.locations l
        LEFT JOIN %I.asset_types t ON l.type_id = t.id
        WHERE l.network_id = $1
        AND l.is_active = true
        ORDER BY t.name, l.display_name
    ', p_company_code, p_company_code)
    USING p_network_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- Expand a package to all its locations
CREATE OR REPLACE FUNCTION public.expand_package_to_locations(
    p_company_code TEXT,
    p_package_id BIGINT
)
RETURNS TABLE(
    location_id BIGINT,
    location_key TEXT,
    display_name TEXT,
    item_type TEXT,
    source_network_id BIGINT
) AS $$
BEGIN
    RETURN QUERY EXECUTE format('
        -- Direct asset items
        SELECT
            l.id as location_id,
            l.location_key,
            l.display_name,
            ''asset''::TEXT as item_type,
            NULL::BIGINT as source_network_id
        FROM %I.package_items pi
        JOIN %I.locations l ON pi.location_id = l.id
        WHERE pi.package_id = $1
        AND pi.item_type = ''asset''

        UNION ALL

        -- Network items (expand to all locations in network)
        SELECT
            l.id as location_id,
            l.location_key,
            l.display_name,
            ''network''::TEXT as item_type,
            pi.network_id as source_network_id
        FROM %I.package_items pi
        JOIN %I.locations l ON l.network_id = pi.network_id
        WHERE pi.package_id = $1
        AND pi.item_type = ''network''
        AND l.is_active = true
    ', p_company_code, p_company_code, p_company_code, p_company_code)
    USING p_package_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- DONE!
-- =============================================================================
--
-- NEW TABLES (per company schema):
--   {company}.networks - Network groupings
--   {company}.asset_types - Asset type categories within networks
--   {company}.packages - Company-specific bundles
--   {company}.package_items - Package contents
--
-- MODIFIED TABLES:
--   {company}.locations - Added network_id, type_id columns
--   public.proposal_locations - Added item_type, network_id, package_id columns
--
-- NEW VIEWS:
--   public.all_networks - All networks across companies
--   public.all_asset_types - All asset types across companies
--   public.all_packages - All packages across companies
--
-- NEW FUNCTIONS:
--   public.get_network_locations(company, network_id)
--   public.expand_package_to_locations(company, package_id)
--
-- =============================================================================
