-- =============================================================================
-- MIGRATION: V1 to V2 (Location-Centric Schema)
-- =============================================================================
-- This migration transforms the existing schema to the location-centric design.
--
-- IMPORTANT: This migration is ADDITIVE ONLY - it does NOT delete any data!
-- - All existing tables are preserved
-- - New columns are added with IF NOT EXISTS
-- - New tables are created with IF NOT EXISTS
-- - No DROP TABLE or DELETE statements
--
-- Run this AFTER backing up your data (recommended, not required)
--
-- Changes:
-- 1. Creates new `locations` table as the foundation
-- 2. Adds location_id FKs to mockup_frames, mockup_usage
-- 3. Creates junction tables: proposal_locations, bo_locations
-- 4. Adds location_occupations for inventory management
-- 5. Adds rate_cards for location pricing
-- 6. Adds file storage tables: documents, mockup_files, proposal_files, location_photos
-- 7. Updates bo_approval_workflows with more statuses
-- =============================================================================

-- =============================================================================
-- STEP 1: CREATE LOCATIONS TABLE (The Foundation)
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

CREATE INDEX IF NOT EXISTS idx_locations_key ON locations(location_key);
CREATE INDEX IF NOT EXISTS idx_locations_type ON locations(display_type);
CREATE INDEX IF NOT EXISTS idx_locations_series ON locations(series);
CREATE INDEX IF NOT EXISTS idx_locations_active ON locations(is_active);
CREATE INDEX IF NOT EXISTS idx_locations_city ON locations(city);

-- =============================================================================
-- STEP 2: ADD location_id TO MOCKUP TABLES
-- =============================================================================

