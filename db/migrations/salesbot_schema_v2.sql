-- =============================================================================
-- SALES BOT SUPABASE SCHEMA V2 - LOCATION-CENTRIC DESIGN
-- =============================================================================
-- This schema puts LOCATIONS at the center, with everything linked to it.
-- Designed for extensibility: inventory management, occupation tracking, etc.
-- =============================================================================
--
-- USER_ID STRATEGY:
-- -----------------
-- All user_id fields store the SUPABASE UUID from UI Supabase (auth.users.id).
-- This is the canonical identifier passed via X-Trusted-User-Id header.
--
-- Flow: Browser → unified-ui (validates JWT, extracts user.id) → proposal-bot
--       Header: X-Trusted-User-Id: "550e8400-e29b-41d4-a716-446655440000"
--
-- For HISTORICAL DATA from Slack channel (before web UI):
--   - proposals_log.submitted_by contains Slack IDs like "U08867WNDUN"
--   - These are preserved in 'submitted_by' for display purposes
--   - New records from web UI will have proper user_id (UUID)
--
-- LINKING TO UI SUPABASE:
--   - user_id in SalesBot = id in UI Supabase auth.users table
--   - To get user details: Query UI Supabase profiles table by user_id
--   - Example: SELECT * FROM profiles WHERE id = '{user_id}'
--
-- =============================================================================

-- =============================================================================
-- CORE: LOCATIONS INVENTORY (The Foundation)
-- =============================================================================
CREATE TABLE IF NOT EXISTS locations (
    id BIGSERIAL PRIMARY KEY,

    -- Identity
    location_key TEXT NOT NULL UNIQUE,  -- e.g., 'dubai_gateway', 'uae14'
    display_name TEXT NOT NULL,          -- e.g., 'The Dubai Gateway'

    -- Classification
    display_type TEXT NOT NULL CHECK (display_type IN ('digital', 'static')),
    series TEXT,                          -- e.g., 'The Landmark Series'

    -- Physical Specs
    height TEXT,                          -- e.g., '14m' or 'Multiple Sizes'
    width TEXT,                           -- e.g., '7m' or 'Multiple Sizes'
    number_of_faces INTEGER DEFAULT 1,

    -- Digital-only fields (NULL for static)
    spot_duration INTEGER,                -- seconds per ad
    loop_duration INTEGER,                -- total loop seconds
    sov_percent DECIMAL(5,2),             -- share of voice %
    upload_fee DECIMAL(10,2),             -- one-time upload fee

    -- Static-only fields (NULL for digital)
    -- (production_fee is per-campaign, stored in rate_cards)

    -- Geographic
    city TEXT,                            -- e.g., 'Dubai', 'Abu Dhabi'
    area TEXT,                            -- e.g., 'Sheikh Zayed Road', 'DIFC'
    gps_lat DECIMAL(10,7),
    gps_lng DECIMAL(10,7),

    -- File references (relative paths)
    template_path TEXT,                   -- e.g., 'dubai_gateway/dubai_gateway.pptx'

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    notes TEXT
);

CREATE INDEX idx_locations_key ON locations(location_key);
CREATE INDEX idx_locations_type ON locations(display_type);
CREATE INDEX idx_locations_series ON locations(series);
CREATE INDEX idx_locations_active ON locations(is_active);
CREATE INDEX idx_locations_city ON locations(city);

-- =============================================================================
-- MOCKUP: Frame Configurations (Linked to Location)
-- =============================================================================
CREATE TABLE IF NOT EXISTS mockup_frames (
    id BIGSERIAL PRIMARY KEY,

    -- Link to location
    location_id BIGINT REFERENCES locations(id) ON DELETE CASCADE,
    location_key TEXT NOT NULL,  -- Denormalized for quick access

    -- Frame config
    time_of_day TEXT NOT NULL DEFAULT 'day' CHECK (time_of_day IN ('day', 'night')),
    finish TEXT NOT NULL DEFAULT 'gold' CHECK (finish IN ('gold', 'silver', 'black')),
    photo_filename TEXT NOT NULL,
    frames_data JSONB NOT NULL,  -- Frame positioning data [{points, config}, ...]

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    config_json JSONB,

    CONSTRAINT mockup_frames_unique UNIQUE (location_key, time_of_day, finish, photo_filename)
);

