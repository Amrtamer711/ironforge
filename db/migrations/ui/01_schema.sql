-- =============================================================================
-- UI SUPABASE SCHEMA - CONSOLIDATED
-- =============================================================================
-- Run this in: UI-Module-Dev and UI-Module-Prod Supabase SQL Editor
--
-- This is the COMPLETE UI database schema including:
-- - User management and preferences
-- - Enterprise RBAC (profiles, permissions, teams)
-- - Multi-company support with hierarchy
-- - Channel identity tracking (Slack, Teams, etc.)
-- - Module access control
-- - Audit logging
-- - API key management
--
-- Company Hierarchy:
--   MMG (root) - sees everything
--   ├── Backlite (group) - sees all Backlite verticals
--   │   ├── Backlite Dubai
--   │   ├── Backlite UK
--   │   └── Backlite Abu Dhabi
--   └── Viola
--
-- NOTE: auth.users is managed automatically by Supabase Auth - do NOT create it
-- =============================================================================

-- =============================================================================
-- UTILITY FUNCTIONS
-- =============================================================================

-- Auto-update timestamp function (used by multiple tables)
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- USER PREFERENCES (linked to Supabase Auth)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    avatar_url TEXT,
    theme TEXT DEFAULT 'system' CHECK (theme IN ('light', 'dark', 'system')),
    language TEXT DEFAULT 'en',
    timezone TEXT DEFAULT 'Asia/Dubai',
    notifications_enabled BOOLEAN DEFAULT true,
    email_notifications BOOLEAN DEFAULT true,
    preferences_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_preferences_created_at ON user_preferences(created_at);

-- Auto-create preferences when user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_preferences (id, display_name, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- =============================================================================
-- LEVEL 1: PROFILES (Base Role Templates)
-- =============================================================================
CREATE TABLE IF NOT EXISTS profiles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);
CREATE INDEX IF NOT EXISTS idx_profiles_system ON profiles(is_system);

CREATE TABLE IF NOT EXISTS profile_permissions (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT profile_permissions_unique UNIQUE (profile_id, permission)
);

