-- ============================================================================
-- Supabase Schema for Proposal Bot
-- ============================================================================
-- Run this SQL in Supabase Dashboard > SQL Editor
--
-- To modify later:
--   - ALTER TABLE table_name ADD COLUMN column_name TYPE;
--   - ALTER TABLE table_name DROP COLUMN column_name;
--   - DROP TABLE table_name; (then recreate)
-- ============================================================================

-- Users table (syncs with Supabase Auth)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    avatar_url TEXT,
    is_active BIGINT NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Roles for RBAC
CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_system BIGINT NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);

-- User-Role assignments
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role_id BIGINT NOT NULL,
    granted_by TEXT,
    granted_at TEXT NOT NULL,
    expires_at TEXT,
    CONSTRAINT user_roles_user_id_role_id_unique UNIQUE (user_id, role_id)
);
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);

-- Permissions
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT permissions_resource_action_unique UNIQUE (resource, action)
);
CREATE INDEX IF NOT EXISTS idx_permissions_name ON permissions(name);
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON permissions(resource);

-- Role-Permission assignments
CREATE TABLE IF NOT EXISTS role_permissions (
    id BIGSERIAL PRIMARY KEY,
    role_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    granted_at TEXT NOT NULL,
    CONSTRAINT role_permissions_role_id_permission_id_unique UNIQUE (role_id, permission_id)
);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions(permission_id);

-- Audit log for tracking actions
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details_json TEXT,
    ip_address TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);

-- Proposals log
CREATE TABLE IF NOT EXISTS proposals_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    submitted_by TEXT NOT NULL,
    client_name TEXT NOT NULL,
    date_generated TEXT NOT NULL,
    package_type TEXT NOT NULL,
    locations TEXT NOT NULL,
    total_amount TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_user ON proposals_log(user_id);

-- Mockup frame configurations
CREATE TABLE IF NOT EXISTS mockup_frames (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    location_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL DEFAULT 'day',
    finish TEXT NOT NULL DEFAULT 'gold',
    photo_filename TEXT NOT NULL,
    frames_data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    config_json TEXT,
    CONSTRAINT mockup_frames_location_key_time_of_day_finish_photo_filename_unique UNIQUE (location_key, time_of_day, finish, photo_filename)
);
CREATE INDEX IF NOT EXISTS idx_mockup_frames_user ON mockup_frames(user_id);

-- Mockup usage analytics
CREATE TABLE IF NOT EXISTS mockup_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    generated_at TEXT NOT NULL,
    location_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    finish TEXT NOT NULL,
    photo_used TEXT NOT NULL,
    creative_type TEXT NOT NULL,
    ai_prompt TEXT,
    template_selected BIGINT NOT NULL DEFAULT 0,
    success BIGINT NOT NULL DEFAULT 1,
    user_ip TEXT,
    CONSTRAINT mockup_usage_creative_type_check CHECK (creative_type IN ('uploaded', 'ai_generated'))
);
CREATE INDEX IF NOT EXISTS idx_mockup_usage_user ON mockup_usage(user_id);

-- Booking orders
CREATE TABLE IF NOT EXISTS booking_orders (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    bo_ref TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL,
    original_file_path TEXT NOT NULL,
    original_file_type TEXT NOT NULL,
    original_file_size BIGINT,
    original_filename TEXT,
    parsed_excel_path TEXT NOT NULL,
    bo_number TEXT,
    bo_date TEXT,
    client TEXT,
    agency TEXT,
    brand_campaign TEXT,
    category TEXT,
    asset TEXT,
    net_pre_vat DOUBLE PRECISION,
    vat_value DOUBLE PRECISION,
    gross_amount DOUBLE PRECISION,
    sla_pct DOUBLE PRECISION,
    payment_terms TEXT,
    sales_person TEXT,
    commission_pct DOUBLE PRECISION,
    notes TEXT,
    locations_json TEXT,
    extraction_method TEXT,
    extraction_confidence TEXT,
    warnings_json TEXT,
    missing_fields_json TEXT,
    vat_calc DOUBLE PRECISION,
    gross_calc DOUBLE PRECISION,
    sla_deduction DOUBLE PRECISION,
    net_excl_sla_calc DOUBLE PRECISION,
    parsed_at TEXT NOT NULL,
    parsed_by TEXT,
    source_classification TEXT,
    classification_confidence TEXT,
    needs_review BIGINT DEFAULT 0,
    search_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_booking_orders_user ON booking_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_booking_orders_bo_ref ON booking_orders(bo_ref);
CREATE INDEX IF NOT EXISTS idx_booking_orders_company ON booking_orders(company);
CREATE INDEX IF NOT EXISTS idx_booking_orders_client ON booking_orders(client);
CREATE INDEX IF NOT EXISTS idx_booking_orders_parsed_at ON booking_orders(parsed_at);

-- Booking order approval workflows
CREATE TABLE IF NOT EXISTS bo_approval_workflows (
    workflow_id TEXT PRIMARY KEY,
    workflow_data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bo_workflows_updated ON bo_approval_workflows(updated_at);

-- API keys for external integrations
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    scopes_json TEXT NOT NULL,
    rate_limit BIGINT,
    is_active BIGINT NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by TEXT,
    expires_at TEXT,
    last_used_at TEXT,
    last_rotated_at TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_name ON api_keys(name);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON api_keys(created_by);

-- API key usage tracking
CREATE TABLE IF NOT EXISTS api_key_usage (
    id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT NOT NULL,
    timestamp TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code BIGINT,
    ip_address TEXT,
    user_agent TEXT,
    response_time_ms BIGINT,
    request_size BIGINT,
    response_size BIGINT
);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_timestamp ON api_key_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_endpoint ON api_key_usage(endpoint);

-- AI costs tracking
CREATE TABLE IF NOT EXISTS ai_costs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    call_type TEXT NOT NULL,
    workflow TEXT,
    model TEXT NOT NULL,
    user_id TEXT,
    context TEXT,
    input_tokens BIGINT,
    cached_input_tokens BIGINT DEFAULT 0,
    output_tokens BIGINT,
    reasoning_tokens BIGINT DEFAULT 0,
    total_tokens BIGINT,
    input_cost DOUBLE PRECISION,
    output_cost DOUBLE PRECISION,
    reasoning_cost DOUBLE PRECISION DEFAULT 0,
    total_cost DOUBLE PRECISION,
    metadata_json TEXT,
    CONSTRAINT ai_costs_call_type_check CHECK (call_type IN ('classification', 'parsing', 'coordinator_thread', 'main_llm', 'mockup_analysis', 'image_generation', 'bo_edit', 'other')),
    CONSTRAINT ai_costs_workflow_check CHECK (workflow IN ('mockup_upload', 'mockup_ai', 'bo_parsing', 'bo_editing', 'bo_revision', 'proposal_generation', 'general_chat', 'location_management') OR workflow IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_ai_costs_timestamp ON ai_costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_costs_call_type ON ai_costs(call_type);
CREATE INDEX IF NOT EXISTS idx_ai_costs_user ON ai_costs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_costs_workflow ON ai_costs(workflow);

-- ============================================================================
-- Insert default roles
-- ============================================================================
INSERT INTO roles (name, description, is_system, created_at) VALUES
    ('admin', 'Full system access', 1, NOW()::TEXT),
    ('user', 'Standard user access', 1, NOW()::TEXT),
    ('viewer', 'Read-only access', 1, NOW()::TEXT)
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- Done! Your database is ready.
-- ============================================================================