CREATE INDEX idx_mockup_frames_location ON mockup_frames(location_id);
CREATE INDEX idx_mockup_frames_location_key ON mockup_frames(location_key);

-- =============================================================================
-- MOCKUP: Usage Analytics
-- =============================================================================
CREATE TABLE IF NOT EXISTS mockup_usage (
    id BIGSERIAL PRIMARY KEY,

    -- Link to location
    location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
    location_key TEXT NOT NULL,

    -- User
    user_id TEXT,

    -- Generation details
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    time_of_day TEXT NOT NULL,
    finish TEXT NOT NULL,
    photo_used TEXT NOT NULL,
    creative_type TEXT NOT NULL CHECK (creative_type IN ('uploaded', 'ai_generated')),
    ai_prompt TEXT,
    template_selected BOOLEAN DEFAULT false,
    success BOOLEAN DEFAULT true,

    -- Metadata
    user_ip TEXT,
    metadata_json JSONB
);

CREATE INDEX idx_mockup_usage_location ON mockup_usage(location_id);
CREATE INDEX idx_mockup_usage_user ON mockup_usage(user_id);
CREATE INDEX idx_mockup_usage_date ON mockup_usage(generated_at);

-- =============================================================================
-- PROPOSALS: Log with Location Links
-- =============================================================================
CREATE TABLE IF NOT EXISTS proposals_log (
    id BIGSERIAL PRIMARY KEY,

    -- User
    user_id TEXT NOT NULL,
    submitted_by TEXT NOT NULL,

    -- Client
    client_name TEXT NOT NULL,

    -- Proposal details
    date_generated TIMESTAMPTZ DEFAULT NOW(),
    package_type TEXT NOT NULL CHECK (package_type IN ('separate', 'combined')),

    -- Financials (stored as aggregates)
    total_amount TEXT NOT NULL,
    currency TEXT DEFAULT 'AED',

    -- Full proposal data
    proposal_data JSONB,  -- Complete proposal JSON for reference

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_proposals_user ON proposals_log(user_id);
CREATE INDEX idx_proposals_client ON proposals_log(client_name);
CREATE INDEX idx_proposals_date ON proposals_log(date_generated);

-- =============================================================================
-- PROPOSALS: Location Line Items (Many-to-Many)
-- =============================================================================
-- This allows querying "all proposals for dubai_gateway"
CREATE TABLE IF NOT EXISTS proposal_locations (
    id BIGSERIAL PRIMARY KEY,

    -- Links
    proposal_id BIGINT NOT NULL REFERENCES proposals_log(id) ON DELETE CASCADE,
    location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
    location_key TEXT NOT NULL,  -- Denormalized for historical records

    -- Campaign details for this location
    start_date DATE,
    duration_weeks INTEGER,
    net_rate DECIMAL(15,2),

    -- Fees
    upload_fee DECIMAL(10,2),      -- For digital
    production_fee DECIMAL(10,2),  -- For static

    -- Metadata
    location_display_name TEXT,  -- Snapshot at time of proposal

    CONSTRAINT proposal_locations_unique UNIQUE (proposal_id, location_key)
);

CREATE INDEX idx_proposal_locations_proposal ON proposal_locations(proposal_id);
CREATE INDEX idx_proposal_locations_location ON proposal_locations(location_id);
CREATE INDEX idx_proposal_locations_key ON proposal_locations(location_key);

-- =============================================================================
-- BOOKING ORDERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS booking_orders (
    id BIGSERIAL PRIMARY KEY,

    -- Identity
    bo_ref TEXT NOT NULL UNIQUE,
    user_id TEXT,

    -- Company
    company TEXT NOT NULL,

    -- File information
    original_file_path TEXT NOT NULL,
    original_file_type TEXT NOT NULL,
    original_file_size BIGINT,
    original_filename TEXT,
    parsed_excel_path TEXT,

    -- Extracted data
    bo_number TEXT,
    bo_date TEXT,
    client TEXT,
    agency TEXT,
    brand_campaign TEXT,
    category TEXT,
    asset TEXT,

    -- Financial data
    net_pre_vat DECIMAL(15,2),
    vat_value DECIMAL(15,2),
    gross_amount DECIMAL(15,2),
    sla_pct DECIMAL(5,2),
    payment_terms TEXT,
    sales_person TEXT,
    commission_pct DECIMAL(5,2),

    -- Additional
    notes TEXT,
    locations_json JSONB,

    -- Parsing metadata
    extraction_method TEXT,
    extraction_confidence TEXT,
    warnings_json JSONB,
    missing_fields_json JSONB,

    -- Calculated fields
    vat_calc DECIMAL(15,2),
    gross_calc DECIMAL(15,2),
    sla_deduction DECIMAL(15,2),
    net_excl_sla_calc DECIMAL(15,2),

    -- Status
    parsed_at TIMESTAMPTZ DEFAULT NOW(),
    parsed_by TEXT,
    source_classification TEXT,
    classification_confidence TEXT,
    needs_review BOOLEAN DEFAULT false,

    -- Search
    search_text TEXT
);

CREATE INDEX idx_booking_orders_bo_ref ON booking_orders(bo_ref);
CREATE INDEX idx_booking_orders_company ON booking_orders(company);
CREATE INDEX idx_booking_orders_client ON booking_orders(client);
CREATE INDEX idx_booking_orders_user ON booking_orders(user_id);
CREATE INDEX idx_booking_orders_parsed ON booking_orders(parsed_at);

-- =============================================================================
-- BOOKING ORDER: Location Line Items
-- =============================================================================
CREATE TABLE IF NOT EXISTS bo_locations (
    id BIGSERIAL PRIMARY KEY,

    -- Links
    bo_id BIGINT NOT NULL REFERENCES booking_orders(id) ON DELETE CASCADE,
    location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
    location_key TEXT,

    -- Campaign details
    start_date DATE,
    end_date DATE,
    duration_weeks INTEGER,

    -- Financials
    net_rate DECIMAL(15,2),

    -- Raw from BO
    raw_location_text TEXT  -- Original text from parsed BO
);

CREATE INDEX idx_bo_locations_bo ON bo_locations(bo_id);
CREATE INDEX idx_bo_locations_location ON bo_locations(location_id);

-- =============================================================================
-- BOOKING ORDER: Approval Workflows
-- =============================================================================
CREATE TABLE IF NOT EXISTS bo_approval_workflows (
    workflow_id TEXT PRIMARY KEY,

    -- Link to BO (optional, workflow may exist before BO is saved)
    bo_id BIGINT REFERENCES booking_orders(id) ON DELETE SET NULL,

    -- Workflow data
    workflow_data JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'coordinator_approved', 'coordinator_rejected',
        'hos_approved', 'hos_rejected', 'cancelled', 'completed'
    )),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bo_workflows_status ON bo_approval_workflows(status);