-- Add location_id to mockup_frames
ALTER TABLE mockup_frames
ADD COLUMN IF NOT EXISTS location_id BIGINT REFERENCES locations(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_mockup_frames_location_id ON mockup_frames(location_id);

-- Add location_id to mockup_usage
ALTER TABLE mockup_usage
ADD COLUMN IF NOT EXISTS location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_mockup_usage_location_id ON mockup_usage(location_id);

-- =============================================================================
-- STEP 3: CREATE PROPOSAL_LOCATIONS JUNCTION TABLE
-- =============================================================================
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

CREATE INDEX IF NOT EXISTS idx_proposal_locations_proposal ON proposal_locations(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_locations_location ON proposal_locations(location_id);
CREATE INDEX IF NOT EXISTS idx_proposal_locations_key ON proposal_locations(location_key);

-- =============================================================================
-- STEP 4: CREATE BO_LOCATIONS JUNCTION TABLE
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

CREATE INDEX IF NOT EXISTS idx_bo_locations_bo ON bo_locations(bo_id);
CREATE INDEX IF NOT EXISTS idx_bo_locations_location ON bo_locations(location_id);
CREATE INDEX IF NOT EXISTS idx_bo_locations_dates ON bo_locations(start_date, end_date);

-- =============================================================================
-- STEP 5: CREATE LOCATION_OCCUPATIONS TABLE (Inventory Management)
-- =============================================================================
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
    notes TEXT,

    -- Prevent overlapping confirmed bookings
    CONSTRAINT no_double_booking EXCLUDE USING gist (
        location_id WITH =,
        daterange(start_date, end_date, '[]') WITH &&
    ) WHERE (status IN ('confirmed', 'live'))
);

CREATE INDEX IF NOT EXISTS idx_occupations_location ON location_occupations(location_id);
CREATE INDEX IF NOT EXISTS idx_occupations_dates ON location_occupations(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_occupations_status ON location_occupations(status);
CREATE INDEX IF NOT EXISTS idx_occupations_client ON location_occupations(client_name);
CREATE INDEX IF NOT EXISTS idx_occupations_bo ON location_occupations(bo_id);

-- =============================================================================
-- STEP 6: CREATE RATE_CARDS TABLE (Location Pricing)
-- =============================================================================
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

CREATE INDEX IF NOT EXISTS idx_rate_cards_location ON rate_cards(location_id);
CREATE INDEX IF NOT EXISTS idx_rate_cards_valid ON rate_cards(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_rate_cards_active ON rate_cards(is_active);

-- =============================================================================
-- STEP 7: FILE STORAGE - Documents Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,

    -- Ownership
    user_id TEXT NOT NULL,

    -- File info
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size BIGINT,
    file_extension TEXT,

    -- Storage location
    storage_provider TEXT NOT NULL DEFAULT 'local' CHECK (storage_provider IN ('local', 'supabase', 's3')),
    storage_bucket TEXT NOT NULL DEFAULT 'uploads',
    storage_key TEXT NOT NULL,

    -- Classification
    document_type TEXT CHECK (document_type IN (
        'bo_pdf', 'bo_image', 'bo_excel', 'creative', 'contract', 'invoice', 'other'
    )),

    -- Links
    bo_id BIGINT REFERENCES booking_orders(id) ON DELETE SET NULL,
    proposal_id BIGINT REFERENCES proposals_log(id) ON DELETE SET NULL,

    -- Status
    is_processed BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_documents_file_id ON documents(file_id);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_bo ON documents(bo_id);
CREATE INDEX IF NOT EXISTS idx_documents_proposal ON documents(proposal_id);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at);

-- =============================================================================
-- STEP 8: FILE STORAGE - Mockup Files Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS mockup_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,

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
    storage_key TEXT NOT NULL,

    -- Mockup details
    time_of_day TEXT NOT NULL DEFAULT 'day',
    finish TEXT NOT NULL DEFAULT 'gold',
    photo_filename TEXT,

    -- Creative source
    creative_type TEXT CHECK (creative_type IN ('uploaded', 'ai_generated')),
    creative_file_id TEXT,
    ai_prompt TEXT,

    -- Output
    output_format TEXT DEFAULT 'png',
    width INTEGER,
    height INTEGER,

    -- Status
    is_deleted BOOLEAN DEFAULT false,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_mockup_files_file_id ON mockup_files(file_id);
CREATE INDEX IF NOT EXISTS idx_mockup_files_user ON mockup_files(user_id);
CREATE INDEX IF NOT EXISTS idx_mockup_files_location ON mockup_files(location_id);
CREATE INDEX IF NOT EXISTS idx_mockup_files_location_key ON mockup_files(location_key);
CREATE INDEX IF NOT EXISTS idx_mockup_files_created ON mockup_files(created_at);

-- =============================================================================
-- STEP 9: FILE STORAGE - Proposal Files Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS proposal_files (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,

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
    storage_key TEXT NOT NULL,

    -- Proposal details (snapshot)
    client_name TEXT,
    package_type TEXT,
    location_count INTEGER,

    -- Version tracking
    version INTEGER DEFAULT 1,
    is_latest BOOLEAN DEFAULT true,

    -- Status
    is_deleted BOOLEAN DEFAULT false,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_proposal_files_file_id ON proposal_files(file_id);
CREATE INDEX IF NOT EXISTS idx_proposal_files_user ON proposal_files(user_id);
CREATE INDEX IF NOT EXISTS idx_proposal_files_proposal ON proposal_files(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_files_created ON proposal_files(created_at);

-- =============================================================================
-- STEP 10: FILE STORAGE - Location Photos Table
-- =============================================================================
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
    file_path TEXT NOT NULL,
    file_size BIGINT,
    width INTEGER,
    height INTEGER,

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    notes TEXT,

    CONSTRAINT location_photos_unique UNIQUE (location_key, time_of_day, finish, filename)
);

CREATE INDEX IF NOT EXISTS idx_location_photos_location ON location_photos(location_id);
CREATE INDEX IF NOT EXISTS idx_location_photos_key ON location_photos(location_key);
CREATE INDEX IF NOT EXISTS idx_location_photos_variant ON location_photos(time_of_day, finish);

-- =============================================================================
-- STEP 10B: ADD deleted_at AND file_hash COLUMNS TO FILE TABLES
-- =============================================================================
-- These columns support:
-- - deleted_at: Proper soft-delete tracking (when was it deleted)
-- - file_hash: SHA256 hash for integrity checking and deduplication

-- Documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(is_deleted) WHERE is_deleted = false;

-- Mockup files table
ALTER TABLE mockup_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE mockup_files ADD COLUMN IF NOT EXISTS file_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_mockup_files_hash ON mockup_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_mockup_files_active ON mockup_files(is_deleted) WHERE is_deleted = false;

-- Proposal files table
ALTER TABLE proposal_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE proposal_files ADD COLUMN IF NOT EXISTS file_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_proposal_files_hash ON proposal_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_proposal_files_active ON proposal_files(is_deleted) WHERE is_deleted = false;

-- =============================================================================
-- STEP 11: UPDATE BO_APPROVAL_WORKFLOWS (Enhanced statuses)
-- =============================================================================
-- Drop old constraint if exists
ALTER TABLE bo_approval_workflows
DROP CONSTRAINT IF EXISTS bo_approval_workflows_status_check;

-- Add new constraint with more granular statuses
ALTER TABLE bo_approval_workflows
ADD CONSTRAINT bo_approval_workflows_status_check
CHECK (status IN (
    'pending',
    'coordinator_approved',
    'coordinator_rejected',
    'hos_approved',
    'hos_rejected',
    'cancelled',
    'completed'
));

-- Add bo_id link if not exists
ALTER TABLE bo_approval_workflows
ADD COLUMN IF NOT EXISTS bo_id BIGINT REFERENCES booking_orders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_bo_workflows_bo ON bo_approval_workflows(bo_id);

-- =============================================================================
-- STEP 12: TRIGGERS FOR UPDATED_AT
-- =============================================================================

-- Locations trigger
DROP TRIGGER IF EXISTS update_locations_updated_at ON locations;
CREATE TRIGGER update_locations_updated_at
    BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Location occupations trigger
DROP TRIGGER IF EXISTS update_occupations_updated_at ON location_occupations;
CREATE TRIGGER update_occupations_updated_at
    BEFORE UPDATE ON location_occupations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- STEP 13: ROW LEVEL SECURITY
-- =============================================================================
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to locations" ON locations FOR ALL USING (true);

ALTER TABLE proposal_locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposal_locations" ON proposal_locations FOR ALL USING (true);

ALTER TABLE bo_locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to bo_locations" ON bo_locations FOR ALL USING (true);

ALTER TABLE location_occupations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to location_occupations" ON location_occupations FOR ALL USING (true);

ALTER TABLE rate_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to rate_cards" ON rate_cards FOR ALL USING (true);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to documents" ON documents FOR ALL USING (true);

ALTER TABLE mockup_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to mockup_files" ON mockup_files FOR ALL USING (true);

ALTER TABLE proposal_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to proposal_files" ON proposal_files FOR ALL USING (true);

ALTER TABLE location_photos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access to location_photos" ON location_photos FOR ALL USING (true);

-- =============================================================================
-- STEP 14: GRANTS
-- =============================================================================
GRANT ALL ON locations TO service_role;
GRANT ALL ON proposal_locations TO service_role;
GRANT ALL ON bo_locations TO service_role;
GRANT ALL ON location_occupations TO service_role;
GRANT ALL ON rate_cards TO service_role;
GRANT ALL ON documents TO service_role;
GRANT ALL ON mockup_files TO service_role;
GRANT ALL ON proposal_files TO service_role;
GRANT ALL ON location_photos TO service_role;

GRANT USAGE, SELECT ON SEQUENCE locations_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE proposal_locations_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE bo_locations_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE location_occupations_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE rate_cards_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE documents_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE mockup_files_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE proposal_files_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE location_photos_id_seq TO service_role;

-- =============================================================================
-- STEP 15: CONVENIENCE VIEWS
-- =============================================================================

-- Digital locations with current rate
CREATE OR REPLACE VIEW digital_locations_with_rates AS
SELECT
    l.id, l.location_key, l.display_name, l.series,
    l.height, l.width, l.number_of_faces,
    l.spot_duration, l.loop_duration, l.sov_percent,
    COALESCE(r.upload_fee, l.upload_fee) as upload_fee,
    r.weekly_rate,
    l.city, l.area,
    l.template_path, l.is_active
FROM locations l
LEFT JOIN rate_cards r ON l.id = r.location_id
    AND r.is_active = true
    AND r.valid_from <= CURRENT_DATE
    AND (r.valid_to IS NULL OR r.valid_to >= CURRENT_DATE)
WHERE l.display_type = 'digital' AND l.is_active = true
ORDER BY l.series, l.display_name;

-- Static locations with current rate
CREATE OR REPLACE VIEW static_locations_with_rates AS
SELECT
    l.id, l.location_key, l.display_name, l.series,
    l.height, l.width, l.number_of_faces,
    r.weekly_rate,
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
    o.status
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

-- =============================================================================
-- MIGRATION COMPLETE!
-- =============================================================================
-- Next steps:
-- 1. Run the seed_locations.py script to populate locations from metadata.txt files
-- 2. Run the migrate_existing_data.py script to populate junction tables
-- =============================================================================
