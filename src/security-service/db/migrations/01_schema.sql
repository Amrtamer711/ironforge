-- =============================================================================
-- SECURITY SERVICE - SUPABASE SCHEMA
-- =============================================================================
-- This service tracks:
--   - Audit logs (all user/service actions)
--   - API key management and usage
--   - Rate limiting state
--   - Security events and incidents
--
-- User/Profile data is read from UI Supabase (read-only)
-- =============================================================================

-- =============================================================================
-- AUDIT LOGS
-- Comprehensive logging of all user and service actions
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Actor (who performed the action)
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'service', 'system', 'api_key')),
    actor_id TEXT,                      -- User ID, service name, or API key ID
    actor_email TEXT,
    actor_ip TEXT,

    -- Action performed
    service TEXT NOT NULL,              -- Which service: unified-ui, sales-module, asset-management, security-service
    action TEXT NOT NULL,               -- What action: create, update, delete, login, etc.

    -- Resource affected
    resource_type TEXT,                 -- proposal, booking_order, user, api_key, etc.
    resource_id TEXT,

    -- Outcome
    result TEXT NOT NULL DEFAULT 'success' CHECK (result IN ('success', 'failure', 'error')),
    error_message TEXT,

    -- Request details
    request_id TEXT,
    request_method TEXT,                -- GET, POST, PUT, DELETE
    request_path TEXT,
    request_body JSONB,                 -- Careful with PII
    response_status INTEGER,
    duration_ms INTEGER,

    -- Additional context
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_id, actor_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_service_action ON audit_logs(service, action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_result ON audit_logs(result);

-- =============================================================================
-- API KEYS
-- Manage API keys for service-to-service and external integrations
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,

    -- Key identification
    key_hash TEXT NOT NULL UNIQUE,      -- SHA-256 hash of the key
    key_prefix TEXT NOT NULL,           -- First 8 chars for display (e.g., "sk_live_...")
    name TEXT NOT NULL,
    description TEXT,

    -- Ownership
    created_by TEXT,                    -- User ID who created it

    -- Permissions
    scopes TEXT[] DEFAULT '{}',         -- Allowed scopes: ['read:proposals', 'write:orders']
    allowed_services TEXT[],            -- Restrict to specific services
    allowed_ips TEXT[],                 -- IP whitelist

    -- Rate limiting
    rate_limit_per_minute INTEGER DEFAULT 100,
    rate_limit_per_day INTEGER DEFAULT 10000,

    -- Status
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMPTZ,

    -- Tracking
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Additional context
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON api_keys(created_by);

-- =============================================================================
-- API KEY USAGE
-- Track API key usage for analytics and billing
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_key_usage (
    id BIGSERIAL PRIMARY KEY,
    key_id BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Request details
    service TEXT NOT NULL,              -- Which service was called
    endpoint TEXT,                      -- API endpoint
    method TEXT,                        -- HTTP method
    status_code INTEGER,

    -- Client info
    ip_address TEXT,
    user_agent TEXT,

    -- Performance
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage(key_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_timestamp ON api_key_usage(timestamp DESC);

-- =============================================================================
-- RATE LIMIT STATE
-- Track rate limiting buckets (sliding window)
-- =============================================================================
CREATE TABLE IF NOT EXISTS rate_limit_state (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL,                  -- Rate limit key (user_id, api_key, ip, etc.)
    window_start TIMESTAMPTZ NOT NULL,  -- Window start time (truncated to minute)
    request_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique per key + window
    CONSTRAINT rate_limit_state_unique UNIQUE (key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_key_window ON rate_limit_state(key, window_start DESC);
CREATE INDEX IF NOT EXISTS idx_rate_limit_cleanup ON rate_limit_state(window_start);

-- =============================================================================
-- SECURITY EVENTS
-- Track security incidents and anomalies
-- =============================================================================
CREATE TABLE IF NOT EXISTS security_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Event classification
    event_type TEXT NOT NULL CHECK (event_type IN (
        'authentication_failure',
        'authorization_failure',
        'rate_limit_exceeded',
        'suspicious_activity',
        'data_breach_attempt',
        'invalid_token',
        'api_key_compromised',
        'unusual_access_pattern',
        'brute_force_attempt',
        'other'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    service TEXT NOT NULL,
    message TEXT NOT NULL,

    -- Actor
    actor_type TEXT,
    actor_id TEXT,
    ip_address TEXT,

    -- Details
    details JSONB DEFAULT '{}',

    -- Resolution tracking
    is_resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON security_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_type_severity ON security_events(event_type, severity);
CREATE INDEX IF NOT EXISTS idx_security_events_unresolved ON security_events(is_resolved, severity) WHERE is_resolved = false;
CREATE INDEX IF NOT EXISTS idx_security_events_service ON security_events(service);

-- =============================================================================
-- TRIGGERS
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_api_keys_updated_at BEFORE UPDATE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_rate_limit_state_updated_at BEFORE UPDATE ON rate_limit_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "Service role full access" ON audit_logs FOR ALL USING (true);
CREATE POLICY "Service role full access" ON api_keys FOR ALL USING (true);
CREATE POLICY "Service role full access" ON api_key_usage FOR ALL USING (true);
CREATE POLICY "Service role full access" ON rate_limit_state FOR ALL USING (true);
CREATE POLICY "Service role full access" ON security_events FOR ALL USING (true);

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Recent audit activity summary
CREATE OR REPLACE VIEW recent_audit_activity AS
SELECT
    service,
    action,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE result = 'success') as success_count,
    COUNT(*) FILTER (WHERE result = 'failure') as failure_count,
    MAX(timestamp) as last_occurrence
FROM audit_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY service, action
ORDER BY count DESC;

-- Active API keys summary
CREATE OR REPLACE VIEW active_api_keys_summary AS
SELECT
    ak.id,
    ak.name,
    ak.key_prefix,
    ak.created_by,
    ak.created_at,
    ak.last_used_at,
    COUNT(aku.id) as total_requests,
    COUNT(aku.id) FILTER (WHERE aku.timestamp > NOW() - INTERVAL '24 hours') as requests_last_24h
FROM api_keys ak
LEFT JOIN api_key_usage aku ON ak.id = aku.key_id
WHERE ak.is_active = true AND (ak.expires_at IS NULL OR ak.expires_at > NOW())
GROUP BY ak.id, ak.name, ak.key_prefix, ak.created_by, ak.created_at, ak.last_used_at
ORDER BY ak.last_used_at DESC NULLS LAST;

-- Unresolved security events
CREATE OR REPLACE VIEW unresolved_security_events AS
SELECT
    id,
    timestamp,
    event_type,
    severity,
    service,
    message,
    actor_id,
    ip_address
FROM security_events
WHERE is_resolved = false
ORDER BY
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END,
    timestamp DESC;

-- =============================================================================
-- COMMENTS
-- =============================================================================
COMMENT ON TABLE audit_logs IS 'Comprehensive audit trail of all user and service actions';
COMMENT ON TABLE api_keys IS 'API key management for service-to-service and external integrations';
COMMENT ON TABLE api_key_usage IS 'Usage tracking and analytics for API keys';
COMMENT ON TABLE rate_limit_state IS 'Sliding window rate limiting buckets';
COMMENT ON TABLE security_events IS 'Security incidents and anomalies requiring investigation';