CREATE INDEX idx_bo_workflows_bo ON bo_approval_workflows(bo_id);

-- =============================================================================
-- CHAT SESSIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chat_sessions_user_unique UNIQUE (user_id)
);

CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);

-- =============================================================================
-- AI COSTS TRACKING
-- =============================================================================
CREATE TABLE IF NOT EXISTS ai_costs (
    id BIGSERIAL PRIMARY KEY,

    -- Context
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    call_type TEXT NOT NULL CHECK (call_type IN (
        'classification', 'parsing', 'coordinator_thread', 'main_llm',
        'mockup_analysis', 'image_generation', 'bo_edit', 'other'
    )),
    workflow TEXT CHECK (workflow IN (
        'mockup_upload', 'mockup_ai', 'bo_parsing', 'bo_editing',
        'bo_revision', 'proposal_generation', 'general_chat', 'location_management'
    ) OR workflow IS NULL),

    -- Model
    model TEXT NOT NULL,
    user_id TEXT,
    context TEXT,

    -- Tokens
    input_tokens INTEGER,
    cached_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER,
    reasoning_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER,

    -- Costs
    input_cost DECIMAL(10,6),
    output_cost DECIMAL(10,6),
    reasoning_cost DECIMAL(10,6) DEFAULT 0,
    total_cost DECIMAL(10,6),

    -- Metadata
    metadata_json JSONB
);

CREATE INDEX idx_ai_costs_timestamp ON ai_costs(timestamp);
CREATE INDEX idx_ai_costs_call_type ON ai_costs(call_type);
CREATE INDEX idx_ai_costs_user ON ai_costs(user_id);
CREATE INDEX idx_ai_costs_workflow ON ai_costs(workflow);

