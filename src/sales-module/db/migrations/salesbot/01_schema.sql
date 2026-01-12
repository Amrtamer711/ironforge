-- =============================================================================
-- SALES-MODULE SUPABASE SCHEMA
-- =============================================================================
-- Run this in: Sales-Module Supabase SQL Editor
--
-- ARCHITECTURE:
-- - public schema: Cross-company data (proposals, BOs, AI costs, documents)
-- - Per-company schemas: Company-specific analytics (mockup_usage only)
--
-- IMPORTANT: This service does NOT store inventory data!
-- - Locations, networks, mockup_frames are in ASSET-MANAGEMENT
-- - Sales-Module references them via location_key (TEXT)
--
-- Company Schemas (analytics only):
--   backlite_dubai.mockup_usage
--   backlite_uk.mockup_usage
--   backlite_abudhabi.mockup_usage
--   viola.mockup_usage
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

-- Companies reference table (mirrors Asset-Management for consistency)
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
-- NOTE: References Asset-Management locations via location_key (TEXT)
-- location_company tracks which company schema the location belongs to
CREATE TABLE IF NOT EXISTS public.proposal_locations (
    id BIGSERIAL PRIMARY KEY,
    proposal_id BIGINT NOT NULL REFERENCES public.proposals_log(id) ON DELETE CASCADE,
    location_key TEXT NOT NULL,            -- Reference to Asset-Management
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
-- NOTE: References Asset-Management locations via location_key (TEXT)
CREATE TABLE IF NOT EXISTS public.bo_locations (
    id BIGSERIAL PRIMARY KEY,
    bo_id BIGINT NOT NULL REFERENCES public.booking_orders(id) ON DELETE CASCADE,
    location_key TEXT,                     -- Reference to Asset-Management
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
    metadata_json JSONB,
    -- Thumbnail support (added in migration 05)
    thumbnail_key TEXT,
    thumbnail_generated_at TIMESTAMPTZ,
    image_width INTEGER,
    image_height INTEGER
);

CREATE INDEX IF NOT EXISTS idx_documents_file_id ON public.documents(file_id);
CREATE INDEX IF NOT EXISTS idx_documents_user ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON public.documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_thumbnail ON public.documents(thumbnail_key)
WHERE thumbnail_key IS NOT NULL;

-- =============================================================================
-- MOCKUP FILES (Public - generated mockups, references Asset-Management locations)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.mockup_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    location_key TEXT NOT NULL,            -- Reference to Asset-Management
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
-- PART 2: HELPER FUNCTIONS
-- =============================================================================

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
        SELECT c.id, c.code, c.is_group
        FROM public.companies c
        WHERE c.id = ANY(p_company_ids)
        UNION
        SELECT c.id, c.code, c.is_group
        FROM public.companies c
        INNER JOIN all_companies ac ON c.parent_id = ac.id
    )
    SELECT ac.code FROM all_companies ac WHERE ac.is_group = false;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- PART 3: COMPANY SCHEMA TEMPLATE (Analytics only - NO inventory!)
-- =============================================================================
-- This function creates ONLY the mockup_usage table for analytics
-- Location data is in Asset-Management, not here!

CREATE OR REPLACE FUNCTION public.create_company_schema(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
BEGIN
    -- Create schema if not exists
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema);

    -- =========================================================================
    -- MOCKUP USAGE (Company-specific analytics)
    -- =========================================================================
    -- Tracks mockup generation for analytics purposes
    -- References Asset-Management locations via location_key (TEXT)
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.mockup_usage (
            id BIGSERIAL PRIMARY KEY,
            location_key TEXT NOT NULL,        -- Reference to Asset-Management
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
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_location ON %I.mockup_usage(location_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_user ON %I.mockup_usage(user_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_usage_date ON %I.mockup_usage(generated_at)', v_schema);

    -- =========================================================================
    -- ROW LEVEL SECURITY
    -- =========================================================================
    EXECUTE format('ALTER TABLE %I.mockup_usage ENABLE ROW LEVEL SECURITY', v_schema);

    -- Service role full access
    EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON %I.mockup_usage', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_usage FOR ALL USING (true)', v_schema);

    -- =========================================================================
    -- GRANTS
    -- =========================================================================
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO service_role', v_schema);

    RAISE NOTICE 'Created Sales-Module schema % with mockup_usage table', v_schema;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- PART 4: CREATE COMPANY SCHEMAS
-- =============================================================================

SELECT public.create_company_schema('backlite_dubai');
SELECT public.create_company_schema('backlite_uk');
SELECT public.create_company_schema('backlite_abudhabi');
SELECT public.create_company_schema('viola');

-- =============================================================================
-- PART 5: PUBLIC SCHEMA TRIGGERS & RLS
-- =============================================================================

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_companies_updated_at ON public.companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON public.companies
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON public.chat_sessions;
CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON public.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

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

-- Service role full access policies
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
-- PART 6: CROSS-SCHEMA VIEW (for unified analytics access)
-- =============================================================================

-- All mockup usage across all companies
CREATE OR REPLACE VIEW public.all_mockup_usage AS
SELECT 'backlite_dubai' as company_code, u.* FROM backlite_dubai.mockup_usage u
UNION ALL
SELECT 'backlite_uk' as company_code, u.* FROM backlite_uk.mockup_usage u
UNION ALL
SELECT 'backlite_abudhabi' as company_code, u.* FROM backlite_abudhabi.mockup_usage u
UNION ALL
SELECT 'viola' as company_code, u.* FROM viola.mockup_usage u;

-- =============================================================================
-- DONE! Sales-Module schema is ready.
-- =============================================================================
--
-- SUMMARY:
-- --------
-- PUBLIC SCHEMA (cross-company data):
--   - companies (reference table)
--   - chat_sessions
--   - proposals_log, proposal_locations
--   - booking_orders, bo_locations, bo_approval_workflows
--   - ai_costs
--   - documents, mockup_files, proposal_files
--
-- COMPANY SCHEMAS (analytics only):
--   - mockup_usage (tracks mockup generation for analytics)
--
-- CROSS-SCHEMA VIEWS:
--   - public.all_mockup_usage
--
-- IMPORTANT:
-- ----------
-- This service does NOT store inventory data!
-- - Locations are in Asset-Management: {company}.standalone_assets, {company}.networks
-- - Mockup frames are in Asset-Management: {company}.mockup_frames
-- - Templates are in Asset-Management Storage: templates/{company}/{location_key}/
-- - Mockup photos are in Asset-Management Storage: mockups/{company}/{location_key}/
--
-- Sales-Module references Asset-Management via:
-- - location_key (TEXT) - the unique identifier for a location
-- - location_company (TEXT) - which company schema owns the location
--
-- To get location details, Sales-Module calls Asset-Management API.
--
-- =============================================================================
