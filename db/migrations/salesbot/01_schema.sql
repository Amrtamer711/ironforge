-- =============================================================================
-- SALES BOT SUPABASE SCHEMA - MULTI-SCHEMA PER-COMPANY ISOLATION
-- =============================================================================
-- Run this in: Sales-Bot-Dev and Sales-Bot-Prod Supabase SQL Editor
--
-- ARCHITECTURE:
-- - public schema: Shared reference data (companies, functions)
-- - Per-company schemas: Isolated data (locations, proposals, etc.)
--
-- Schemas:
--   public          - Shared reference tables and functions
--   backlite_dubai  - Backlite Dubai data
--   backlite_uk     - Backlite UK data
--   backlite_abudhabi - Backlite Abu Dhabi data
--   viola           - Viola data
--
-- Storage Paths (per company):
--   templates/{company_code}/{location_key}/
--   mockups/{company_code}/{location_key}/
--   uploads/{company_code}/{user_id}/
--   proposals/{company_code}/{user_id}/
--
-- =============================================================================

-- =============================================================================
-- PART 1: PUBLIC SCHEMA - SHARED REFERENCE DATA
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
-- This function creates all tables for a company schema
-- Call: SELECT public.create_company_schema('backlite_dubai');

CREATE OR REPLACE FUNCTION public.create_company_schema(p_company_code TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := p_company_code;
BEGIN
    -- Create schema if not exists
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema);

    -- =========================================================================
    -- LOCATIONS INVENTORY
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.locations (
            id BIGSERIAL PRIMARY KEY,
            location_key TEXT NOT NULL UNIQUE,
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
            gps_lat DECIMAL(10,7),
            gps_lng DECIMAL(10,7),
            template_path TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT,
            notes TEXT
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_key ON %I.locations(location_key)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_type ON %I.locations(display_type)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_series ON %I.locations(series)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_locations_active ON %I.locations(is_active)', v_schema);

    -- =========================================================================
    -- MOCKUP FRAMES
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
    -- MOCKUP USAGE
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
    -- PROPOSALS LOG
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.proposals_log (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            submitted_by TEXT NOT NULL,
            client_name TEXT NOT NULL,
            date_generated TIMESTAMPTZ DEFAULT NOW(),
            package_type TEXT NOT NULL CHECK (package_type IN (''separate'', ''combined'')),
            total_amount TEXT NOT NULL,
            currency TEXT DEFAULT ''AED'',
            proposal_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposals_user ON %I.proposals_log(user_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposals_client ON %I.proposals_log(client_name)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposals_date ON %I.proposals_log(date_generated)', v_schema);

    -- =========================================================================
    -- PROPOSAL LOCATIONS
    -- =========================================================================
    -- NOTE: No unique constraint - same location can appear multiple times per proposal
    -- (e.g., same location with different options/finishes)
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.proposal_locations (
            id BIGSERIAL PRIMARY KEY,
            proposal_id BIGINT NOT NULL REFERENCES %I.proposals_log(id) ON DELETE CASCADE,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE SET NULL,
            location_key TEXT NOT NULL,
            start_date DATE,
            duration_weeks INTEGER,
            net_rate DECIMAL(15,2),
            upload_fee DECIMAL(10,2),
            production_fee DECIMAL(10,2),
            location_display_name TEXT
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposal_locations_proposal ON %I.proposal_locations(proposal_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposal_locations_location ON %I.proposal_locations(location_id)', v_schema);

    -- =========================================================================
    -- BOOKING ORDERS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.booking_orders (
            id BIGSERIAL PRIMARY KEY,
            bo_ref TEXT NOT NULL UNIQUE,
            user_id TEXT,
            company TEXT NOT NULL,
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
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_booking_orders_bo_ref ON %I.booking_orders(bo_ref)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_booking_orders_client ON %I.booking_orders(client)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_booking_orders_user ON %I.booking_orders(user_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_booking_orders_parsed ON %I.booking_orders(parsed_at)', v_schema);

    -- =========================================================================
    -- BO LOCATIONS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.bo_locations (
            id BIGSERIAL PRIMARY KEY,
            bo_id BIGINT NOT NULL REFERENCES %I.booking_orders(id) ON DELETE CASCADE,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE SET NULL,
            location_key TEXT,
            start_date DATE,
            end_date DATE,
            duration_weeks INTEGER,
            net_rate DECIMAL(15,2),
            raw_location_text TEXT
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_bo_locations_bo ON %I.bo_locations(bo_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_bo_locations_location ON %I.bo_locations(location_id)', v_schema);

    -- =========================================================================
    -- BO APPROVAL WORKFLOWS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.bo_approval_workflows (
            workflow_id TEXT PRIMARY KEY,
            bo_id BIGINT REFERENCES %I.booking_orders(id) ON DELETE SET NULL,
            workflow_data JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT ''pending'' CHECK (status IN (
                ''pending'', ''coordinator_approved'', ''coordinator_rejected'',
                ''hos_approved'', ''hos_rejected'', ''cancelled'', ''completed''
            )),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_bo_workflows_status ON %I.bo_approval_workflows(status)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_bo_workflows_bo ON %I.bo_approval_workflows(bo_id)', v_schema);

    -- =========================================================================
    -- CHAT SESSIONS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.chat_sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            messages JSONB NOT NULL DEFAULT ''[]'',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON %I.chat_sessions(user_id)', v_schema);

    -- =========================================================================
    -- AI COSTS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.ai_costs (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            call_type TEXT NOT NULL CHECK (call_type IN (
                ''classification'', ''parsing'', ''coordinator_thread'', ''main_llm'',
                ''mockup_analysis'', ''image_generation'', ''bo_edit'', ''other''
            )),
            workflow TEXT CHECK (workflow IN (
                ''mockup_upload'', ''mockup_ai'', ''bo_parsing'', ''bo_editing'',
                ''bo_revision'', ''proposal_generation'', ''general_chat'', ''location_management''
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
        )', v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_ai_costs_timestamp ON %I.ai_costs(timestamp)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_ai_costs_call_type ON %I.ai_costs(call_type)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_ai_costs_user ON %I.ai_costs(user_id)', v_schema);

    -- =========================================================================
    -- LOCATION OCCUPATIONS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.location_occupations (
            id BIGSERIAL PRIMARY KEY,
            location_id BIGINT NOT NULL REFERENCES %I.locations(id) ON DELETE CASCADE,
            bo_id BIGINT REFERENCES %I.booking_orders(id) ON DELETE SET NULL,
            proposal_id BIGINT REFERENCES %I.proposals_log(id) ON DELETE SET NULL,
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
        )', v_schema, v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_location ON %I.location_occupations(location_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_dates ON %I.location_occupations(start_date, end_date)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_occupations_status ON %I.location_occupations(status)', v_schema);

    -- =========================================================================
    -- RATE CARDS
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
    -- DOCUMENTS
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.documents (
            id BIGSERIAL PRIMARY KEY,
            file_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size BIGINT,
            file_extension TEXT,
            storage_provider TEXT NOT NULL DEFAULT ''supabase'',
            storage_bucket TEXT NOT NULL DEFAULT ''uploads'',
            storage_key TEXT NOT NULL,
            document_type TEXT CHECK (document_type IN (
                ''bo_pdf'', ''bo_image'', ''bo_excel'', ''creative'', ''contract'', ''invoice'', ''other''
            )),
            bo_id BIGINT REFERENCES %I.booking_orders(id) ON DELETE SET NULL,
            proposal_id BIGINT REFERENCES %I.proposals_log(id) ON DELETE SET NULL,
            is_processed BOOLEAN DEFAULT false,
            is_deleted BOOLEAN DEFAULT false,
            deleted_at TIMESTAMPTZ,
            file_hash TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            metadata_json JSONB
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_documents_file_id ON %I.documents(file_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_documents_user ON %I.documents(user_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_documents_type ON %I.documents(document_type)', v_schema);

    -- =========================================================================
    -- MOCKUP FILES
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.mockup_files (
            id BIGSERIAL PRIMARY KEY,
            file_id TEXT NOT NULL UNIQUE,
            user_id TEXT,
            location_id BIGINT REFERENCES %I.locations(id) ON DELETE SET NULL,
            location_key TEXT NOT NULL,
            mockup_usage_id BIGINT REFERENCES %I.mockup_usage(id) ON DELETE SET NULL,
            original_filename TEXT,
            file_size BIGINT,
            storage_provider TEXT NOT NULL DEFAULT ''supabase'',
            storage_bucket TEXT NOT NULL DEFAULT ''mockups'',
            storage_key TEXT NOT NULL,
            time_of_day TEXT NOT NULL DEFAULT ''day'',
            finish TEXT NOT NULL DEFAULT ''gold'',
            photo_filename TEXT,
            creative_type TEXT CHECK (creative_type IN (''uploaded'', ''ai_generated'')),
            creative_file_id TEXT,
            ai_prompt TEXT,
            output_format TEXT DEFAULT ''png'',
            width INTEGER,
            height INTEGER,
            is_deleted BOOLEAN DEFAULT false,
            deleted_at TIMESTAMPTZ,
            file_hash TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            metadata_json JSONB
        )', v_schema, v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_files_file_id ON %I.mockup_files(file_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_mockup_files_location ON %I.mockup_files(location_id)', v_schema);

    -- =========================================================================
    -- PROPOSAL FILES
    -- =========================================================================
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.proposal_files (
            id BIGSERIAL PRIMARY KEY,
            file_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            proposal_id BIGINT REFERENCES %I.proposals_log(id) ON DELETE CASCADE,
            original_filename TEXT NOT NULL,
            file_size BIGINT,
            storage_provider TEXT NOT NULL DEFAULT ''supabase'',
            storage_bucket TEXT NOT NULL DEFAULT ''proposals'',
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
        )', v_schema, v_schema);

    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposal_files_file_id ON %I.proposal_files(file_id)', v_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_proposal_files_proposal ON %I.proposal_files(proposal_id)', v_schema);

    -- =========================================================================
    -- LOCATION PHOTOS
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
    -- TRIGGERS
    -- =========================================================================
    EXECUTE format('
        DROP TRIGGER IF EXISTS update_locations_updated_at ON %I.locations;
        CREATE TRIGGER update_locations_updated_at
            BEFORE UPDATE ON %I.locations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_bo_workflows_updated_at ON %I.bo_approval_workflows;
        CREATE TRIGGER update_bo_workflows_updated_at
            BEFORE UPDATE ON %I.bo_approval_workflows
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON %I.chat_sessions;
        CREATE TRIGGER update_chat_sessions_updated_at
            BEFORE UPDATE ON %I.chat_sessions
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    EXECUTE format('
        DROP TRIGGER IF EXISTS update_occupations_updated_at ON %I.location_occupations;
        CREATE TRIGGER update_occupations_updated_at
            BEFORE UPDATE ON %I.location_occupations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
    ', v_schema, v_schema);

    -- =========================================================================
    -- ROW LEVEL SECURITY
    -- =========================================================================
    EXECUTE format('ALTER TABLE %I.locations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.mockup_frames ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.mockup_usage ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.proposals_log ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.proposal_locations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.booking_orders ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.bo_locations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.bo_approval_workflows ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.chat_sessions ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.ai_costs ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.location_occupations ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.rate_cards ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.documents ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.mockup_files ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.proposal_files ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I.location_photos ENABLE ROW LEVEL SECURITY', v_schema);

    -- Service role full access policies
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.locations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_frames FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_usage FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.proposals_log FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.proposal_locations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.booking_orders FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.bo_locations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.bo_approval_workflows FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.chat_sessions FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.ai_costs FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.location_occupations FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.rate_cards FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.documents FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.mockup_files FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.proposal_files FOR ALL USING (true)', v_schema);
    EXECUTE format('CREATE POLICY "Service role full access" ON %I.location_photos FOR ALL USING (true)', v_schema);

    -- =========================================================================
    -- GRANTS
    -- =========================================================================
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO service_role', v_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO service_role', v_schema);

    RAISE NOTICE 'Created schema % with all tables', v_schema;
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
-- PART 5: CROSS-SCHEMA VIEWS (for MMG/group access)
-- =============================================================================

-- All locations across all companies (for MMG users)
CREATE OR REPLACE VIEW public.all_locations AS
SELECT 'backlite_dubai' as company_code, l.* FROM backlite_dubai.locations l
UNION ALL
SELECT 'backlite_uk' as company_code, l.* FROM backlite_uk.locations l
UNION ALL
SELECT 'backlite_abudhabi' as company_code, l.* FROM backlite_abudhabi.locations l
UNION ALL
SELECT 'viola' as company_code, l.* FROM viola.locations l;

-- All proposals across all companies
CREATE OR REPLACE VIEW public.all_proposals AS
SELECT 'backlite_dubai' as company_code, p.* FROM backlite_dubai.proposals_log p
UNION ALL
SELECT 'backlite_uk' as company_code, p.* FROM backlite_uk.proposals_log p
UNION ALL
SELECT 'backlite_abudhabi' as company_code, p.* FROM backlite_abudhabi.proposals_log p
UNION ALL
SELECT 'viola' as company_code, p.* FROM viola.proposals_log p;

-- All booking orders across all companies
CREATE OR REPLACE VIEW public.all_booking_orders AS
SELECT 'backlite_dubai' as company_code, bo.* FROM backlite_dubai.booking_orders bo
UNION ALL
SELECT 'backlite_uk' as company_code, bo.* FROM backlite_uk.booking_orders bo
UNION ALL
SELECT 'backlite_abudhabi' as company_code, bo.* FROM backlite_abudhabi.booking_orders bo
UNION ALL
SELECT 'viola' as company_code, bo.* FROM viola.booking_orders bo;

-- All AI costs across all companies
CREATE OR REPLACE VIEW public.all_ai_costs AS
SELECT 'backlite_dubai' as company_code, c.* FROM backlite_dubai.ai_costs c
UNION ALL
SELECT 'backlite_uk' as company_code, c.* FROM backlite_uk.ai_costs c
UNION ALL
SELECT 'backlite_abudhabi' as company_code, c.* FROM backlite_abudhabi.ai_costs c
UNION ALL
SELECT 'viola' as company_code, c.* FROM viola.ai_costs c;

-- =============================================================================
-- PART 6: PUBLIC SCHEMA RLS & GRANTS
-- =============================================================================

ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON public.companies FOR ALL USING (true);

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- DONE! Multi-schema per-company isolation is ready.
-- =============================================================================
--
-- USAGE:
-- ------
-- 1. Query specific company:
--    SELECT * FROM backlite_dubai.locations;
--
-- 2. Query all companies (MMG access):
--    SELECT * FROM public.all_locations;
--
-- 3. Get user's accessible schemas:
--    SELECT * FROM public.get_accessible_schemas(ARRAY[3, 6]); -- backlite_dubai + viola
--
-- STORAGE PATHS:
-- --------------
-- templates/backlite_dubai/dubai_gateway/dubai_gateway.pptx
-- templates/backlite_uk/london_bridge/london_bridge.pptx
-- mockups/backlite_dubai/dubai_gateway/day/gold/photo1.jpg
-- uploads/backlite_dubai/{user_id}/bo_2024_001.pdf
-- proposals/backlite_dubai/{user_id}/proposal_client_2024.pptx
--
-- =============================================================================