-- =============================================================================
-- INVENTORY: Location Occupations (For scheduling/availability)
-- =============================================================================
-- Tracks which locations are booked for which dates
-- Enables availability checking and inventory management
CREATE TABLE IF NOT EXISTS location_occupations (
    id BIGSERIAL PRIMARY KEY,

    -- Links
    location_id BIGINT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    bo_id BIGINT REFERENCES booking_orders(id) ON DELETE SET NULL,
    proposal_id BIGINT REFERENCES proposals_log(id) ON DELETE SET NULL,

    -- Booking period
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    -- Client info
    client_name TEXT,
    campaign_name TEXT,
    brand TEXT,

    -- Status workflow
    status TEXT NOT NULL DEFAULT 'tentative' CHECK (status IN (
        'tentative',      -- Proposal stage
        'pending',        -- BO received, awaiting confirmation
        'confirmed',      -- Confirmed booking
        'live',           -- Currently running
        'completed',      -- Campaign finished
        'cancelled'       -- Cancelled
    )),

    -- Financials (snapshot)
    net_rate DECIMAL(15,2),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    notes TEXT

    -- Note: For PostgreSQL with btree_gist extension, you can add:
    -- CONSTRAINT no_double_booking EXCLUDE USING gist (
    --     location_id WITH =,
    --     daterange(start_date, end_date, '[]') WITH &&
    -- ) WHERE (status IN ('confirmed', 'live'))
);

CREATE INDEX idx_occupations_location ON location_occupations(location_id);
CREATE INDEX idx_occupations_dates ON location_occupations(start_date, end_date);
CREATE INDEX idx_occupations_status ON location_occupations(status);
CREATE INDEX idx_occupations_client ON location_occupations(client_name);
CREATE INDEX idx_occupations_bo ON location_occupations(bo_id);

-- =============================================================================
-- PRICING: Rate Cards (Location pricing by period)
-- =============================================================================
-- Allows flexible pricing: different rates for different periods
-- Supports seasonal pricing, price increases, etc.
CREATE TABLE IF NOT EXISTS rate_cards (
    id BIGSERIAL PRIMARY KEY,

    -- Link to location
    location_id BIGINT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,

    -- Validity period
    valid_from DATE NOT NULL,
    valid_to DATE,  -- NULL = indefinitely valid

    -- Pricing
    weekly_rate DECIMAL(15,2) NOT NULL,
    monthly_rate DECIMAL(15,2),  -- Optional monthly discount rate

    -- Digital specifics
    upload_fee DECIMAL(10,2),

    -- Static specifics
    production_fee_estimate DECIMAL(10,2),

    -- Currency
    currency TEXT DEFAULT 'AED',

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    notes TEXT,

    CONSTRAINT rate_cards_unique_period UNIQUE (location_id, valid_from)
);

CREATE INDEX idx_rate_cards_location ON rate_cards(location_id);
CREATE INDEX idx_rate_cards_valid ON rate_cards(valid_from, valid_to);
CREATE INDEX idx_rate_cards_active ON rate_cards(is_active);

-- =============================================================================
-- FILE STORAGE: Documents (BO uploads, general files)
-- =============================================================================
-- Central registry for all uploaded files
-- Actual files stored in Supabase Storage or local filesystem
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,  -- UUID for file access

    -- Ownership
    user_id TEXT NOT NULL,

    -- File info
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- MIME type
    file_size BIGINT,
    file_extension TEXT,

    -- Storage location
    storage_provider TEXT NOT NULL DEFAULT 'local' CHECK (storage_provider IN ('local', 'supabase', 's3')),
    storage_bucket TEXT NOT NULL DEFAULT 'uploads',
    storage_key TEXT NOT NULL,  -- Path within bucket: {user_id}/{date}/{file_id}_{filename}

    -- Classification
    document_type TEXT CHECK (document_type IN (
        'bo_pdf',           -- Booking order PDF
        'bo_image',         -- Booking order scan/photo
        'bo_excel',         -- Parsed BO Excel
        'creative',         -- Ad creative
        'contract',         -- Contract document
        'invoice',          -- Invoice
        'other'
    )),

    -- Links (optional, can link to specific records)
    bo_id BIGINT REFERENCES booking_orders(id) ON DELETE SET NULL,
    proposal_id BIGINT REFERENCES proposals_log(id) ON DELETE SET NULL,

    -- Status
    is_processed BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,  -- Soft delete
    deleted_at TIMESTAMPTZ,  -- When soft-deleted (NULL if active)

    -- File integrity
    file_hash TEXT,  -- SHA256 hash for deduplication/integrity

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB  -- Extra info (dimensions, page count, etc.)
);

