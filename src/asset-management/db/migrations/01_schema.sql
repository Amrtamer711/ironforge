-- =============================================================================
-- ASSET MANAGEMENT - MULTI-SCHEMA ARCHITECTURE
-- =============================================================================
-- Mirrors Sales-Module's multi-schema design for consistency.
--
-- ARCHITECTURE:
-- - public schema: Companies reference table, cross-company views
-- - Per-company schemas: Company-specific asset inventory
--
-- Company Schemas (isolated inventory):
--   backlite_dubai  - Backlite Dubai assets
--   backlite_uk     - Backlite UK assets
--   backlite_abudhabi - Backlite Abu Dhabi assets
--   viola           - Viola assets
--
-- Public Schema (cross-company):
--   companies - references the UI Supabase companies or maintains own
--   all_assets - unified view across all companies
-- =============================================================================

-- =============================================================================
-- PART 1: PUBLIC SCHEMA - COMPANIES REFERENCE
-- =============================================================================

-- Companies reference table (can sync from UI Supabase or maintain separately)
CREATE TABLE IF NOT EXISTS public.companies (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,           -- Schema name: 'backlite_dubai'
    name TEXT NOT NULL,                   -- Display: 'Backlite Dubai'
    parent_id BIGINT REFERENCES public.companies(id),
    country TEXT,
    currency TEXT DEFAULT 'AED',
    timezone TEXT DEFAULT 'Asia/Dubai',
    is_group BOOLEAN DEFAULT false,       -- True for MMG, Backlite (grouping only)
    is_active BOOLEAN DEFAULT true,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_code ON public.companies(code);
CREATE INDEX IF NOT EXISTS idx_companies_parent ON public.companies(parent_id);

-- Seed companies
INSERT INTO public.companies (id, code, name, parent_id, country, currency, is_group, config) VALUES
    (1, 'mmg', 'MMG', NULL, NULL, 'AED', true, '{"description": "Parent company - no data schema"}'),
    (2, 'backlite', 'Backlite', 1, NULL, 'AED', true, '{"description": "Backlite group - no data schema"}'),
    (3, 'backlite_dubai', 'Backlite Dubai', 2, 'UAE', 'AED', false, '{"region": "Dubai"}'),
    (4, 'backlite_uk', 'Backlite UK', 2, 'UK', 'GBP', false, '{"region": "United Kingdom"}'),
    (5, 'backlite_abudhabi', 'Backlite Abu Dhabi', 2, 'UAE', 'AED', false, '{"region": "Abu Dhabi"}'),
    (6, 'viola', 'Viola', 1, 'UAE', 'AED', false, '{"description": "Viola outdoor"}')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    parent_id = EXCLUDED.parent_id,
    country = EXCLUDED.country,
    currency = EXCLUDED.currency,
    is_group = EXCLUDED.is_group,
    config = EXCLUDED.config,
    updated_at = NOW();

-- =============================================================================
-- PART 2: HELPER FUNCTIONS (in public schema)
-- =============================================================================

-- Get company and all its children (for MMG/Backlite group access)
CREATE OR REPLACE FUNCTION public.get_company_and_children(p_company_id BIGINT)
RETURNS TABLE(company_id BIGINT, company_code TEXT) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE company_tree AS (
        SELECT c.id, c.code FROM public.companies c WHERE c.id = p_company_id
        UNION
        SELECT c.id, c.code FROM public.companies c
        INNER JOIN company_tree ct ON c.parent_id = ct.id
    )
    SELECT ct.id, ct.code FROM company_tree ct;
END;
$$ LANGUAGE plpgsql STABLE;

-- Get schemas user can access based on company assignments
CREATE OR REPLACE FUNCTION public.get_accessible_schemas(p_company_ids BIGINT[])
RETURNS TABLE(schema_name TEXT) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE all_companies AS (
        -- Start with assigned companies
        SELECT c.id, c.code, c.is_group
        FROM public.companies c
        WHERE c.id = ANY(p_company_ids)

        UNION

        -- Add children of group companies
        SELECT c.id, c.code, c.is_group
        FROM public.companies c
        INNER JOIN all_companies ac ON c.parent_id = ac.id
    )
    -- Return only non-group companies (those with actual data schemas)
    SELECT ac.code FROM all_companies ac WHERE ac.is_group = false;
END;
$$ LANGUAGE plpgsql STABLE;

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- PART 3: COMPANY SCHEMA TEMPLATE
-- =============================================================================
-- This function creates asset tables for a company schema

CREATE OR REPLACE FUNCTION public.create_company_asset_schema(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
BEGIN
    -- Create schema if not exists
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema);

    -- =========================================================================
    -- NETWORKS (Company-specific groupings - SELLABLE as a whole)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.networks (
            id BIGSERIAL PRIMARY KEY,
            network_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,

            -- Network-level attributes (inherited by child assets)
            series TEXT,
            sov_percent DECIMAL(5,2),
            upload_fee DECIMAL(10,2),
            spot_duration INTEGER,
            loop_duration INTEGER,
            number_of_faces INTEGER,

            template_path TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_key ON %I.networks(network_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_active ON %I.networks(is_active)', v_schema);

    -- =========================================================================
    -- ASSET TYPES (Categories within networks - NOT sellable)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.asset_types (
            id BIGSERIAL PRIMARY KEY,
            network_id BIGINT NOT NULL REFERENCES %I.networks(id) ON DELETE CASCADE,
            type_key TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            display_type TEXT NOT NULL CHECK (display_type IN (''digital'', ''static'')),
            height TEXT,
            width TEXT,
            specs JSONB DEFAULT ''{}'',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            CONSTRAINT asset_types_unique UNIQUE (network_id, type_key)
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_asset_types_network ON %I.asset_types(network_id)', v_schema);

    -- =========================================================================
    -- NETWORK ASSETS (Assets within networks)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.network_assets (
            id BIGSERIAL PRIMARY KEY,
            asset_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,

            network_id BIGINT NOT NULL REFERENCES %I.networks(id) ON DELETE CASCADE,
            type_id BIGINT NOT NULL REFERENCES %I.asset_types(id) ON DELETE CASCADE,

            -- Location info
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
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_network_assets_key ON %I.network_assets(asset_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_network_assets_network ON %I.network_assets(network_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_network_assets_type ON %I.network_assets(type_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_network_assets_active ON %I.network_assets(is_active)', v_schema);

    -- =========================================================================
    -- STANDALONE ASSETS (Independent assets)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.standalone_assets (
            id BIGSERIAL PRIMARY KEY,
            asset_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,

            -- All attributes stored directly
            display_type TEXT NOT NULL CHECK (display_type IN (''digital'', ''static'')),
            series TEXT,
            height TEXT,
            width TEXT,
            number_of_faces INTEGER DEFAULT 1,
            spot_duration INTEGER,
            loop_duration INTEGER,
            sov_percent DECIMAL(5,2),
            upload_fee DECIMAL(10,2),

            -- Location info
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
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_key ON %I.standalone_assets(asset_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_active ON %I.standalone_assets(is_active)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_standalone_assets_city ON %I.standalone_assets(city)', v_schema);

    -- =========================================================================
    -- PACKAGES (Sellable bundles)
    -- =========================================================================
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

    -- =========================================================================
    -- PACKAGE ITEMS (Junction table)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.package_items (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES %I.packages(id) ON DELETE CASCADE,
            item_type TEXT NOT NULL CHECK (item_type IN (''network'', ''standalone'')),
            network_id BIGINT REFERENCES %I.networks(id) ON DELETE CASCADE,
            standalone_asset_id BIGINT REFERENCES %I.standalone_assets(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT package_items_type_check CHECK (
                (item_type = ''network'' AND network_id IS NOT NULL AND standalone_asset_id IS NULL) OR
                (item_type = ''standalone'' AND standalone_asset_id IS NOT NULL AND network_id IS NULL)
            )
        )', v_schema, v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_package_items_package ON %I.package_items(package_id)', v_schema);

    -- =========================================================================
    -- ASSET PHOTOS (Real billboard photos)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.asset_photos (
            id BIGSERIAL PRIMARY KEY,
            network_asset_id BIGINT REFERENCES %I.network_assets(id) ON DELETE CASCADE,
            standalone_asset_id BIGINT REFERENCES %I.standalone_assets(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size BIGINT,
            width INTEGER,
            height INTEGER,
            is_primary BOOLEAN DEFAULT false,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT,
            CONSTRAINT asset_photos_one_parent CHECK (
                (network_asset_id IS NOT NULL AND standalone_asset_id IS NULL) OR
                (standalone_asset_id IS NOT NULL AND network_asset_id IS NULL)
            )
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_asset_photos_network_asset ON %I.asset_photos(network_asset_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_asset_photos_standalone ON %I.asset_photos(standalone_asset_id)', v_schema);

    -- =========================================================================
    -- ASSET OCCUPATIONS (Booking/availability)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.asset_occupations (
            id BIGSERIAL PRIMARY KEY,
            network_asset_id BIGINT REFERENCES %I.network_assets(id) ON DELETE CASCADE,
            standalone_asset_id BIGINT REFERENCES %I.standalone_assets(id) ON DELETE CASCADE,

            -- References to sales-module
            bo_id BIGINT,
            proposal_id BIGINT,

            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            client_name TEXT,
            campaign_name TEXT,
            brand TEXT,
            status TEXT NOT NULL DEFAULT ''tentative'' CHECK (status IN (
                ''tentative'', ''pending'', ''confirmed'', ''live'', ''completed'', ''cancelled''
            )),
            net_rate DECIMAL(15,2),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT,
            CONSTRAINT occupations_one_parent CHECK (
                (network_asset_id IS NOT NULL AND standalone_asset_id IS NULL) OR
                (standalone_asset_id IS NOT NULL AND network_asset_id IS NULL)
            )
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_dates ON %I.asset_occupations(start_date, end_date)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_status ON %I.asset_occupations(status)', v_schema);

    -- =========================================================================
    -- UNIFIED LOCATIONS VIEW (sellable entities: networks + standalone_assets)
    -- =========================================================================
    -- Networks and standalone assets are both sellable as complete units
    -- Network assets are NOT included here (they are components of networks)
    EXECUTE format('
        CREATE OR REPLACE VIEW %I.locations AS
        -- Networks (sellable as complete units)
        SELECT
            n.id,
            n.network_key AS location_key,
            n.name AS display_name,
            NULL::TEXT AS display_type,      -- Networks don''t have a single display_type
            n.id AS network_id,               -- Self-reference for network entities
            NULL::BIGINT AS type_id,          -- Networks don''t belong to types
            n.series,
            NULL::TEXT AS height,             -- Networks don''t have single height
            NULL::TEXT AS width,              -- Networks don''t have single width
            n.number_of_faces,
            n.spot_duration,
            n.loop_duration,
            n.sov_percent,
            n.upload_fee,
            NULL::TEXT AS city,               -- Networks span multiple locations
            NULL::TEXT AS area,               -- Networks span multiple locations
            NULL::TEXT AS address,            -- Networks don''t have single address
            NULL::DECIMAL(10,7) AS gps_lat,   -- Networks don''t have single GPS
            NULL::DECIMAL(10,7) AS gps_lng,   -- Networks don''t have single GPS
            n.template_path,
            n.is_active,
            n.created_at,
            n.updated_at,
            n.created_by,
            n.notes,
            ''network''::TEXT AS asset_source
        FROM %I.networks n

        UNION ALL

        -- Standalone assets (sellable individually)
        SELECT
            sa.id,
            sa.asset_key AS location_key,
            sa.display_name,
            sa.display_type,
            NULL::BIGINT AS network_id,       -- Standalones don''t belong to networks
            NULL::BIGINT AS type_id,          -- Standalones don''t have types
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

    -- =========================================================================
    -- TRIGGERS
    -- =========================================================================
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
        DROP TRIGGER IF EXISTS update_network_assets_updated_at ON %I.network_assets;
        CREATE TRIGGER update_network_assets_updated_at
            BEFORE UPDATE ON %I.network_assets
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_standalone_assets_updated_at ON %I.standalone_assets;
        CREATE TRIGGER update_standalone_assets_updated_at
            BEFORE UPDATE ON %I.standalone_assets
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_packages_updated_at ON %I.packages;
        CREATE TRIGGER update_packages_updated_at
            BEFORE UPDATE ON %I.packages
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_occupations_updated_at ON %I.asset_occupations;
        CREATE TRIGGER update_occupations_updated_at
            BEFORE UPDATE ON %I.asset_occupations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    -- =========================================================================
    -- ROW LEVEL SECURITY
    -- =========================================================================
    EXECUTE format('ALTER TABLE %I.networks ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.asset_types ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.network_assets ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.standalone_assets ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.packages ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.package_items ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.asset_photos ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.asset_occupations ENABLE ROW LEVEL SECURITY', v_schema);

    -- Service role full access policies
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.networks', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.asset_types', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.network_assets', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.standalone_assets', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.packages', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.package_items', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.asset_photos', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.asset_occupations', v_schema);

    EXECUTE format('CREATE POLICY "Service role full access" ON %I.networks FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.asset_types FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.network_assets FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.standalone_assets FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.packages FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.package_items FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.asset_photos FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.asset_occupations FOR ALL USING (true)', v_schema);

    -- =========================================================================
    -- GRANTS
    -- =========================================================================
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO service_role', v_schema);

    RAISE NOTICE 'Created asset management schema % with networks, assets, and packages', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- PART 4: CREATE COMPANY SCHEMAS
-- =============================================================================

SELECT public.create_company_asset_schema('backlite_dubai');
SELECT public.create_company_asset_schema('backlite_uk');
SELECT public.create_company_asset_schema('backlite_abudhabi');
SELECT public.create_company_asset_schema('viola');

-- =============================================================================
-- PART 5: PUBLIC SCHEMA TRIGGERS & RLS
-- =============================================================================

-- Trigger for companies updated_at
DROP TRIGGER IF EXISTS update_companies_updated_at ON public.companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON public.companies
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Enable RLS on public tables
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;

-- Service role full access policies for public tables
DROP POLICY IF EXISTS "Service role full access" ON public.companies;
CREATE POLICY "Service role full access" ON public.companies FOR ALL USING (true);

-- Grants for public schema
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- PART 6: CROSS-SCHEMA VIEWS
-- =============================================================================

-- All assets across all companies (for MMG users or aggregated views)
CREATE OR REPLACE VIEW public.all_standalone_assets AS
SELECT 'backlite_dubai' as company_code, a.* FROM backlite_dubai.standalone_assets a
UNION ALL
SELECT 'backlite_uk' as company_code, a.* FROM backlite_uk.standalone_assets a
UNION ALL
SELECT 'backlite_abudhabi' as company_code, a.* FROM backlite_abudhabi.standalone_assets a
UNION ALL
SELECT 'viola' as company_code, a.* FROM viola.standalone_assets a;

-- All networks across all companies
CREATE OR REPLACE VIEW public.all_networks AS
SELECT 'backlite_dubai' as company_code, n.* FROM backlite_dubai.networks n
UNION ALL
SELECT 'backlite_uk' as company_code, n.* FROM backlite_uk.networks n
UNION ALL
SELECT 'backlite_abudhabi' as company_code, n.* FROM backlite_abudhabi.networks n
UNION ALL
SELECT 'viola' as company_code, n.* FROM viola.networks n;

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
-- DONE! Multi-schema architecture is ready.
-- =============================================================================