CREATE INDEX IF NOT EXISTS idx_profile_permissions_profile ON profile_permissions(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_permissions_permission ON profile_permissions(permission);

-- =============================================================================
-- LEVEL 2: PERMISSION SETS (Additive Permissions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS permission_sets (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permission_sets_name ON permission_sets(name);
CREATE INDEX IF NOT EXISTS idx_permission_sets_active ON permission_sets(is_active);

CREATE TABLE IF NOT EXISTS permission_set_permissions (
    id BIGSERIAL PRIMARY KEY,
    permission_set_id BIGINT NOT NULL REFERENCES permission_sets(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT permission_set_permissions_unique UNIQUE (permission_set_id, permission)
);

CREATE INDEX IF NOT EXISTS idx_psp_set ON permission_set_permissions(permission_set_id);
CREATE INDEX IF NOT EXISTS idx_psp_permission ON permission_set_permissions(permission);

-- =============================================================================
-- LEVEL 3: TEAMS & HIERARCHY
-- =============================================================================
CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    parent_team_id BIGINT REFERENCES teams(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name);
CREATE INDEX IF NOT EXISTS idx_teams_parent ON teams(parent_team_id);
CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(is_active);

-- =============================================================================
-- COMPANIES TABLE (Multi-Company Support)
-- =============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id BIGINT REFERENCES companies(id) ON DELETE SET NULL,
    country TEXT,
    currency TEXT DEFAULT 'AED',
    timezone TEXT DEFAULT 'Asia/Dubai',
    config JSONB DEFAULT '{}',
    is_group BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_code ON companies(code);
CREATE INDEX IF NOT EXISTS idx_companies_parent ON companies(parent_id);
CREATE INDEX IF NOT EXISTS idx_companies_active ON companies(is_active);

-- =============================================================================
-- USERS TABLE (Extended for Enterprise RBAC + Companies)
-- =============================================================================
-- NOTE: Not using IF NOT EXISTS because the table structure must be exact.
-- Run 00_reset.sql first if this errors with "relation already exists"
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
    manager_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    primary_company_id BIGINT REFERENCES companies(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_profile ON users(profile_id);
CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_company ON users(primary_company_id);

-- Sync users table from auth.users on insert/update
CREATE OR REPLACE FUNCTION public.sync_user_from_auth()
RETURNS TRIGGER AS $$
DECLARE
    default_profile_id BIGINT;
    existing_profile_id BIGINT;
BEGIN
    SELECT profile_id INTO existing_profile_id
    FROM public.users
    WHERE id = NEW.id::TEXT;

    IF existing_profile_id IS NULL THEN
        SELECT id INTO default_profile_id
        FROM public.profiles
        WHERE name = 'sales_user';
    END IF;

    INSERT INTO public.users (id, email, name, avatar_url, profile_id, created_at, updated_at)
    VALUES (
        NEW.id::TEXT,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        NEW.raw_user_meta_data->>'avatar_url',
        default_profile_id,
        NOW(),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_sync ON auth.users;
CREATE TRIGGER on_auth_user_sync
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.sync_user_from_auth();

-- =============================================================================
-- USER-COMPANY ASSIGNMENTS (Many-to-Many)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_companies (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT false,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT user_companies_unique UNIQUE (user_id, company_id)
);

CREATE INDEX IF NOT EXISTS idx_user_companies_user ON user_companies(user_id);
CREATE INDEX IF NOT EXISTS idx_user_companies_company ON user_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_user_companies_primary ON user_companies(is_primary) WHERE is_primary = true;

-- User-Permission Set assignments
CREATE TABLE IF NOT EXISTS user_permission_sets (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_set_id BIGINT NOT NULL REFERENCES permission_sets(id) ON DELETE CASCADE,
    granted_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    CONSTRAINT user_permission_sets_unique UNIQUE (user_id, permission_set_id)
);

CREATE INDEX IF NOT EXISTS idx_ups_user ON user_permission_sets(user_id);
CREATE INDEX IF NOT EXISTS idx_ups_set ON user_permission_sets(permission_set_id);
CREATE INDEX IF NOT EXISTS idx_ups_expires ON user_permission_sets(expires_at);
CREATE INDEX IF NOT EXISTS idx_ups_user_expires ON user_permission_sets(user_id, expires_at);

-- Team membership
CREATE TABLE IF NOT EXISTS team_members (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'leader')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT team_members_unique UNIQUE (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);
CREATE INDEX IF NOT EXISTS idx_team_members_role ON team_members(role);

-- =============================================================================
-- LEVEL 4: RECORD-LEVEL ACCESS (Sharing)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sharing_rules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    object_type TEXT NOT NULL,
    share_from_type TEXT NOT NULL CHECK (share_from_type IN ('owner', 'profile', 'team')),
    share_from_id TEXT,
    share_to_type TEXT NOT NULL CHECK (share_to_type IN ('profile', 'team', 'all')),
    share_to_id TEXT,
    access_level TEXT NOT NULL CHECK (access_level IN ('read', 'read_write', 'full')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sharing_rules_object ON sharing_rules(object_type);
CREATE INDEX IF NOT EXISTS idx_sharing_rules_active ON sharing_rules(is_active);

CREATE TABLE IF NOT EXISTS record_shares (
    id BIGSERIAL PRIMARY KEY,
    object_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    shared_with_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    shared_with_team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL CHECK (access_level IN ('read', 'read_write', 'full')),
    shared_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    reason TEXT,
    CONSTRAINT record_shares_target CHECK (
        (shared_with_user_id IS NOT NULL AND shared_with_team_id IS NULL) OR
        (shared_with_user_id IS NULL AND shared_with_team_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_record_shares_lookup ON record_shares(object_type, record_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_user ON record_shares(shared_with_user_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_team ON record_shares(shared_with_team_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_expires ON record_shares(expires_at);
CREATE INDEX IF NOT EXISTS idx_record_shares_user_expires ON record_shares(shared_with_user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_record_shares_access_check ON record_shares(object_type, record_id, shared_with_user_id);

-- =============================================================================
-- CHANNEL IDENTITIES (Slack, Teams, etc.)
-- =============================================================================
CREATE TABLE IF NOT EXISTS channel_identities (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,                      -- 'slack', 'teams', 'whatsapp'
    provider_user_id TEXT NOT NULL,              -- Provider's user ID
    provider_team_id TEXT,                       -- Workspace/tenant ID
    email TEXT,
    display_name TEXT,
    real_name TEXT,
    avatar_url TEXT,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    linked_at TIMESTAMPTZ,
    linked_by TEXT,
    is_blocked BOOLEAN DEFAULT FALSE,
    blocked_reason TEXT,
    blocked_at TIMESTAMPTZ,
    blocked_by TEXT,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT channel_identities_unique UNIQUE (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_identities_user_id ON channel_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_channel_identities_email ON channel_identities(email);
CREATE INDEX IF NOT EXISTS idx_channel_identities_provider ON channel_identities(provider);
CREATE INDEX IF NOT EXISTS idx_channel_identities_last_seen ON channel_identities(last_seen_at DESC);

-- =============================================================================
-- SYSTEM SETTINGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
);

-- =============================================================================
-- PERMISSIONS REFERENCE TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    module TEXT NOT NULL,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT permissions_unique UNIQUE (module, resource, action)
);

CREATE INDEX IF NOT EXISTS idx_permissions_name ON permissions(name);
CREATE INDEX IF NOT EXISTS idx_permissions_module ON permissions(module);

-- =============================================================================
-- MODULE ACCESS CONTROL
-- =============================================================================
CREATE TABLE IF NOT EXISTS modules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 0,
    required_permission TEXT,
    config_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_modules_name ON modules(name);
CREATE INDEX IF NOT EXISTS idx_modules_active ON modules(is_active);

CREATE TABLE IF NOT EXISTS user_modules (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module_id BIGINT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT false,
    granted_by TEXT REFERENCES users(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_modules_unique UNIQUE (user_id, module_id)
);

CREATE INDEX IF NOT EXISTS idx_user_modules_user ON user_modules(user_id);
CREATE INDEX IF NOT EXISTS idx_user_modules_module ON user_modules(module_id);

-- =============================================================================
-- INVITE TOKENS
-- =============================================================================
CREATE TABLE IF NOT EXISTS invite_tokens (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    profile_name TEXT,
    permission_set_ids_json TEXT,
    team_id BIGINT REFERENCES teams(id),
    company_id BIGINT REFERENCES companies(id),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by_user_id TEXT,
    is_revoked BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_invite_tokens_token ON invite_tokens(token);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_email ON invite_tokens(email);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_expires ON invite_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_profile ON invite_tokens(profile_name);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_company ON invite_tokens(company_id);

-- =============================================================================
-- AUDIT LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    user_email TEXT,
    action TEXT NOT NULL,
    action_category TEXT NOT NULL DEFAULT 'other' CHECK (action_category IN (
        'auth', 'rbac', 'sharing', 'user_management', 'data_access', 'admin', 'other'
    )),
    resource_type TEXT,
    resource_id TEXT,
    target_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    target_user_email TEXT,
    old_value JSONB,
    new_value JSONB,
    details_json JSONB,
    ip_address TEXT,
    user_agent TEXT,
    request_id TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_category ON audit_log(action_category);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target_user ON audit_log(target_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_success ON audit_log(success);

-- =============================================================================
-- API KEYS
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    scopes_json JSONB NOT NULL,
    rate_limit INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT REFERENCES users(id),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_rotated_at TIMESTAMPTZ,
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);

CREATE TABLE IF NOT EXISTS api_key_usage (
    id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    response_time_ms INTEGER,
    request_size INTEGER,
    response_size INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_timestamp ON api_key_usage(timestamp);

-- =============================================================================
-- HELPER FUNCTIONS: COMPANY ACCESS
-- =============================================================================

-- Get all company IDs a user can access (including children)
CREATE OR REPLACE FUNCTION get_user_accessible_companies(p_user_id TEXT)
RETURNS TABLE(company_id BIGINT) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE user_assigned AS (
        SELECT uc.company_id FROM user_companies uc WHERE uc.user_id = p_user_id
    ),
    company_tree AS (
        SELECT c.id FROM companies c WHERE c.id IN (SELECT ua.company_id FROM user_assigned ua)
        UNION
        SELECT c.id FROM companies c
        INNER JOIN company_tree ct ON c.parent_id = ct.id
    )
    SELECT ct.id FROM company_tree ct;
END;
$$ LANGUAGE plpgsql STABLE;

-- Get accessible schemas (company codes) from assigned company IDs
-- Used by RBAC to expand group companies to their children
CREATE OR REPLACE FUNCTION get_accessible_schemas(p_company_ids bigint[])
RETURNS TABLE (schema_name text) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE company_tree AS (
        -- Base case: directly assigned companies
        SELECT c.id, c.code, c.is_group
        FROM companies c
        WHERE c.id = ANY(p_company_ids)

        UNION

        -- Recursive case: children of group companies (via parent_id)
        SELECT child.id, child.code, child.is_group
        FROM companies child
        INNER JOIN company_tree parent ON child.parent_id = parent.id
        WHERE parent.is_group = true
    )
    -- Only return non-group companies (those with actual data schemas)
    SELECT DISTINCT ct.code AS schema_name
    FROM company_tree ct
    WHERE ct.code IS NOT NULL AND ct.is_group = false;
END;
$$ LANGUAGE plpgsql STABLE;

-- Check if user can access a specific company
CREATE OR REPLACE FUNCTION user_can_access_company(p_user_id TEXT, p_company_id BIGINT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM get_user_accessible_companies(p_user_id) WHERE company_id = p_company_id
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- Get company hierarchy (for breadcrumbs)
CREATE OR REPLACE FUNCTION get_company_hierarchy(p_company_id BIGINT)
RETURNS TABLE(id BIGINT, code TEXT, name TEXT, level INT) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE hierarchy AS (
        SELECT c.id, c.code, c.name, c.parent_id, 0 as level
        FROM companies c WHERE c.id = p_company_id
        UNION ALL
        SELECT c.id, c.code, c.name, c.parent_id, h.level + 1
        FROM companies c INNER JOIN hierarchy h ON c.id = h.parent_id
    )
    SELECT h.id, h.code, h.name, h.level FROM hierarchy h ORDER BY h.level DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- HELPER FUNCTIONS: CHANNEL IDENTITY
-- =============================================================================

-- Record channel user interaction
CREATE OR REPLACE FUNCTION record_channel_interaction(
    p_provider TEXT,
    p_provider_user_id TEXT,
    p_provider_team_id TEXT DEFAULT NULL,
    p_email TEXT DEFAULT NULL,
    p_display_name TEXT DEFAULT NULL,
    p_real_name TEXT DEFAULT NULL,
    p_avatar_url TEXT DEFAULT NULL
)
RETURNS TABLE(
    identity_id BIGINT,
    platform_user_id TEXT,
    is_linked BOOLEAN,
    is_blocked BOOLEAN,
    require_auth BOOLEAN
) AS $$
DECLARE
    v_identity_id BIGINT;
    v_user_id TEXT;
    v_is_blocked BOOLEAN;
    v_require_auth BOOLEAN;
    v_setting_key TEXT;
BEGIN
    v_setting_key := p_provider || '_require_platform_auth';
    SELECT (value)::boolean INTO v_require_auth FROM system_settings WHERE key = v_setting_key;
    v_require_auth := COALESCE(v_require_auth, FALSE);

    INSERT INTO channel_identities (
        provider, provider_user_id, provider_team_id,
        email, display_name, real_name, avatar_url, last_seen_at
    ) VALUES (
        p_provider, p_provider_user_id, p_provider_team_id,
        p_email, p_display_name, p_real_name, p_avatar_url, NOW()
    )
    ON CONFLICT (provider, provider_user_id) DO UPDATE SET
        provider_team_id = COALESCE(EXCLUDED.provider_team_id, channel_identities.provider_team_id),
        email = COALESCE(EXCLUDED.email, channel_identities.email),
        display_name = COALESCE(EXCLUDED.display_name, channel_identities.display_name),
        real_name = COALESCE(EXCLUDED.real_name, channel_identities.real_name),
        avatar_url = COALESCE(EXCLUDED.avatar_url, channel_identities.avatar_url),
        last_seen_at = NOW(),
        updated_at = NOW()
    RETURNING id, user_id, is_blocked INTO v_identity_id, v_user_id, v_is_blocked;

    RETURN QUERY SELECT v_identity_id, v_user_id, (v_user_id IS NOT NULL)::BOOLEAN, v_is_blocked, v_require_auth;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Check channel user authorization
CREATE OR REPLACE FUNCTION check_channel_authorization(p_provider TEXT, p_provider_user_id TEXT)
RETURNS TABLE(
    is_authorized BOOLEAN,
    reason TEXT,
    platform_user_id TEXT,
    platform_user_name TEXT,
    platform_profile TEXT
) AS $$
DECLARE
    v_identity RECORD;
    v_user RECORD;
    v_require_auth BOOLEAN;
    v_setting_key TEXT;
BEGIN
    v_setting_key := p_provider || '_require_platform_auth';
    SELECT (value)::boolean INTO v_require_auth FROM system_settings WHERE key = v_setting_key;
    v_require_auth := COALESCE(v_require_auth, FALSE);

    SELECT * INTO v_identity FROM channel_identities
    WHERE provider = p_provider AND provider_user_id = p_provider_user_id;

    IF v_identity IS NULL AND NOT v_require_auth THEN
        RETURN QUERY SELECT TRUE, 'open_access'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF v_identity IS NULL AND v_require_auth THEN
        RETURN QUERY SELECT FALSE, 'unknown_user'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF v_identity.is_blocked THEN
        RETURN QUERY SELECT FALSE, 'blocked'::TEXT, v_identity.user_id, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF v_identity.user_id IS NULL AND NOT v_require_auth THEN
        RETURN QUERY SELECT TRUE, 'open_access'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF v_identity.user_id IS NULL AND v_require_auth THEN
        RETURN QUERY SELECT FALSE, 'not_linked'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    SELECT u.*, p.name as profile_name INTO v_user
    FROM users u LEFT JOIN profiles p ON u.profile_id = p.id
    WHERE u.id = v_identity.user_id;

    IF v_user IS NULL THEN
        RETURN QUERY SELECT FALSE, 'user_not_found'::TEXT, v_identity.user_id, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF NOT v_user.is_active THEN
        RETURN QUERY SELECT FALSE, 'user_inactive'::TEXT, v_identity.user_id, v_user.name, v_user.profile_name;
        RETURN;
    END IF;

    RETURN QUERY SELECT TRUE, 'linked_active'::TEXT, v_identity.user_id, v_user.name, v_user.profile_name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Link channel identity to platform user
CREATE OR REPLACE FUNCTION link_channel_identity(
    p_provider TEXT,
    p_provider_user_id TEXT,
    p_platform_user_id TEXT,
    p_linked_by TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_platform_user_id) THEN
        RAISE EXCEPTION 'Platform user not found: %', p_platform_user_id;
    END IF;

    UPDATE channel_identities
    SET user_id = p_platform_user_id, linked_at = NOW(), linked_by = p_linked_by, updated_at = NOW()
    WHERE provider = p_provider AND provider_user_id = p_provider_user_id;

    IF NOT FOUND THEN
        INSERT INTO channel_identities (provider, provider_user_id, provider_team_id, user_id, linked_at, linked_by)
        VALUES (p_provider, p_provider_user_id, 'unknown', p_platform_user_id, NOW(), p_linked_by);
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Auto-link by email
CREATE OR REPLACE FUNCTION auto_link_channel_by_email(p_provider TEXT DEFAULT NULL)
RETURNS TABLE(provider TEXT, provider_user_id TEXT, email TEXT, platform_user_id TEXT, platform_user_name TEXT) AS $$
BEGIN
    RETURN QUERY
    WITH linkable AS (
        SELECT ci.provider, ci.provider_user_id, ci.email, u.id as user_id, u.name as user_name
        FROM channel_identities ci
        INNER JOIN users u ON LOWER(ci.email) = LOWER(u.email)
        WHERE ci.user_id IS NULL AND ci.email IS NOT NULL AND u.is_active = TRUE
        AND (p_provider IS NULL OR ci.provider = p_provider)
    ),
    updated AS (
        UPDATE channel_identities ci
        SET user_id = l.user_id, linked_at = NOW(), linked_by = 'auto_link_by_email', updated_at = NOW()
        FROM linkable l
        WHERE ci.provider = l.provider AND ci.provider_user_id = l.provider_user_id
        RETURNING ci.provider
    )
    SELECT l.provider, l.provider_user_id, l.email, l.user_id, l.user_name FROM linkable l;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- HELPER FUNCTIONS: AUDIT LOG
-- =============================================================================

CREATE OR REPLACE FUNCTION create_audit_log(
    p_user_id TEXT,
    p_action TEXT,
    p_action_category TEXT,
    p_resource_type TEXT DEFAULT NULL,
    p_resource_id TEXT DEFAULT NULL,
    p_target_user_id TEXT DEFAULT NULL,
    p_old_value JSONB DEFAULT NULL,
    p_new_value JSONB DEFAULT NULL,
    p_details JSONB DEFAULT NULL
)
RETURNS BIGINT AS $$
DECLARE
    v_user_email TEXT;
    v_target_email TEXT;
    v_id BIGINT;
BEGIN
    SELECT email INTO v_user_email FROM users WHERE id = p_user_id;
    IF p_target_user_id IS NOT NULL THEN
        SELECT email INTO v_target_email FROM users WHERE id = p_target_user_id;
    END IF;

    INSERT INTO audit_log (
        user_id, user_email, action, action_category,
        resource_type, resource_id, target_user_id, target_user_email,
        old_value, new_value, details_json
    ) VALUES (
        p_user_id, v_user_email, p_action, p_action_category,
        p_resource_type, p_resource_id, p_target_user_id, v_target_email,
        p_old_value, p_new_value, p_details
    ) RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- TRIGGERS: COMPANY MANAGEMENT
-- =============================================================================

-- Ensure only one primary company per user
CREATE OR REPLACE FUNCTION ensure_single_primary_company()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_primary = true THEN
        UPDATE user_companies SET is_primary = false
        WHERE user_id = NEW.user_id AND id != NEW.id AND is_primary = true;
        UPDATE users SET primary_company_id = NEW.company_id WHERE id = NEW.user_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_ensure_single_primary_company ON user_companies;
CREATE TRIGGER trigger_ensure_single_primary_company
    AFTER INSERT OR UPDATE ON user_companies
    FOR EACH ROW WHEN (NEW.is_primary = true)
    EXECUTE FUNCTION ensure_single_primary_company();

-- Auto-set primary if first company assignment
CREATE OR REPLACE FUNCTION auto_set_primary_company()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM user_companies WHERE user_id = NEW.user_id AND id != NEW.id) THEN
        NEW.is_primary := true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_auto_set_primary_company ON user_companies;
CREATE TRIGGER trigger_auto_set_primary_company
    BEFORE INSERT ON user_companies
    FOR EACH ROW EXECUTE FUNCTION auto_set_primary_company();

-- =============================================================================
-- TRIGGERS: AUDIT
-- =============================================================================

CREATE OR REPLACE FUNCTION audit_profile_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.profile_id IS DISTINCT FROM NEW.profile_id THEN
        PERFORM create_audit_log(
            NULL, 'profile.assign', 'rbac', 'user', NEW.id, NEW.id,
            jsonb_build_object('profile_id', OLD.profile_id),
            jsonb_build_object('profile_id', NEW.profile_id), NULL
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS audit_user_profile_change ON users;
CREATE TRIGGER audit_user_profile_change
    AFTER UPDATE ON users FOR EACH ROW EXECUTE FUNCTION audit_profile_change();

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Companies with hierarchy info
CREATE OR REPLACE VIEW companies_with_hierarchy AS
SELECT c.id, c.code, c.name, c.parent_id, p.code as parent_code, p.name as parent_name,
       c.country, c.currency, c.is_group, c.is_active, c.config
FROM companies c
LEFT JOIN companies p ON c.parent_id = p.id
WHERE c.is_active = true
ORDER BY CASE WHEN c.parent_id IS NULL THEN 0 ELSE 1 END, c.name;

-- User companies with details
CREATE OR REPLACE VIEW user_companies_detailed AS
SELECT uc.user_id, uc.company_id, uc.is_primary, c.code as company_code, c.name as company_name,
       c.parent_id, c.is_group, c.country, c.currency, u.email as user_email, u.name as user_name
FROM user_companies uc
JOIN companies c ON uc.company_id = c.id
JOIN users u ON uc.user_id = u.id
WHERE c.is_active = true;

-- Channel identities pending links
CREATE OR REPLACE VIEW channel_pending_links AS
SELECT ci.id, ci.provider, ci.provider_user_id, ci.provider_team_id, ci.email,
       ci.display_name, ci.real_name, ci.first_seen_at, ci.last_seen_at,
       u.id as potential_user_id, u.name as potential_user_name, u.email as potential_user_email,
       p.display_name as potential_user_profile
FROM channel_identities ci
LEFT JOIN users u ON LOWER(ci.email) = LOWER(u.email)
LEFT JOIN profiles p ON u.profile_id = p.id
WHERE ci.user_id IS NULL AND ci.is_blocked = FALSE
ORDER BY (u.id IS NOT NULL) DESC, ci.last_seen_at DESC;

-- Channel identities full view
CREATE OR REPLACE VIEW channel_identities_full AS
SELECT ci.*, u.name as platform_user_name, u.email as platform_user_email, u.is_active as platform_user_active,
       p.name as platform_profile_name, p.display_name as platform_profile_display
FROM channel_identities ci
LEFT JOIN users u ON ci.user_id = u.id
LEFT JOIN profiles p ON u.profile_id = p.id
ORDER BY ci.last_seen_at DESC;

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_set_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_permission_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE sharing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE record_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE invite_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;

-- Service role has full access to all tables
CREATE POLICY "Service role full access" ON user_preferences FOR ALL USING (true);
CREATE POLICY "Service role full access" ON profiles FOR ALL USING (true);
CREATE POLICY "Service role full access" ON profile_permissions FOR ALL USING (true);
CREATE POLICY "Service role full access" ON permission_sets FOR ALL USING (true);
CREATE POLICY "Service role full access" ON permission_set_permissions FOR ALL USING (true);
CREATE POLICY "Service role full access" ON teams FOR ALL USING (true);
CREATE POLICY "Service role full access" ON team_members FOR ALL USING (true);
CREATE POLICY "Service role full access" ON companies FOR ALL USING (true);
CREATE POLICY "Service role full access" ON users FOR ALL USING (true);
CREATE POLICY "Service role full access" ON user_companies FOR ALL USING (true);
CREATE POLICY "Service role full access" ON user_permission_sets FOR ALL USING (true);
CREATE POLICY "Service role full access" ON sharing_rules FOR ALL USING (true);
CREATE POLICY "Service role full access" ON record_shares FOR ALL USING (true);
CREATE POLICY "Service role full access" ON channel_identities FOR ALL USING (true);
CREATE POLICY "Service role full access" ON system_settings FOR ALL USING (true);
CREATE POLICY "Service role full access" ON permissions FOR ALL USING (true);
CREATE POLICY "Service role full access" ON modules FOR ALL USING (true);
CREATE POLICY "Service role full access" ON user_modules FOR ALL USING (true);
CREATE POLICY "Service role full access" ON invite_tokens FOR ALL USING (true);
CREATE POLICY "Service role full access" ON audit_log FOR ALL USING (true);
CREATE POLICY "Service role full access" ON api_keys FOR ALL USING (true);
CREATE POLICY "Service role full access" ON api_key_usage FOR ALL USING (true);

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- =============================================================================
-- SEED DATA: DEFAULT PROFILES
-- =============================================================================
INSERT INTO profiles (name, display_name, description, is_system) VALUES
    ('system_admin', 'System Administrator', 'Full system access to all modules and features', true),
    ('sales_manager', 'Sales Manager', 'Sales team management and oversight', true),
    ('sales_user', 'Sales User', 'Sales team member with standard access', true),
    ('coordinator', 'Coordinator', 'Operations coordinator for booking orders', true),
    ('finance', 'Finance', 'Finance team with read access to financial data', true),
    ('viewer', 'Viewer', 'Read-only access to assigned modules', true)
ON CONFLICT (name) DO NOTHING;

-- System Admin - full access
INSERT INTO profile_permissions (profile_id, permission)
SELECT id, '*:*:*' FROM profiles WHERE name = 'system_admin'
ON CONFLICT DO NOTHING;

-- Sales Manager
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES ('sales:*:*'), ('core:users:read'), ('core:ai_costs:read'), ('core:teams:read')) AS perms(perm)
WHERE p.name = 'sales_manager'
ON CONFLICT DO NOTHING;

-- Sales User
-- Note: mockups permissions are explicit (generate, read) - NOT setup
-- Setup requires sales_manager or system_admin profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES
    ('sales:proposals:create'), ('sales:proposals:read'), ('sales:proposals:update'),
    ('sales:booking_orders:create'), ('sales:booking_orders:read'),
    ('sales:mockups:generate'), ('sales:mockups:read'),
    ('sales:templates:read'),
    ('sales:chat:use')
) AS perms(perm)
WHERE p.name = 'sales_user'
ON CONFLICT DO NOTHING;

-- Coordinator
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES ('sales:booking_orders:*'), ('sales:proposals:read')) AS perms(perm)
WHERE p.name = 'coordinator'
ON CONFLICT DO NOTHING;

-- Finance
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES ('sales:booking_orders:read'), ('core:ai_costs:read')) AS perms(perm)
WHERE p.name = 'finance'
ON CONFLICT DO NOTHING;

-- Viewer
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES ('sales:proposals:read'), ('sales:booking_orders:read'), ('sales:mockups:read')) AS perms(perm)
WHERE p.name = 'viewer'
ON CONFLICT DO NOTHING;

-- =============================================================================
-- SEED DATA: DEFAULT PERMISSION SETS
-- =============================================================================
INSERT INTO permission_sets (name, display_name, description) VALUES
    ('api_access', 'API Access', 'Programmatic API access for integrations'),
    ('data_export', 'Data Export', 'Export data to CSV/Excel formats'),
    ('delete_records', 'Delete Records', 'Ability to delete records'),
    ('view_all_data', 'View All Data', 'View all records regardless of ownership'),
    ('manage_templates', 'Manage Templates', 'Create and edit templates')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: DEFAULT COMPANIES
-- =============================================================================
INSERT INTO companies (code, name, parent_id, country, currency, is_group, config) VALUES
    ('mmg', 'MMG', NULL, NULL, 'AED', true, '{"description": "Parent company - full access to all subsidiaries"}')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_group = EXCLUDED.is_group;

INSERT INTO companies (code, name, parent_id, country, currency, is_group, config) VALUES
    ('backlite', 'Backlite', (SELECT id FROM companies WHERE code = 'mmg'), NULL, 'AED', true, '{"description": "Backlite group - outdoor advertising"}')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_group = EXCLUDED.is_group;

INSERT INTO companies (code, name, parent_id, country, currency, is_group, config) VALUES
    ('backlite_dubai', 'Backlite Dubai', (SELECT id FROM companies WHERE code = 'backlite'), 'UAE', 'AED', false, '{"region": "Dubai"}'),
    ('backlite_uk', 'Backlite UK', (SELECT id FROM companies WHERE code = 'backlite'), 'UK', 'GBP', false, '{"region": "United Kingdom"}'),
    ('backlite_abudhabi', 'Backlite Abu Dhabi', (SELECT id FROM companies WHERE code = 'backlite'), 'UAE', 'AED', false, '{"region": "Abu Dhabi"}'),
    ('viola', 'Viola', (SELECT id FROM companies WHERE code = 'mmg'), 'UAE', 'AED', false, '{"description": "Viola outdoor"}')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, country = EXCLUDED.country;

-- =============================================================================
-- SEED DATA: DEFAULT MODULES
-- =============================================================================
INSERT INTO modules (name, display_name, description, icon, is_active, is_default, sort_order, required_permission) VALUES
    ('sales', 'Sales Bot', 'Sales proposal generation, mockups, and booking orders', 'chart-bar', true, true, 1, 'sales:*:read'),
    ('core', 'Administration', 'System administration and user management', 'shield', true, false, 100, 'core:*:read')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: DEFAULT SYSTEM SETTINGS
-- =============================================================================
INSERT INTO system_settings (key, value, description) VALUES
    ('slack_require_platform_auth', 'false'::jsonb, 'When true, Slack users must be linked to use the bot'),
    ('teams_require_platform_auth', 'false'::jsonb, 'When true, Teams users must be linked to use the bot')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- DONE! UI Schema Complete.
-- =============================================================================