CREATE INDEX idx_documents_file_id ON documents(file_id);
CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_bo ON documents(bo_id);
CREATE INDEX idx_documents_proposal ON documents(proposal_id);
CREATE INDEX idx_documents_created ON documents(created_at);
CREATE INDEX idx_documents_hash ON documents(file_hash);
CREATE INDEX idx_documents_active ON documents(is_deleted) WHERE is_deleted = false;

-- =============================================================================
-- FILE STORAGE: Mockup Files (Generated mockups)
-- =============================================================================
-- Tracks generated mockup images
CREATE TABLE IF NOT EXISTS mockup_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,  -- UUID for file access

    -- Ownership
    user_id TEXT,

    -- Link to location
    location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
    location_key TEXT NOT NULL,

    -- Generation context
    mockup_usage_id BIGINT REFERENCES mockup_usage(id) ON DELETE SET NULL,

    -- File info
    original_filename TEXT,
    file_size BIGINT,

    -- Storage location
    storage_provider TEXT NOT NULL DEFAULT 'local',
    storage_bucket TEXT NOT NULL DEFAULT 'mockups',
    storage_key TEXT NOT NULL,  -- Path: {location_key}/{time_of_day}/{finish}/{filename}

    -- Mockup details
    time_of_day TEXT NOT NULL DEFAULT 'day',
    finish TEXT NOT NULL DEFAULT 'gold',
    photo_filename TEXT,  -- Base photo used

    -- Creative source
    creative_type TEXT CHECK (creative_type IN ('uploaded', 'ai_generated')),
    creative_file_id TEXT,  -- Reference to uploaded creative
    ai_prompt TEXT,

    -- Output
    output_format TEXT DEFAULT 'png',
    width INTEGER,
    height INTEGER,

    -- Status
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,  -- When soft-deleted (NULL if active)

    -- File integrity
    file_hash TEXT,  -- SHA256 hash for deduplication/integrity

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX idx_mockup_files_file_id ON mockup_files(file_id);
CREATE INDEX idx_mockup_files_user ON mockup_files(user_id);
CREATE INDEX idx_mockup_files_location ON mockup_files(location_id);
CREATE INDEX idx_mockup_files_location_key ON mockup_files(location_key);
CREATE INDEX idx_mockup_files_created ON mockup_files(created_at);
CREATE INDEX idx_mockup_files_hash ON mockup_files(file_hash);
CREATE INDEX idx_mockup_files_active ON mockup_files(is_deleted) WHERE is_deleted = false;

-- =============================================================================
-- FILE STORAGE: Proposal Files (Generated PPTX)
-- =============================================================================
-- Tracks generated proposal presentations
CREATE TABLE IF NOT EXISTS proposal_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,  -- UUID for file access

    -- Ownership
    user_id TEXT NOT NULL,

    -- Link to proposal
    proposal_id BIGINT REFERENCES proposals_log(id) ON DELETE CASCADE,

    -- File info
    original_filename TEXT NOT NULL,
    file_size BIGINT,

    -- Storage location
    storage_provider TEXT NOT NULL DEFAULT 'local',
    storage_bucket TEXT NOT NULL DEFAULT 'proposals',
    storage_key TEXT NOT NULL,  -- Path: {user_id}/{date}/{proposal_id}_{filename}.pptx

    -- Proposal details (snapshot)
    client_name TEXT,
    package_type TEXT,
    location_count INTEGER,

    -- Version tracking
    version INTEGER DEFAULT 1,
    is_latest BOOLEAN DEFAULT true,

    -- Status
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,  -- When soft-deleted (NULL if active)

    -- File integrity
    file_hash TEXT,  -- SHA256 hash for deduplication/integrity

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB  -- Slide count, template used, etc.
);

