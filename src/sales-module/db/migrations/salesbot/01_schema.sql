-- =============================================================================
-- SALES BOT SUPABASE SCHEMA - HYBRID MULTI-SCHEMA ARCHITECTURE
-- =============================================================================
-- Run this in: Sales-Bot-Dev and Sales-Bot-Prod Supabase SQL Editor
--
-- ARCHITECTURE:
-- - public schema: Cross-company data (proposals, BOs, AI costs, etc.)
-- - Per-company schemas: Company-specific inventory (locations, mockup frames)
--
-- WHY THIS DESIGN:
-- - Proposals can include locations from MULTIPLE companies
-- - Booking orders can span MULTIPLE companies
-- - AI costs are tracked by USER (users can belong to multiple companies)
-- - But locations and mockup frames are owned by a SINGLE company
--
-- Company Schemas (isolated inventory):
--   backlite_dubai  - Backlite Dubai locations & mockups
--   backlite_uk     - Backlite UK locations & mockups
--   backlite_abudhabi - Backlite Abu Dhabi locations & mockups
--   viola           - Viola locations & mockups
--
-- Public Schema (cross-company):
--   companies, chat_sessions, proposals_log, proposal_locations,
--   booking_orders, bo_locations, bo_approval_workflows, ai_costs,
--   documents, mockup_files, proposal_files
--
-- =============================================================================

-- =============================================================================
-- PART 1: PUBLIC SCHEMA - CROSS-COMPANY DATA
-- =============================================================================

-- Companies reference table (source of truth for company info)
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

