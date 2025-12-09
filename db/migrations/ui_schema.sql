-- =============================================================================
-- UI SUPABASE SCHEMA (Core/Auth)
-- =============================================================================
-- Run this in UI-Module-Dev and UI-Module-Prod Supabase projects
--
-- This database handles:
-- - User profiles and preferences
-- - RBAC (roles, permissions)
-- - Module access control
-- - Invite tokens for signup
-- - Audit logging
-- - API key management
--
-- NOTE: auth.users is managed automatically by Supabase Auth - do NOT create it
-- =============================================================================

-- =============================================================================
-- USER PROFILES (linked to Supabase Auth)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_profiles (
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

CREATE INDEX IF NOT EXISTS idx_user_profiles_created_at ON user_profiles(created_at);

-- Auto-create profile when user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, display_name, avatar_url)
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

-- Auto-update timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- =============================================================================
-- USERS TABLE (synced from Supabase Auth for cross-service reference)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,  -- UUID as text for compatibility
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Sync users table from auth.users on insert
CREATE OR REPLACE FUNCTION public.sync_user_from_auth()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, name, avatar_url, created_at, updated_at)
    VALUES (
        NEW.id::TEXT,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        NEW.raw_user_meta_data->>'avatar_url',
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
-- RBAC TABLES
-- =============================================================================

-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT,
    module TEXT,  -- NULL = system-wide, 'sales' = sales module specific
    is_system BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);
CREATE INDEX IF NOT EXISTS idx_roles_module ON roles(module);

-- User-Role assignments
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    granted_by TEXT REFERENCES users(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    CONSTRAINT user_roles_unique UNIQUE (user_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);

-- Permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,  -- e.g., 'sales:proposals:create'
    description TEXT,
    module TEXT NOT NULL,  -- 'core', 'sales', etc.
    resource TEXT NOT NULL,  -- 'proposals', 'users', etc.
    action TEXT NOT NULL,  -- 'create', 'read', 'update', 'delete', 'manage'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT permissions_unique UNIQUE (module, resource, action)
);

CREATE INDEX IF NOT EXISTS idx_permissions_name ON permissions(name);
CREATE INDEX IF NOT EXISTS idx_permissions_module ON permissions(module);
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON permissions(resource);