CREATE INDEX idx_proposal_files_file_id ON proposal_files(file_id);
CREATE INDEX idx_proposal_files_user ON proposal_files(user_id);
CREATE INDEX idx_proposal_files_proposal ON proposal_files(proposal_id);
CREATE INDEX idx_proposal_files_created ON proposal_files(created_at);
CREATE INDEX idx_proposal_files_hash ON proposal_files(file_hash);
CREATE INDEX idx_proposal_files_active ON proposal_files(is_deleted) WHERE is_deleted = false;

-- =============================================================================
-- FILE STORAGE: Location Photos (Background photos for mockups)
-- =============================================================================
-- Tracks available background photos for each location
CREATE TABLE IF NOT EXISTS location_photos (
    id BIGSERIAL PRIMARY KEY,

    -- Link to location
    location_id BIGINT REFERENCES locations(id) ON DELETE CASCADE,
    location_key TEXT NOT NULL,

    -- Photo variants
    time_of_day TEXT NOT NULL DEFAULT 'day' CHECK (time_of_day IN ('day', 'night', 'all')),
    finish TEXT NOT NULL DEFAULT 'gold' CHECK (finish IN ('gold', 'silver', 'black', 'all')),

    -- File info
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,  -- Relative path: {location_key}/{time_of_day}/{finish}/{filename}
    file_size BIGINT,
    width INTEGER,
    height INTEGER,

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,  -- Default photo for this variant

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    notes TEXT,

    CONSTRAINT location_photos_unique UNIQUE (location_key, time_of_day, finish, filename)
);

CREATE INDEX idx_location_photos_location ON location_photos(location_id);
CREATE INDEX idx_location_photos_key ON location_photos(location_key);
CREATE INDEX idx_location_photos_variant ON location_photos(time_of_day, finish);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-update timestamps
DROP TRIGGER IF EXISTS update_locations_updated_at ON locations;
CREATE TRIGGER update_locations_updated_at
    BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_bo_workflows_updated_at ON bo_approval_workflows;
CREATE TRIGGER update_bo_workflows_updated_at
    BEFORE UPDATE ON bo_approval_workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_occupations_updated_at ON location_occupations;
CREATE TRIGGER update_occupations_updated_at
    BEFORE UPDATE ON location_occupations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- ROW LEVEL SECURITY (Service role bypasses)
-- =============================================================================
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to locations" ON locations FOR ALL USING (true);

ALTER TABLE mockup_frames ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_frames" ON mockup_frames FOR ALL USING (true);

ALTER TABLE mockup_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_usage" ON mockup_usage FOR ALL USING (true);

ALTER TABLE proposals_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposals_log" ON proposals_log FOR ALL USING (true);

ALTER TABLE proposal_locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposal_locations" ON proposal_locations FOR ALL USING (true);

ALTER TABLE booking_orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to booking_orders" ON booking_orders FOR ALL USING (true);

ALTER TABLE bo_locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to bo_locations" ON bo_locations FOR ALL USING (true);

ALTER TABLE bo_approval_workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to bo_workflows" ON bo_approval_workflows FOR ALL USING (true);

ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to chat_sessions" ON chat_sessions FOR ALL USING (true);

ALTER TABLE ai_costs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to ai_costs" ON ai_costs FOR ALL USING (true);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to documents" ON documents FOR ALL USING (true);

ALTER TABLE mockup_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_files" ON mockup_files FOR ALL USING (true);

ALTER TABLE proposal_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposal_files" ON proposal_files FOR ALL USING (true);

ALTER TABLE location_photos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to location_photos" ON location_photos FOR ALL USING (true);

ALTER TABLE location_occupations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to location_occupations" ON location_occupations FOR ALL USING (true);

ALTER TABLE rate_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to rate_cards" ON rate_cards FOR ALL USING (true);

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- VIEWS (Convenience)
-- =============================================================================

-- Digital locations with full metadata
CREATE OR REPLACE VIEW digital_locations AS
SELECT
    id, location_key, display_name, series,
    height, width, number_of_faces,
    spot_duration, loop_duration, sov_percent, upload_fee,
    city, area,
    template_path, is_active
FROM locations
WHERE display_type = 'digital' AND is_active = true
ORDER BY series, display_name;

-- Static locations with full metadata
CREATE OR REPLACE VIEW static_locations AS
SELECT
    id, location_key, display_name, series,
    height, width, number_of_faces,
    city, area,
    template_path, is_active
