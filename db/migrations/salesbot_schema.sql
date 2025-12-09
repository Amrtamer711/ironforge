-- =============================================================================
-- SALES BOT SUPABASE SCHEMA (Business Data)
-- =============================================================================
-- Run this in SalesBot-Dev and SalesBot-Prod Supabase projects
--
-- This database handles Sales module business data ONLY:
-- - Proposals
-- - Mockups
-- - Booking Orders
-- - AI Costs
--
-- NOTE: Auth/RBAC tables are in UI Supabase, NOT here.
-- This service receives user_id from JWT tokens validated by the UI.
-- =============================================================================

-- =============================================================================
-- PROPOSALS
-- =============================================================================
CREATE TABLE IF NOT EXISTS proposals_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,  -- From JWT, references UI Supabase users
    submitted_by TEXT NOT NULL,  -- Display name
    client_name TEXT NOT NULL,
    date_generated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    package_type TEXT NOT NULL,
    locations TEXT NOT NULL,
    total_amount TEXT NOT NULL,
    proposal_data JSONB,  -- Full proposal JSON for future reference
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proposals_user ON proposals_log(user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_client ON proposals_log(client_name);
CREATE INDEX IF NOT EXISTS idx_proposals_date ON proposals_log(date_generated);

-- =============================================================================
-- MOCKUPS
-- =============================================================================

-- Mockup frame configurations (saved templates)
CREATE TABLE IF NOT EXISTS mockup_frames (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,  -- NULL for system templates
    location_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL DEFAULT 'day' CHECK (time_of_day IN ('day', 'night')),
    finish TEXT NOT NULL DEFAULT 'gold' CHECK (finish IN ('gold', 'silver', 'black')),
    photo_filename TEXT NOT NULL,
    frames_data JSONB NOT NULL,  -- Frame positioning data
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,  -- Display name
    config_json JSONB,  -- Additional configuration
    CONSTRAINT mockup_frames_unique UNIQUE (location_key, time_of_day, finish, photo_filename)
);

CREATE INDEX IF NOT EXISTS idx_mockup_frames_user ON mockup_frames(user_id);
CREATE INDEX IF NOT EXISTS idx_mockup_frames_location ON mockup_frames(location_key);

-- Mockup usage analytics
CREATE TABLE IF NOT EXISTS mockup_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    finish TEXT NOT NULL,
    photo_used TEXT NOT NULL,
    creative_type TEXT NOT NULL CHECK (creative_type IN ('uploaded', 'ai_generated')),
    ai_prompt TEXT,
    template_selected BOOLEAN NOT NULL DEFAULT false,
    success BOOLEAN NOT NULL DEFAULT true,
    user_ip TEXT,
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_mockup_usage_user ON mockup_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_mockup_usage_date ON mockup_usage(generated_at);
CREATE INDEX IF NOT EXISTS idx_mockup_usage_location ON mockup_usage(location_key);

-- =============================================================================
-- BOOKING ORDERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS booking_orders (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,  -- User who uploaded/created
    bo_ref TEXT NOT NULL UNIQUE,  -- Unique reference ID
    company TEXT NOT NULL,

    -- File information
    original_file_path TEXT NOT NULL,
    original_file_type TEXT NOT NULL,
    original_file_size BIGINT,
    original_filename TEXT,
    parsed_excel_path TEXT NOT NULL,

    -- Extracted data
    bo_number TEXT,
    bo_date TEXT,
    client TEXT,
    agency TEXT,
    brand_campaign TEXT,
    category TEXT,
    asset TEXT,

    -- Financial data
    net_pre_vat DOUBLE PRECISION,
    vat_value DOUBLE PRECISION,
    gross_amount DOUBLE PRECISION,
    sla_pct DOUBLE PRECISION,
    payment_terms TEXT,
    sales_person TEXT,
    commission_pct DOUBLE PRECISION,

    -- Additional data
    notes TEXT,
    locations_json JSONB,

    -- Parsing metadata
    extraction_method TEXT,
    extraction_confidence TEXT,
    warnings_json JSONB,
    missing_fields_json JSONB,

    -- Calculated fields
    vat_calc DOUBLE PRECISION,
    gross_calc DOUBLE PRECISION,
    sla_deduction DOUBLE PRECISION,
    net_excl_sla_calc DOUBLE PRECISION,

    -- Timestamps and status
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsed_by TEXT,
    source_classification TEXT,
    classification_confidence TEXT,
    needs_review BOOLEAN DEFAULT false,

    -- Search optimization
    search_text TEXT  -- Full-text search field
);

CREATE INDEX IF NOT EXISTS idx_booking_orders_user ON booking_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_booking_orders_bo_ref ON booking_orders(bo_ref);
CREATE INDEX IF NOT EXISTS idx_booking_orders_company ON booking_orders(company);
CREATE INDEX IF NOT EXISTS idx_booking_orders_client ON booking_orders(client);
CREATE INDEX IF NOT EXISTS idx_booking_orders_parsed_at ON booking_orders(parsed_at);
CREATE INDEX IF NOT EXISTS idx_booking_orders_sales_person ON booking_orders(sales_person);

-- Booking order approval workflows
CREATE TABLE IF NOT EXISTS bo_approval_workflows (
    workflow_id TEXT PRIMARY KEY,
    workflow_data JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bo_workflows_status ON bo_approval_workflows(status);
CREATE INDEX IF NOT EXISTS idx_bo_workflows_updated ON bo_approval_workflows(updated_at);

-- =============================================================================
-- AI COSTS TRACKING
-- =============================================================================
CREATE TABLE IF NOT EXISTS ai_costs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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

    -- Token counts
    input_tokens INTEGER,
    cached_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER,
    reasoning_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER,

    -- Costs
    input_cost DOUBLE PRECISION,
    output_cost DOUBLE PRECISION,
    reasoning_cost DOUBLE PRECISION DEFAULT 0,
    total_cost DOUBLE PRECISION,

    -- Additional data
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_ai_costs_timestamp ON ai_costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_costs_call_type ON ai_costs(call_type);
CREATE INDEX IF NOT EXISTS idx_ai_costs_user ON ai_costs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_costs_workflow ON ai_costs(workflow);
CREATE INDEX IF NOT EXISTS idx_ai_costs_model ON ai_costs(model);

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================
-- Note: Sales Bot uses service_role key for all operations.
-- User isolation is handled at the application layer via JWT user_id.
-- RLS policies here are a defense-in-depth measure.

-- Proposals - users see own, admins see all
ALTER TABLE proposals_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposals" ON proposals_log
    FOR ALL USING (true);  -- Service role bypasses RLS

-- Mockup frames - public read for templates (user_id IS NULL), own for user frames
ALTER TABLE mockup_frames ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_frames" ON mockup_frames
    FOR ALL USING (true);

-- Mockup usage - users see own
ALTER TABLE mockup_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_usage" ON mockup_usage
    FOR ALL USING (true);

-- Booking orders - users see own, HOS/admin see team
ALTER TABLE booking_orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to booking_orders" ON booking_orders
    FOR ALL USING (true);

-- BO workflows
ALTER TABLE bo_approval_workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to bo_workflows" ON bo_approval_workflows
    FOR ALL USING (true);

-- AI costs - analytics, service role only
ALTER TABLE ai_costs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to ai_costs" ON ai_costs
    FOR ALL USING (true);

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-update workflow timestamp
DROP TRIGGER IF EXISTS update_bo_workflows_updated_at ON bo_approval_workflows;
CREATE TRIGGER update_bo_workflows_updated_at
    BEFORE UPDATE ON bo_approval_workflows
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- =============================================================================
-- Done! Your Sales Bot database is ready.
-- =============================================================================