-- Role-Permission assignments
CREATE TABLE IF NOT EXISTS role_permissions (
    id BIGSERIAL PRIMARY KEY,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT role_permissions_unique UNIQUE (role_id, permission_id)
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions(permission_id);

-- =============================================================================
-- MODULE ACCESS CONTROL
-- =============================================================================

-- Modules table
CREATE TABLE IF NOT EXISTS modules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,  -- 'sales', 'crm', 'analytics'
    display_name TEXT NOT NULL,
    description TEXT,
    icon TEXT,  -- Icon identifier for frontend
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 0,
    required_permission TEXT,  -- Permission needed to access (e.g., 'sales:*:read')
    config_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_modules_name ON modules(name);
CREATE INDEX IF NOT EXISTS idx_modules_active ON modules(is_active);

-- User-Module assignments (explicit module access)
CREATE TABLE IF NOT EXISTS user_modules (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module_id BIGINT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT false,  -- User's default landing module
    granted_by TEXT REFERENCES users(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_modules_unique UNIQUE (user_id, module_id)
);

CREATE INDEX IF NOT EXISTS idx_user_modules_user ON user_modules(user_id);
CREATE INDEX IF NOT EXISTS idx_user_modules_module ON user_modules(module_id);

-- =============================================================================
-- INVITE TOKENS (for user signup)
-- =============================================================================
CREATE TABLE IF NOT EXISTS invite_tokens (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    role_id BIGINT NOT NULL REFERENCES roles(id),
    module_ids BIGINT[],  -- Array of module IDs to grant access to
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by_user_id TEXT REFERENCES users(id),
    is_revoked BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_invite_tokens_token ON invite_tokens(token);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_email ON invite_tokens(email);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_expires ON invite_tokens(expires_at);

-- =============================================================================
-- AUDIT LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,  -- 'login', 'logout', 'create', 'update', 'delete'
    resource_type TEXT,  -- 'user', 'role', 'module', etc.
    resource_id TEXT,
    details_json JSONB,
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);

-- =============================================================================
-- API KEYS
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,  -- SHA256 hash of the key
    key_prefix TEXT NOT NULL,  -- First 8 chars for identification
    name TEXT NOT NULL,
    description TEXT,
    scopes_json JSONB NOT NULL,  -- Array of permission scopes
    rate_limit INTEGER,  -- Requests per minute (null = unlimited)
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT REFERENCES users(id),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_rotated_at TIMESTAMPTZ,
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_name ON api_keys(name);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON api_keys(created_by);

-- API key usage tracking
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
CREATE INDEX IF NOT EXISTS idx_api_key_usage_endpoint ON api_key_usage(endpoint);

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================

-- User profiles
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own profile" ON user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON user_profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Service role has full access to profiles" ON user_profiles FOR ALL USING (auth.role() = 'service_role');

-- Users table (service role only for cross-service sync)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to users" ON users FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Authenticated can view users" ON users FOR SELECT TO authenticated USING (true);

-- Roles (read by authenticated, manage by service role)
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view roles" ON roles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages roles" ON roles FOR ALL USING (auth.role() = 'service_role');

-- User roles
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own roles" ON user_roles FOR SELECT USING (user_id = auth.uid()::TEXT);
CREATE POLICY "Service role manages user_roles" ON user_roles FOR ALL USING (auth.role() = 'service_role');

-- Permissions
ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view permissions" ON permissions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages permissions" ON permissions FOR ALL USING (auth.role() = 'service_role');

-- Role permissions
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view role_permissions" ON role_permissions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages role_permissions" ON role_permissions FOR ALL USING (auth.role() = 'service_role');

-- Modules
ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view active modules" ON modules FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "Service role manages modules" ON modules FOR ALL USING (auth.role() = 'service_role');

-- User modules
ALTER TABLE user_modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own modules" ON user_modules FOR SELECT USING (user_id = auth.uid()::TEXT);
CREATE POLICY "Service role manages user_modules" ON user_modules FOR ALL USING (auth.role() = 'service_role');

-- Invite tokens (service role only)
ALTER TABLE invite_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages invite_tokens" ON invite_tokens FOR ALL USING (auth.role() = 'service_role');

-- Audit log (service role only)
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages audit_log" ON audit_log FOR ALL USING (auth.role() = 'service_role');

-- API keys (service role only)
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages api_keys" ON api_keys FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages api_key_usage" ON api_key_usage FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT SELECT ON user_profiles TO authenticated;
GRANT UPDATE ON user_profiles TO authenticated;
GRANT SELECT ON users TO authenticated;
GRANT SELECT ON roles TO authenticated;
GRANT SELECT ON user_roles TO authenticated;
GRANT SELECT ON permissions TO authenticated;
GRANT SELECT ON role_permissions TO authenticated;
GRANT SELECT ON modules TO authenticated;
GRANT SELECT ON user_modules TO authenticated;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- =============================================================================
-- SEED DATA: Default Roles
-- =============================================================================
INSERT INTO roles (name, display_name, description, module, is_system) VALUES
    ('admin', 'Administrator', 'Full system access to all modules', NULL, true),
    ('user', 'User', 'Standard authenticated user', NULL, true),
    ('sales:admin', 'Sales Admin', 'Full access to Sales module', 'sales', true),
    ('sales:hos', 'Head of Sales', 'Sales team oversight and management', 'sales', true),
    ('sales:sales_person', 'Sales Person', 'Sales team member', 'sales', true),
    ('sales:coordinator', 'Coordinator', 'Operations coordinator', 'sales', true),
    ('sales:finance', 'Finance', 'Finance team member', 'sales', true)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: Default Modules
-- =============================================================================
INSERT INTO modules (name, display_name, description, icon, is_active, is_default, sort_order, required_permission) VALUES
    ('sales', 'Sales Bot', 'Sales proposal generation, mockups, and booking orders', 'chart-bar', true, true, 1, 'sales:*:read'),
    ('core', 'Administration', 'System administration and user management', 'shield', true, false, 100, 'core:*:read')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: Core Permissions
-- =============================================================================
INSERT INTO permissions (name, description, module, resource, action) VALUES
    -- Core module permissions
    ('core:users:read', 'View users', 'core', 'users', 'read'),
    ('core:users:create', 'Create users', 'core', 'users', 'create'),
    ('core:users:update', 'Update users', 'core', 'users', 'update'),
    ('core:users:delete', 'Delete users', 'core', 'users', 'delete'),
    ('core:users:manage', 'Full user management', 'core', 'users', 'manage'),
    ('core:roles:read', 'View roles', 'core', 'roles', 'read'),
    ('core:roles:manage', 'Manage roles', 'core', 'roles', 'manage'),
    ('core:modules:read', 'View modules', 'core', 'modules', 'read'),
    ('core:modules:manage', 'Manage modules', 'core', 'modules', 'manage'),
    -- Sales module permissions
    ('sales:proposals:read', 'View proposals', 'sales', 'proposals', 'read'),
    ('sales:proposals:create', 'Create proposals', 'sales', 'proposals', 'create'),
    ('sales:proposals:update', 'Update proposals', 'sales', 'proposals', 'update'),
    ('sales:proposals:delete', 'Delete proposals', 'sales', 'proposals', 'delete'),
    ('sales:mockups:read', 'View mockups', 'sales', 'mockups', 'read'),
    ('sales:mockups:create', 'Create mockups', 'sales', 'mockups', 'create'),
    ('sales:booking_orders:read', 'View booking orders', 'sales', 'booking_orders', 'read'),
    ('sales:booking_orders:create', 'Create booking orders', 'sales', 'booking_orders', 'create'),
    ('sales:booking_orders:update', 'Update booking orders', 'sales', 'booking_orders', 'update'),
    ('sales:ai_costs:read', 'View AI costs', 'sales', 'ai_costs', 'read')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- Done! Your UI database is ready.
-- =============================================================================