FROM locations
WHERE display_type = 'static' AND is_active = true
ORDER BY series, display_name;

-- Digital locations with current rate card
CREATE OR REPLACE VIEW digital_locations_with_rates AS
SELECT
    l.id, l.location_key, l.display_name, l.series,
    l.height, l.width, l.number_of_faces,
    l.spot_duration, l.loop_duration, l.sov_percent,
    COALESCE(r.upload_fee, l.upload_fee) as upload_fee,
    r.weekly_rate,
    r.monthly_rate,
    l.city, l.area,
    l.template_path, l.is_active
FROM locations l
LEFT JOIN rate_cards r ON l.id = r.location_id
    AND r.is_active = true
    AND r.valid_from <= CURRENT_DATE
    AND (r.valid_to IS NULL OR r.valid_to >= CURRENT_DATE)
WHERE l.display_type = 'digital' AND l.is_active = true
ORDER BY l.series, l.display_name;

-- Static locations with current rate card
CREATE OR REPLACE VIEW static_locations_with_rates AS
SELECT
    l.id, l.location_key, l.display_name, l.series,
    l.height, l.width, l.number_of_faces,
    r.weekly_rate,
    r.monthly_rate,
    r.production_fee_estimate,
    l.city, l.area,
    l.template_path, l.is_active
FROM locations l
LEFT JOIN rate_cards r ON l.id = r.location_id
    AND r.is_active = true
    AND r.valid_from <= CURRENT_DATE
    AND (r.valid_to IS NULL OR r.valid_to >= CURRENT_DATE)
WHERE l.display_type = 'static' AND l.is_active = true
ORDER BY l.series, l.display_name;

-- Location availability view (shows what's booked)
CREATE OR REPLACE VIEW location_availability AS
SELECT
    l.id as location_id,
    l.location_key,
    l.display_name,
    l.display_type,
    o.id as occupation_id,
    o.start_date,
    o.end_date,
    o.client_name,
    o.campaign_name,
    o.brand,
    o.status,
    o.net_rate
FROM locations l
LEFT JOIN location_occupations o ON l.id = o.location_id
    AND o.status NOT IN ('cancelled', 'completed')
    AND o.end_date >= CURRENT_DATE
WHERE l.is_active = true
ORDER BY l.display_name, o.start_date;

-- Proposal summary with location details
CREATE OR REPLACE VIEW proposals_summary AS
SELECT
    p.id,
    p.user_id,
    p.submitted_by,
    p.client_name,
    p.date_generated,
    p.package_type,
    p.total_amount,
    p.currency,
    COUNT(pl.id) as location_count,
    STRING_AGG(DISTINCT pl.location_key, ', ' ORDER BY pl.location_key) as location_keys,
    STRING_AGG(DISTINCT pl.location_display_name, ', ' ORDER BY pl.location_display_name) as location_names,
    SUM(pl.net_rate) as total_net_rate
FROM proposals_log p
LEFT JOIN proposal_locations pl ON p.id = pl.proposal_id
GROUP BY p.id
ORDER BY p.date_generated DESC;

-- Booking order summary with location details
CREATE OR REPLACE VIEW booking_orders_summary AS
SELECT
    bo.id,
    bo.bo_ref,
    bo.user_id,
    bo.company,
    bo.client,
    bo.agency,
    bo.brand_campaign,
    bo.net_pre_vat,
    bo.gross_amount,
    bo.parsed_at,
    COUNT(bl.id) as location_count,
    STRING_AGG(DISTINCT bl.location_key, ', ' ORDER BY bl.location_key) as location_keys,
    MIN(bl.start_date) as campaign_start,
    MAX(bl.end_date) as campaign_end
FROM booking_orders bo
LEFT JOIN bo_locations bl ON bo.id = bl.bo_id
GROUP BY bo.id
ORDER BY bo.parsed_at DESC;

-- =============================================================================
-- Done! Location-centric schema ready.
-- =============================================================================
--
-- MIGRATION NOTES:
-- ----------------
-- For existing databases, use db/migrations/v1_to_v2_migration.sql
--
-- After migration, run:
-- 1. python db/scripts/seed_locations.py  -- Populate locations from metadata.txt
-- 2. python db/scripts/migrate_existing_data.py  -- Link existing data
--
-- =============================================================================