-- Chat sessions (global per user, not company-specific)
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON public.chat_sessions(user_id);

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
-- PROPOSALS LOG (Public - can include locations from multiple companies)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.proposals_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    client_name TEXT NOT NULL,
    date_generated TIMESTAMPTZ DEFAULT NOW(),
    package_type TEXT NOT NULL CHECK (package_type IN ('separate', 'combined')),
    total_amount TEXT,                     -- Legacy: formatted display text "AED 446,796"
    total_amount_value DECIMAL(15,2),      -- Normalized: numeric sum
    currency TEXT DEFAULT 'AED',
    locations TEXT,                        -- Legacy: comma-separated location names
    proposal_data JSONB,                   -- Full proposal details
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proposals_user ON public.proposals_log(user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_client ON public.proposals_log(client_name);
CREATE INDEX IF NOT EXISTS idx_proposals_date ON public.proposals_log(date_generated);

-- =============================================================================
-- PROPOSAL LOCATIONS (Public - links proposals to locations across companies)
-- =============================================================================
-- NOTE: No unique constraint - same location can appear multiple times per proposal
-- (e.g., same location with different options/finishes)
-- location_company tracks which company schema the location belongs to
CREATE TABLE IF NOT EXISTS public.proposal_locations (
    id BIGSERIAL PRIMARY KEY,
    proposal_id BIGINT NOT NULL REFERENCES public.proposals_log(id) ON DELETE CASCADE,
    location_key TEXT NOT NULL,
    location_company TEXT,                 -- Company schema that owns this location
    location_display_name TEXT,
    start_date DATE,
    duration_weeks INTEGER,
    net_rate DECIMAL(15,2),
    upload_fee DECIMAL(10,2),
    production_fee DECIMAL(10,2)
);

CREATE INDEX IF NOT EXISTS idx_proposal_locations_proposal ON public.proposal_locations(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_locations_location ON public.proposal_locations(location_key);
CREATE INDEX IF NOT EXISTS idx_proposal_locations_company ON public.proposal_locations(location_company);

-- =============================================================================
-- BOOKING ORDERS (Public - can span multiple companies)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.booking_orders (
    id BIGSERIAL PRIMARY KEY,
    bo_ref TEXT NOT NULL UNIQUE,
    user_id TEXT,
    company TEXT NOT NULL,                 -- Primary company (for BO numbering)
    original_file_path TEXT NOT NULL,
    original_file_type TEXT NOT NULL,
    original_file_size BIGINT,
    original_filename TEXT,
    parsed_excel_path TEXT,
    bo_number TEXT,
    bo_date TEXT,
    client TEXT,
    agency TEXT,
    brand_campaign TEXT,
    category TEXT,
    asset TEXT,
    net_pre_vat DECIMAL(15,2),
    vat_value DECIMAL(15,2),
    gross_amount DECIMAL(15,2),
    sla_pct DECIMAL(5,2),
    payment_terms TEXT,
    sales_person TEXT,
    commission_pct DECIMAL(5,2),
    notes TEXT,
    locations_json JSONB,
    extraction_method TEXT,
    extraction_confidence TEXT,
    warnings_json JSONB,
    missing_fields_json JSONB,
    vat_calc DECIMAL(15,2),
    gross_calc DECIMAL(15,2),
    sla_deduction DECIMAL(15,2),
    net_excl_sla_calc DECIMAL(15,2),
    parsed_at TIMESTAMPTZ DEFAULT NOW(),
    parsed_by TEXT,
    source_classification TEXT,
    classification_confidence TEXT,
    needs_review BOOLEAN DEFAULT false,
    search_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_booking_orders_bo_ref ON public.booking_orders(bo_ref);
CREATE INDEX IF NOT EXISTS idx_booking_orders_client ON public.booking_orders(client);
CREATE INDEX IF NOT EXISTS idx_booking_orders_user ON public.booking_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_booking_orders_parsed ON public.booking_orders(parsed_at);
CREATE INDEX IF NOT EXISTS idx_booking_orders_company ON public.booking_orders(company);

-- =============================================================================
-- BO LOCATIONS (Public - links BOs to locations across companies)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.bo_locations (
    id BIGSERIAL PRIMARY KEY,
    bo_id BIGINT NOT NULL REFERENCES public.booking_orders(id) ON DELETE CASCADE,
    location_key TEXT,
    location_company TEXT,                 -- Company schema that owns this location
    start_date DATE,
    end_date DATE,
    duration_weeks INTEGER,
    net_rate DECIMAL(15,2),
    raw_location_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_bo_locations_bo ON public.bo_locations(bo_id);
CREATE INDEX IF NOT EXISTS idx_bo_locations_location ON public.bo_locations(location_key);
CREATE INDEX IF NOT EXISTS idx_bo_locations_company ON public.bo_locations(location_company);

-- =============================================================================
-- BO APPROVAL WORKFLOWS (Public - workflows are cross-company)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.bo_approval_workflows (
    workflow_id TEXT PRIMARY KEY,
    bo_id BIGINT REFERENCES public.booking_orders(id) ON DELETE SET NULL,
    workflow_data JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'coordinator_approved', 'coordinator_rejected',
        'hos_approved', 'hos_rejected', 'cancelled', 'completed'
    )),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bo_workflows_status ON public.bo_approval_workflows(status);
CREATE INDEX IF NOT EXISTS idx_bo_workflows_bo ON public.bo_approval_workflows(bo_id);

-- =============================================================================
-- AI COSTS (Public - tracked by user, users can belong to multiple companies)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.ai_costs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    call_type TEXT NOT NULL CHECK (call_type IN (
        'classification', 'parsing', 'coordinator_thread', 'main_llm',
        'mockup_analysis', 'image_generation', 'bo_edit', 'other'
    )),
    workflow TEXT CHECK (workflow IN (
        'mockup_upload', 'mockup_ai', 'bo_parsing', 'bo_editing',
        'bo_revision', 'proposal_generation', 'general_chat', 'location_management'
    ) OR workflow IS NULL),
    model TEXT NOT NULL,
    user_id TEXT,
    context TEXT,
    input_tokens INTEGER,
    cached_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER,
    reasoning_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER,
    input_cost DECIMAL(10,6),
    output_cost DECIMAL(10,6),
    reasoning_cost DECIMAL(10,6) DEFAULT 0,
    total_cost DECIMAL(10,6),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_ai_costs_timestamp ON public.ai_costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_costs_call_type ON public.ai_costs(call_type);
CREATE INDEX IF NOT EXISTS idx_ai_costs_user ON public.ai_costs(user_id);

-- =============================================================================
-- DOCUMENTS (Public - documents can be shared across companies)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.documents (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size BIGINT,
    file_extension TEXT,
    storage_provider TEXT NOT NULL DEFAULT 'supabase',
    storage_bucket TEXT NOT NULL DEFAULT 'uploads',
    storage_key TEXT NOT NULL,
    document_type TEXT CHECK (document_type IN (
        'bo_pdf', 'bo_image', 'bo_excel', 'creative', 'contract', 'invoice', 'other'
    )),
    bo_id BIGINT REFERENCES public.booking_orders(id) ON DELETE SET NULL,
    proposal_id BIGINT REFERENCES public.proposals_log(id) ON DELETE SET NULL,
    is_processed BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    file_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_documents_file_id ON public.documents(file_id);
CREATE INDEX IF NOT EXISTS idx_documents_user ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON public.documents(document_type);

-- =============================================================================
-- MOCKUP FILES (Public - generated mockups, links to company-specific locations)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.mockup_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    location_key TEXT NOT NULL,
    location_company TEXT,                 -- Company schema that owns this location
    original_filename TEXT,
    file_size BIGINT,
    storage_provider TEXT NOT NULL DEFAULT 'supabase',
    storage_bucket TEXT NOT NULL DEFAULT 'mockups',
    storage_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL DEFAULT 'day',
    finish TEXT NOT NULL DEFAULT 'gold',
    photo_filename TEXT,
    creative_type TEXT CHECK (creative_type IN ('uploaded', 'ai_generated')),
    creative_file_id TEXT,
    ai_prompt TEXT,
    output_format TEXT DEFAULT 'png',
    width INTEGER,
    height INTEGER,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    file_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_mockup_files_file_id ON public.mockup_files(file_id);
CREATE INDEX IF NOT EXISTS idx_mockup_files_location ON public.mockup_files(location_key);
CREATE INDEX IF NOT EXISTS idx_mockup_files_company ON public.mockup_files(location_company);

-- =============================================================================
-- PROPOSAL FILES (Public - generated proposals)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.proposal_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    proposal_id BIGINT REFERENCES public.proposals_log(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    file_size BIGINT,
    storage_provider TEXT NOT NULL DEFAULT 'supabase',
    storage_bucket TEXT NOT NULL DEFAULT 'proposals',
    storage_key TEXT NOT NULL,
    client_name TEXT,
    package_type TEXT,
    location_count INTEGER,
    version INTEGER DEFAULT 1,
    is_latest BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    file_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_proposal_files_file_id ON public.proposal_files(file_id);
CREATE INDEX IF NOT EXISTS idx_proposal_files_proposal ON public.proposal_files(proposal_id);

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
-- PART 3: COMPANY SCHEMA TEMPLATE (Location-specific data only)
-- =============================================================================
-- This function creates location and mockup tables for a company schema
-- Call: SELECT public.create_company_schema('backlite_dubai');

CREATE OR REPLACE FUNCTION public.create_company_schema(p_company_code TEXT)
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
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_key ON %I.networks(network_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_networks_active ON %I.networks(is_active)', v_schema);

    -- =========================================================================
    -- ASSET TYPES (Organizational categories within networks - NOT sellable)
    -- =========================================================================
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

    -- =========================================================================
    -- LOCATIONS INVENTORY (Company-specific - SELLABLE individually)
    -- Can be standalone (no network) or part of a network/type hierarchy
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.locations (
            id BIGSERIAL PRIMARY KEY,
            location_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            display_type TEXT NOT NULL CHECK (display_type IN (''digital'', ''static'')),
            network_id BIGINT REFERENCES %I.networks(id) ON DELETE SET NULL,
            type_id BIGINT REFERENCES %I.asset_types(id) ON DELETE SET NULL,
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
            gps_lat DECIMAL(10,7),
            gps_lng DECIMAL(10,7),
            template_path TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_key ON %I.locations(location_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_type ON %I.locations(display_type)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_series ON %I.locations(series)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_active ON %I.locations(is_active)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_network ON %I.locations(network_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_asset_type ON %I.locations(type_id)', v_schema);

    -- =========================================================================
    -- MOCKUP FRAMES (Company-specific - tied to company's locations)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.mockup_frames (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE CASCADE,
            location_key TEXT NOT NULL,
            time_of_day TEXT NOT NULL DEFAULT ''day'' CHECK (time_of_day IN (''day'', ''night'')),
            finish TEXT NOT NULL DEFAULT ''gold'' CHECK (finish IN (''gold'', ''silver'', ''black'')),
            photo_filename TEXT NOT NULL,
            frames_data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            config_json JSONB,
            CONSTRAINT mockup_frames_unique UNIQUE (location_key, time_of_day, finish, photo_filename)
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_frames_location ON %I.mockup_frames(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_frames_location_key ON %I.mockup_frames(location_key)', v_schema);

    -- =========================================================================
    -- MOCKUP USAGE (Company-specific - analytics per company)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.mockup_usage (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE SET NULL,
            location_key TEXT NOT NULL,
            user_id TEXT,
            generated_at TIMESTAMPTZ DEFAULT NOW(),
            time_of_day TEXT NOT NULL,
            finish TEXT NOT NULL,
            photo_used TEXT NOT NULL,
            creative_type TEXT NOT NULL CHECK (creative_type IN (''uploaded'', ''ai_generated'')),
            ai_prompt TEXT,
            template_selected BOOLEAN DEFAULT false,
            success BOOLEAN DEFAULT true,
            user_ip TEXT,
            metadata_json JSONB
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_location ON %I.mockup_usage(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_user ON %I.mockup_usage(user_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_date ON %I.mockup_usage(generated_at)', v_schema);

    -- =========================================================================
    -- LOCATION PHOTOS (Company-specific - billboard photos)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.location_photos (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE CASCADE,
            location_key TEXT NOT NULL,
            time_of_day TEXT NOT NULL DEFAULT ''day'' CHECK (time_of_day IN (''day'', ''night'', ''all'')),
            finish TEXT NOT NULL DEFAULT ''gold'' CHECK (finish IN (''gold'', ''silver'', ''black'', ''all'')),
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size BIGINT,
            width INTEGER,
            height INTEGER,
            is_active BOOLEAN DEFAULT true,
            is_default BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT,
            CONSTRAINT location_photos_unique UNIQUE (location_key, time_of_day, finish, filename)
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_location_photos_location ON %I.location_photos(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_location_photos_key ON %I.location_photos(location_key)', v_schema);

    -- =========================================================================
    -- RATE CARDS (Company-specific - pricing per company)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.rate_cards (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT NOT NULL REFERENCES %I.locations(id) ON DELETE CASCADE,
            valid_from DATE NOT NULL,
            valid_to DATE,
            weekly_rate DECIMAL(15,2) NOT NULL,
            monthly_rate DECIMAL(15,2),
            upload_fee DECIMAL(10,2),
            production_fee_estimate DECIMAL(10,2),
            currency TEXT DEFAULT ''AED'',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT,
            CONSTRAINT rate_cards_unique_period UNIQUE (location_id, valid_from)
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_rate_cards_location ON %I.rate_cards(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_rate_cards_valid ON %I.rate_cards(valid_from, valid_to)', v_schema);

    -- =========================================================================
    -- LOCATION OCCUPATIONS (Company-specific - availability per company)
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.location_occupations (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT NOT NULL REFERENCES %I.locations(id) ON DELETE CASCADE,
            bo_id BIGINT,                   -- References public.booking_orders
            proposal_id BIGINT,             -- References public.proposals_log
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
            notes TEXT
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_location ON %I.location_occupations(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_dates ON %I.location_occupations(start_date, end_date)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_status ON %I.location_occupations(status)', v_schema);

    -- =========================================================================
    -- PACKAGES (Company-specific bundles - SELLABLE)
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
    -- PACKAGE ITEMS (Junction table - networks or individual assets)
    -- =========================================================================
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
        DROP TRIGGER IF EXISTS update_locations_updated_at ON %I.locations;
        CREATE TRIGGER update_locations_updated_at
            BEFORE UPDATE ON %I.locations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_occupations_updated_at ON %I.location_occupations;
        CREATE TRIGGER update_occupations_updated_at
            BEFORE UPDATE ON %I.location_occupations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_packages_updated_at ON %I.packages;
        CREATE TRIGGER update_packages_updated_at
            BEFORE UPDATE ON %I.packages
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    -- =========================================================================
    -- ROW LEVEL SECURITY
    -- =========================================================================
    EXECUTE format('ALTER TABLE %I.networks ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.asset_types ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.locations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.mockup_frames ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.mockup_usage ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.location_photos ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.rate_cards ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.location_occupations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.packages ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.package_items ENABLE ROW LEVEL SECURITY', v_schema);

    -- Service role full access policies (drop first to avoid "already exists" error)
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.networks', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.asset_types', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.locations', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.mockup_frames', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.mockup_usage', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.location_photos', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.rate_cards', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.location_occupations', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.packages', v_schema);
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.package_items', v_schema);

    EXECUTE format('CREATE POLICY "Service role full access" ON %I.networks FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.asset_types FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.locations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_frames FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_usage FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.location_photos FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.rate_cards FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.location_occupations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.packages FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.package_items FOR ALL USING (true)', v_schema);

    -- =========================================================================
    -- GRANTS
    -- =========================================================================
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO service_role', v_schema);

    RAISE NOTICE 'Created schema % with networks, asset_types, locations, packages, and mockup tables', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- PART 4: CREATE COMPANY SCHEMAS
-- =============================================================================
-- Create schemas for each non-group company

SELECT public.create_company_schema('backlite_dubai');
SELECT public.create_company_schema('backlite_uk');
SELECT public.create_company_schema('backlite_abudhabi');
SELECT public.create_company_schema('viola');

-- =============================================================================
-- PART 5: PUBLIC SCHEMA TRIGGERS & RLS
-- =============================================================================

-- Trigger for chat_sessions updated_at
DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON public.chat_sessions;
CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON public.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Trigger for bo_approval_workflows updated_at
DROP TRIGGER IF EXISTS update_bo_workflows_updated_at ON public.bo_approval_workflows;
CREATE TRIGGER update_bo_workflows_updated_at
    BEFORE UPDATE ON public.bo_approval_workflows
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Enable RLS on public tables
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proposals_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proposal_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.booking_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bo_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bo_approval_workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_costs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mockup_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proposal_files ENABLE ROW LEVEL SECURITY;

-- Service role full access policies for public tables (drop first to avoid "already exists" error)
DROP POLICY IF EXISTS "Service role full access" ON public.companies;
DROP POLICY IF EXISTS "Service role full access" ON public.chat_sessions;
DROP POLICY IF EXISTS "Service role full access" ON public.proposals_log;
DROP POLICY IF EXISTS "Service role full access" ON public.proposal_locations;
DROP POLICY IF EXISTS "Service role full access" ON public.booking_orders;
DROP POLICY IF EXISTS "Service role full access" ON public.bo_locations;
DROP POLICY IF EXISTS "Service role full access" ON public.bo_approval_workflows;
DROP POLICY IF EXISTS "Service role full access" ON public.ai_costs;
DROP POLICY IF EXISTS "Service role full access" ON public.documents;
DROP POLICY IF EXISTS "Service role full access" ON public.mockup_files;
DROP POLICY IF EXISTS "Service role full access" ON public.proposal_files;

CREATE POLICY "Service role full access" ON public.companies FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.chat_sessions FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.proposals_log FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.proposal_locations FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.booking_orders FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.bo_locations FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.bo_approval_workflows FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.ai_costs FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.documents FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.mockup_files FOR ALL USING (true);
CREATE POLICY "Service role full access" ON public.proposal_files FOR ALL USING (true);

-- Grants for public schema
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- PART 6: CROSS-SCHEMA VIEWS (for unified access)
-- =============================================================================

-- All locations across all companies (for MMG users or aggregated views)
CREATE OR REPLACE VIEW public.all_locations AS
SELECT 'backlite_dubai' as company_code, l.* FROM backlite_dubai.locations l
UNION ALL
SELECT 'backlite_uk' as company_code, l.* FROM backlite_uk.locations l
UNION ALL
SELECT 'backlite_abudhabi' as company_code, l.* FROM backlite_abudhabi.locations l
UNION ALL
SELECT 'viola' as company_code, l.* FROM viola.locations l;

-- All mockup frames across all companies
CREATE OR REPLACE VIEW public.all_mockup_frames AS
SELECT 'backlite_dubai' as company_code, m.* FROM backlite_dubai.mockup_frames m
UNION ALL
SELECT 'backlite_uk' as company_code, m.* FROM backlite_uk.mockup_frames m
UNION ALL
SELECT 'backlite_abudhabi' as company_code, m.* FROM backlite_abudhabi.mockup_frames m
UNION ALL
SELECT 'viola' as company_code, m.* FROM viola.mockup_frames m;

-- All mockup usage across all companies
CREATE OR REPLACE VIEW public.all_mockup_usage AS
SELECT 'backlite_dubai' as company_code, u.* FROM backlite_dubai.mockup_usage u
UNION ALL
SELECT 'backlite_uk' as company_code, u.* FROM backlite_uk.mockup_usage u
UNION ALL
SELECT 'backlite_abudhabi' as company_code, u.* FROM backlite_abudhabi.mockup_usage u
UNION ALL
SELECT 'viola' as company_code, u.* FROM viola.mockup_usage u;

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
-- DONE! Hybrid multi-schema architecture is ready.
-- =============================================================================
--
-- SUMMARY:
-- --------
-- PUBLIC SCHEMA (cross-company data):
--   - proposals_log, proposal_locations
--   - booking_orders, bo_locations, bo_approval_workflows
--   - ai_costs
--   - documents, mockup_files, proposal_files
--   - chat_sessions, companies
--
-- COMPANY SCHEMAS (company-specific inventory):
--   - networks (sellable as a whole)
--   - asset_types (organizational, NOT sellable)
--   - locations (sellable individually, can be standalone or part of network)
--   - packages (sellable bundles of networks/assets)
--   - package_items (junction table for package contents)
--   - mockup_frames
--   - mockup_usage
--   - location_photos
--   - rate_cards
--   - location_occupations
--
-- CROSS-SCHEMA VIEWS:
--   - public.all_locations
--   - public.all_networks
--   - public.all_asset_types
--   - public.all_packages
--   - public.all_mockup_frames
--   - public.all_mockup_usage
--
-- HIERARCHY:
-- ----------
-- Network (sellable) -> Asset Type (organizational) -> Location (sellable)
-- Locations can also be standalone (no network/type)
-- Packages can include networks and/or individual assets
--
-- USAGE:
-- ------
-- 1. Query specific company's locations:
--    SELECT * FROM backlite_dubai.locations;
--
-- 2. Query all locations (MMG access):
--    SELECT * FROM public.all_locations;
--
-- 3. Create a proposal with locations from multiple companies:
--    INSERT INTO public.proposals_log (...) VALUES (...);
--    INSERT INTO public.proposal_locations (proposal_id, location_key, location_company, ...)
--    VALUES (1, 'dubai_gateway', 'backlite_dubai', ...),
--           (1, 'london_bridge', 'backlite_uk', ...);
--
-- 4. Get all locations in a network:
--    SELECT * FROM backlite_abudhabi.locations WHERE network_id = 1;
--
-- 5. Expand a package to all its locations:
--    SELECT * FROM backlite_dubai.package_items pi
--    JOIN backlite_dubai.locations l ON
--      (pi.item_type = 'asset' AND l.id = pi.location_id) OR
--      (pi.item_type = 'network' AND l.network_id = pi.network_id)
--    WHERE pi.package_id = 1;
--
-- =============================================================================
