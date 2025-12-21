-- ============================================================================
-- SECURITY SUPABASE SCHEMA
-- Centralized security data for all services
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- AUDIT LOGS
-- Compliance-ready audit trail for all services
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- When
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who
    actor_type TEXT NOT NULL,  -- 'user', 'service', 'system', 'anonymous'
    actor_id TEXT,             -- user UUID or service name
    actor_email TEXT,          -- for user actors
    actor_ip TEXT,             -- client IP address

    -- What
    service TEXT NOT NULL,     -- 'sales-module', 'asset-management', 'unified-ui'
    action TEXT NOT NULL,      -- 'create', 'read', 'update', 'delete', 'login', 'logout'
    resource_type TEXT,        -- 'location', 'proposal', 'user', etc.
    resource_id TEXT,          -- specific resource identifier

    -- Result
    result TEXT NOT NULL DEFAULT 'success',  -- 'success', 'denied', 'error'
    error_message TEXT,        -- if result is 'error'

    -- Context
    request_id TEXT,           -- correlation ID
    request_method TEXT,       -- 'GET', 'POST', etc.
    request_path TEXT,         -- '/api/v1/locations/123'
    request_body JSONB,        -- sanitized request body (no secrets)
    response_status INT,       -- HTTP status code
    duration_ms INT,           -- request duration

    -- Additional metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_service ON audit_logs(service);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_result ON audit_logs(result);
CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs(request_id);

-- Composite index for compliance queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_compliance ON audit_logs(actor_id, timestamp DESC, action);

-- ============================================================================
-- API KEYS
-- Centralized API key management
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Key identification
    key_hash TEXT NOT NULL UNIQUE,  -- SHA-256 hash of the key
    key_prefix TEXT NOT NULL,       -- First 8 chars for identification (sk_abc123...)
    name TEXT NOT NULL,             -- Human-readable name
    description TEXT,

    -- Ownership
    created_by TEXT,                -- User ID who created
    organization TEXT,              -- Optional org grouping

    -- Permissions
    scopes TEXT[] NOT NULL DEFAULT '{}',  -- ['read', 'write', 'admin']
    allowed_services TEXT[] DEFAULT NULL, -- NULL = all services
    allowed_ips TEXT[] DEFAULT NULL,      -- NULL = all IPs

    -- Limits
    rate_limit_per_minute INT DEFAULT 100,
    rate_limit_per_day INT DEFAULT 10000,

    -- Lifecycle
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_used_ip TEXT,
    use_count BIGINT DEFAULT 0,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON api_keys(created_by);

-- ============================================================================
-- API KEY USAGE
-- Track API key usage for analytics and billing
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_key_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,

    -- Request info
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    service TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INT NOT NULL,

    -- Client info
    ip_address TEXT,
    user_agent TEXT,

    -- Performance
    duration_ms INT,

    -- For time-series queries
    hour_bucket TIMESTAMPTZ GENERATED ALWAYS AS (date_trunc('hour', timestamp)) STORED
);

-- Indexes for usage analytics
CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage(key_id);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_timestamp ON api_key_usage(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_hour ON api_key_usage(hour_bucket);

-- ============================================================================
-- SERVICE REGISTRY
-- Track authorized services and their permissions
-- ============================================================================

CREATE TABLE IF NOT EXISTS service_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Service identification
    service_name TEXT NOT NULL UNIQUE,  -- 'sales-module', 'asset-management'
    display_name TEXT NOT NULL,
    description TEXT,

    -- Service details
    base_url TEXT,                      -- 'http://sales-module:8000'
    health_endpoint TEXT DEFAULT '/health',
    version TEXT,

    -- Permissions
    allowed_to_call TEXT[] DEFAULT '{}',  -- Services this one can call
    can_be_called_by TEXT[] DEFAULT '{}', -- Services that can call this one

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_heartbeat TIMESTAMPTZ,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- RATE LIMIT STATE
-- Distributed rate limiting (alternative to Redis)
-- ============================================================================

CREATE TABLE IF NOT EXISTS rate_limit_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Rate limit key (e.g., "user:123:endpoint:/api/locations")
    key TEXT NOT NULL,

    -- Sliding window state
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT NOT NULL DEFAULT 1,

    -- Metadata
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint for upsert
    UNIQUE(key, window_start)
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_rate_limit_key ON rate_limit_state(key);
CREATE INDEX IF NOT EXISTS idx_rate_limit_window ON rate_limit_state(window_start);

-- ============================================================================
-- SECURITY EVENTS
-- Track security incidents and alerts
-- ============================================================================

CREATE TABLE IF NOT EXISTS security_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Event classification
    event_type TEXT NOT NULL,   -- 'failed_login', 'rate_limit_exceeded', 'invalid_token', etc.
    severity TEXT NOT NULL,     -- 'info', 'warning', 'error', 'critical'

    -- Context
    service TEXT NOT NULL,
    actor_type TEXT,
    actor_id TEXT,
    ip_address TEXT,

    -- Details
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',

    -- Resolution
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,

    -- Timestamps
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity);
CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON security_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_unresolved ON security_events(is_resolved) WHERE is_resolved = FALSE;

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;

-- Service role has full access (used by backend services)
CREATE POLICY "Service role full access on audit_logs" ON audit_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on api_keys" ON api_keys
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on api_key_usage" ON api_key_usage
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on service_registry" ON service_registry
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on rate_limit_state" ON rate_limit_state
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on security_events" ON security_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Cleanup function for expired rate limit windows
CREATE OR REPLACE FUNCTION cleanup_rate_limit_state() RETURNS void AS $$
BEGIN
    DELETE FROM rate_limit_state
    WHERE window_start < NOW() - INTERVAL '5 minutes';
END;
$$ LANGUAGE plpgsql;

-- Function to increment API key usage count
CREATE OR REPLACE FUNCTION increment_api_key_usage(key_uuid UUID)
RETURNS BIGINT AS $$
DECLARE
    new_count BIGINT;
BEGIN
    UPDATE api_keys
    SET use_count = use_count + 1
    WHERE id = key_uuid
    RETURNING use_count INTO new_count;
    RETURN new_count;
END;
$$ LANGUAGE plpgsql;
