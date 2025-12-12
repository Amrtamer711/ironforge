-- =============================================================================
-- UI SUPABASE SCHEMA (Core/Auth) - Enterprise RBAC Architecture
-- =============================================================================
-- Run this in UI-Module-Dev and UI-Module-Prod Supabase projects
--
-- This database handles:
-- - User profiles and preferences
-- - Enterprise RBAC (profiles, permission sets, teams, sharing)
-- - Module access control
-- - Invite tokens for signup
-- - Audit logging
-- - API key management
--
-- RBAC Architecture:
-- Level 1: Profiles (base permissions for job function)
-- Level 2: Permission Sets (additive, can be temporary)
-- Level 3: Teams & Hierarchy (team-based access)
-- Level 4: Record Sharing (record-level access control)
--
-- NOTE: auth.users is managed automatically by Supabase Auth - do NOT create it
-- =============================================================================

-- =============================================================================
-- USER PROFILES (linked to Supabase Auth) - User preferences, NOT RBAC profiles
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

-- Auto-update timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- =============================================================================
-- LEVEL 1: PROFILES (Base Role Templates)
-- =============================================================================
-- Profiles define the BASE permissions for a job function (e.g., Sales Rep, Admin)
-- Each user has exactly ONE profile assigned

CREATE TABLE IF NOT EXISTS profiles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,              -- 'admin', 'sales_manager', 'sales_rep'
    display_name TEXT NOT NULL,             -- 'Administrator', 'Sales Manager'
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT false,  -- System profiles can't be deleted
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);
CREATE INDEX IF NOT EXISTS idx_profiles_system ON profiles(is_system);

-- Profile permissions - what permissions a profile grants
CREATE TABLE IF NOT EXISTS profile_permissions (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,               -- 'sales:proposals:create', '*:*:*'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT profile_permissions_unique UNIQUE (profile_id, permission)
);

CREATE INDEX IF NOT EXISTS idx_profile_permissions_profile ON profile_permissions(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_permissions_permission ON profile_permissions(permission);

-- =============================================================================
-- LEVEL 2: PERMISSION SETS (Additive Permissions)
-- =============================================================================
-- Permission sets are additional permissions that can be granted to ANY user
-- regardless of their profile. Can be temporary (with expiration).

CREATE TABLE IF NOT EXISTS permission_sets (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,              -- 'api_access', 'data_export'
    display_name TEXT NOT NULL,             -- 'API Access', 'Data Export'
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permission_sets_name ON permission_sets(name);
CREATE INDEX IF NOT EXISTS idx_permission_sets_active ON permission_sets(is_active);

-- Permission set permissions
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
-- Teams allow grouping users and defining team-based access rules
-- Hierarchy enables "see subordinate data" patterns

CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    parent_team_id BIGINT REFERENCES teams(id) ON DELETE SET NULL,  -- Hierarchy
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name);
CREATE INDEX IF NOT EXISTS idx_teams_parent ON teams(parent_team_id);
CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(is_active);

-- =============================================================================
-- USERS TABLE (Extended for Enterprise RBAC)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                    -- UUID as text for compatibility
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- RBAC: Profile assignment (Level 1)
    profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,

    -- Hierarchy: Manager relationship (Level 3)
    manager_id TEXT REFERENCES users(id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,

    -- Extensibility
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_profile ON users(profile_id);
CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);

-- Sync users table from auth.users on insert/update
-- Assigns default 'sales_user' profile to new users if no profile is set
CREATE OR REPLACE FUNCTION public.sync_user_from_auth()
RETURNS TRIGGER AS $$
DECLARE
    default_profile_id BIGINT;
    existing_profile_id BIGINT;
BEGIN
    -- Check if user already exists and has a profile
    SELECT profile_id INTO existing_profile_id
    FROM public.users
    WHERE id = NEW.id::TEXT;

    -- Get default profile ID (sales_user) only if needed for new users
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
        default_profile_id,  -- Will be NULL for existing users (preserving their profile)
        NOW(),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        name = EXCLUDED.name,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = NOW();
        -- Note: profile_id is NOT updated on conflict, preserving existing profile
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_sync ON auth.users;
CREATE TRIGGER on_auth_user_sync
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.sync_user_from_auth();

-- User-Permission Set assignments (Level 2)
CREATE TABLE IF NOT EXISTS user_permission_sets (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_set_id BIGINT NOT NULL REFERENCES permission_sets(id) ON DELETE CASCADE,
    granted_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                 -- NULL = permanent, otherwise temporary
    CONSTRAINT user_permission_sets_unique UNIQUE (user_id, permission_set_id)
);

CREATE INDEX IF NOT EXISTS idx_ups_user ON user_permission_sets(user_id);
CREATE INDEX IF NOT EXISTS idx_ups_set ON user_permission_sets(permission_set_id);
CREATE INDEX IF NOT EXISTS idx_ups_expires ON user_permission_sets(expires_at);
-- Composite index for fetching active (non-expired) permission sets for a user
CREATE INDEX IF NOT EXISTS idx_ups_user_expires ON user_permission_sets(user_id, expires_at);

-- Team membership (Level 3)
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
-- Organization-wide sharing rules
CREATE TABLE IF NOT EXISTS sharing_rules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    object_type TEXT NOT NULL,              -- 'proposal', 'booking_order', 'mockup'

    -- Who owns the records being shared
    share_from_type TEXT NOT NULL CHECK (share_from_type IN ('owner', 'profile', 'team')),
    share_from_id TEXT,                     -- profile name or team id (NULL for 'owner')

    -- Who gets access
    share_to_type TEXT NOT NULL CHECK (share_to_type IN ('profile', 'team', 'all')),
    share_to_id TEXT,                       -- profile name or team id (NULL for 'all')

    access_level TEXT NOT NULL CHECK (access_level IN ('read', 'read_write', 'full')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sharing_rules_object ON sharing_rules(object_type);
CREATE INDEX IF NOT EXISTS idx_sharing_rules_active ON sharing_rules(is_active);

-- Ad-hoc record sharing (share specific record with user/team)
CREATE TABLE IF NOT EXISTS record_shares (
    id BIGSERIAL PRIMARY KEY,
    object_type TEXT NOT NULL,
    record_id TEXT NOT NULL,

    -- Share target (exactly one must be set)
    shared_with_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    shared_with_team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,

    access_level TEXT NOT NULL CHECK (access_level IN ('read', 'read_write', 'full')),
    shared_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                 -- NULL = permanent
    reason TEXT,                            -- Optional: why this was shared

    CONSTRAINT record_shares_target CHECK (
        (shared_with_user_id IS NOT NULL AND shared_with_team_id IS NULL) OR
        (shared_with_user_id IS NULL AND shared_with_team_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_record_shares_lookup ON record_shares(object_type, record_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_user ON record_shares(shared_with_user_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_team ON record_shares(shared_with_team_id);
CREATE INDEX IF NOT EXISTS idx_record_shares_expires ON record_shares(expires_at);
-- Composite index for checking active shares for a user
CREATE INDEX IF NOT EXISTS idx_record_shares_user_expires ON record_shares(shared_with_user_id, expires_at);
-- Composite index for access checks on specific records
CREATE INDEX IF NOT EXISTS idx_record_shares_access_check ON record_shares(object_type, record_id, shared_with_user_id);

-- =============================================================================
-- PERMISSIONS TABLE (for audit/reference - actual permission checks use RBAC layer)
-- =============================================================================
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,              -- 'sales:proposals:create'
    description TEXT,
    module TEXT NOT NULL,                   -- 'sales', 'core'
    resource TEXT NOT NULL,                 -- 'proposals', 'users'
    action TEXT NOT NULL,                   -- 'create', 'read', 'update', 'delete', 'manage'
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
    profile_name TEXT,                          -- Profile name to assign on signup (e.g., 'sales_user')
    permission_set_ids_json TEXT,               -- JSON array of permission set names to grant
    team_id BIGINT REFERENCES teams(id),        -- Optional: auto-add to team
    created_by TEXT NOT NULL,                   -- User ID who created the invite
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by_user_id TEXT,                       -- User ID who used the invite
    is_revoked BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_invite_tokens_token ON invite_tokens(token);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_email ON invite_tokens(email);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_expires ON invite_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_invite_tokens_profile ON invite_tokens(profile_name);

-- =============================================================================
-- AUDIT LOG (Extended for RBAC tracking)
-- =============================================================================
-- Tracks all RBAC and security-related changes for compliance and debugging
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who performed the action
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    user_email TEXT,                            -- Snapshot in case user is deleted

    -- What action was performed
    action TEXT NOT NULL,                       -- e.g., 'profile.assign', 'team.add_member', 'permission_set.grant'
    action_category TEXT NOT NULL DEFAULT 'other' CHECK (action_category IN (
        'auth',              -- login, logout, password_reset
        'rbac',              -- profile/permission/team changes
        'sharing',           -- record sharing
        'user_management',   -- user create/update/deactivate
        'data_access',       -- sensitive data access
        'admin',             -- admin actions
        'other'
    )),

    -- What resource was affected
    resource_type TEXT,                         -- e.g., 'user', 'team', 'permission_set', 'profile'
    resource_id TEXT,                           -- ID of affected resource

    -- Target user (for actions affecting another user)
    target_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    target_user_email TEXT,                     -- Snapshot

    -- Details
    old_value JSONB,                            -- Previous state (for updates)
    new_value JSONB,                            -- New state (for creates/updates)
    details_json JSONB,                         -- Additional context

    -- Request context
    ip_address TEXT,
    user_agent TEXT,
    request_id TEXT,                            -- For correlating related actions

    -- Outcome
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

-- Function to create audit log entry (for triggers and manual calls)
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
    -- Get user emails for snapshots
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

-- Trigger to audit profile assignments
CREATE OR REPLACE FUNCTION audit_profile_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.profile_id IS DISTINCT FROM NEW.profile_id THEN
        PERFORM create_audit_log(
            NULL,  -- System or will be set by app
            'profile.assign',
            'rbac',
            'user',
            NEW.id,
            NEW.id,
            jsonb_build_object('profile_id', OLD.profile_id),
            jsonb_build_object('profile_id', NEW.profile_id),
            NULL
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS audit_user_profile_change ON users;
CREATE TRIGGER audit_user_profile_change
    AFTER UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_profile_change();

-- Trigger to audit team membership changes
CREATE OR REPLACE FUNCTION audit_team_membership()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM create_audit_log(
            NULL,
            'team.add_member',
            'rbac',
            'team',
            NEW.team_id::TEXT,
            NEW.user_id,
            NULL,
            jsonb_build_object('role', NEW.role),
            NULL
        );
    ELSIF TG_OP = 'UPDATE' AND OLD.role IS DISTINCT FROM NEW.role THEN
        PERFORM create_audit_log(
            NULL,
            'team.update_role',
            'rbac',
            'team',
            NEW.team_id::TEXT,
            NEW.user_id,
            jsonb_build_object('role', OLD.role),
            jsonb_build_object('role', NEW.role),
            NULL
        );
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM create_audit_log(
            NULL,
            'team.remove_member',
            'rbac',
            'team',
            OLD.team_id::TEXT,
            OLD.user_id,
            jsonb_build_object('role', OLD.role),
            NULL,
            NULL
        );
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS audit_team_membership_changes ON team_members;
CREATE TRIGGER audit_team_membership_changes
    AFTER INSERT OR UPDATE OR DELETE ON team_members
    FOR EACH ROW EXECUTE FUNCTION audit_team_membership();

-- Trigger to audit permission set grants/revokes
CREATE OR REPLACE FUNCTION audit_permission_set_assignment()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM create_audit_log(
            NEW.granted_by,
            'permission_set.grant',
            'rbac',
            'permission_set',
            NEW.permission_set_id::TEXT,
            NEW.user_id,
            NULL,
            jsonb_build_object('expires_at', NEW.expires_at),
            NULL
        );
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM create_audit_log(
            NULL,
            'permission_set.revoke',
            'rbac',
            'permission_set',
            OLD.permission_set_id::TEXT,
            OLD.user_id,
            jsonb_build_object('granted_by', OLD.granted_by, 'expires_at', OLD.expires_at),
            NULL,
            NULL
        );
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS audit_permission_set_changes ON user_permission_sets;
CREATE TRIGGER audit_permission_set_changes
    AFTER INSERT OR DELETE ON user_permission_sets
    FOR EACH ROW EXECUTE FUNCTION audit_permission_set_assignment();

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
-- ROW LEVEL SECURITY
-- =============================================================================

-- User preferences
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own preferences" ON user_preferences FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own preferences" ON user_preferences FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Service role full access preferences" ON user_preferences FOR ALL USING (auth.role() = 'service_role');

-- Profiles (read by authenticated, manage by service role)
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view profiles" ON profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages profiles" ON profiles FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE profile_permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view profile_permissions" ON profile_permissions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages profile_permissions" ON profile_permissions FOR ALL USING (auth.role() = 'service_role');

-- Permission sets
ALTER TABLE permission_sets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view active permission_sets" ON permission_sets FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "Service role manages permission_sets" ON permission_sets FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE permission_set_permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view psp" ON permission_set_permissions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages psp" ON permission_set_permissions FOR ALL USING (auth.role() = 'service_role');

-- Teams
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view active teams" ON teams FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "Service role manages teams" ON teams FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view team memberships" ON team_members FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages team_members" ON team_members FOR ALL USING (auth.role() = 'service_role');

-- Users
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access users" ON users FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Authenticated can view users" ON users FOR SELECT TO authenticated USING (true);

ALTER TABLE user_permission_sets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own permission_sets" ON user_permission_sets FOR SELECT USING (user_id = auth.uid()::TEXT);
CREATE POLICY "Service role manages user_permission_sets" ON user_permission_sets FOR ALL USING (auth.role() = 'service_role');

-- Sharing
ALTER TABLE sharing_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view active sharing_rules" ON sharing_rules FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "Service role manages sharing_rules" ON sharing_rules FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE record_shares ENABLE ROW LEVEL SECURITY;
-- Users can view shares they created or are shared with
CREATE POLICY "Users can view shares involving them" ON record_shares FOR SELECT TO authenticated USING (
    shared_with_user_id = auth.uid()::TEXT OR shared_by = auth.uid()::TEXT
);
-- Users can update shares they created
CREATE POLICY "Users can update own shares" ON record_shares FOR UPDATE TO authenticated USING (
    shared_by = auth.uid()::TEXT
);
-- Users can delete shares they created
CREATE POLICY "Users can delete own shares" ON record_shares FOR DELETE TO authenticated USING (
    shared_by = auth.uid()::TEXT
);
-- Users can create shares (will be validated by app layer for ownership)
CREATE POLICY "Authenticated can create shares" ON record_shares FOR INSERT TO authenticated WITH CHECK (
    shared_by = auth.uid()::TEXT
);
CREATE POLICY "Service role manages record_shares" ON record_shares FOR ALL USING (auth.role() = 'service_role');

-- Permissions
ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view permissions" ON permissions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role manages permissions" ON permissions FOR ALL USING (auth.role() = 'service_role');

-- Modules
ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated can view active modules" ON modules FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "Service role manages modules" ON modules FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE user_modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own modules" ON user_modules FOR SELECT USING (user_id = auth.uid()::TEXT);
CREATE POLICY "Service role manages user_modules" ON user_modules FOR ALL USING (auth.role() = 'service_role');

-- Invite tokens
ALTER TABLE invite_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages invite_tokens" ON invite_tokens FOR ALL USING (auth.role() = 'service_role');

-- Audit log
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages audit_log" ON audit_log FOR ALL USING (auth.role() = 'service_role');

-- API keys
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages api_keys" ON api_keys FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role manages api_key_usage" ON api_key_usage FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT SELECT ON user_preferences TO authenticated;
GRANT UPDATE ON user_preferences TO authenticated;
GRANT SELECT ON profiles TO authenticated;
GRANT SELECT ON profile_permissions TO authenticated;
GRANT SELECT ON permission_sets TO authenticated;
GRANT SELECT ON permission_set_permissions TO authenticated;
GRANT SELECT ON teams TO authenticated;
GRANT SELECT ON team_members TO authenticated;
GRANT SELECT ON users TO authenticated;
GRANT SELECT ON user_permission_sets TO authenticated;
GRANT SELECT ON sharing_rules TO authenticated;
GRANT SELECT ON record_shares TO authenticated;
GRANT SELECT ON permissions TO authenticated;
GRANT SELECT ON modules TO authenticated;
GRANT SELECT ON user_modules TO authenticated;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- =============================================================================
-- SEED DATA: Default Profiles
-- =============================================================================
INSERT INTO profiles (name, display_name, description, is_system) VALUES
    ('system_admin', 'System Administrator', 'Full system access to all modules and features', true),
    ('sales_manager', 'Sales Manager', 'Sales team management and oversight', true),
    ('sales_user', 'Sales User', 'Sales team member with standard access', true),
    ('coordinator', 'Coordinator', 'Operations coordinator for booking orders', true),
    ('finance', 'Finance', 'Finance team with read access to financial data', true),
    ('viewer', 'Viewer', 'Read-only access to assigned modules', true)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: Profile Permissions
-- =============================================================================
-- System Admin profile - full access
INSERT INTO profile_permissions (profile_id, permission)
SELECT id, '*:*:*' FROM profiles WHERE name = 'system_admin'
ON CONFLICT DO NOTHING;

-- Sales Manager profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p
CROSS JOIN (VALUES
    ('sales:*:*'),
    ('core:users:read'),
    ('core:ai_costs:read'),
    ('core:teams:read')
) AS perms(perm)
WHERE p.name = 'sales_manager'
ON CONFLICT DO NOTHING;

-- Sales User profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p
CROSS JOIN (VALUES
    ('sales:proposals:create'),
    ('sales:proposals:read'),
    ('sales:proposals:update'),
    ('sales:booking_orders:create'),
    ('sales:booking_orders:read'),
    ('sales:mockups:*'),
    ('sales:templates:read')
) AS perms(perm)
WHERE p.name = 'sales_user'
ON CONFLICT DO NOTHING;

-- Coordinator profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p
CROSS JOIN (VALUES
    ('sales:booking_orders:*'),
    ('sales:proposals:read')
) AS perms(perm)
WHERE p.name = 'coordinator'
ON CONFLICT DO NOTHING;

-- Finance profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p
CROSS JOIN (VALUES
    ('sales:booking_orders:read'),
    ('core:ai_costs:read')
) AS perms(perm)
WHERE p.name = 'finance'
ON CONFLICT DO NOTHING;

-- Viewer profile
INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p
CROSS JOIN (VALUES
    ('sales:proposals:read'),
    ('sales:booking_orders:read'),
    ('sales:mockups:read')
) AS perms(perm)
WHERE p.name = 'viewer'
ON CONFLICT DO NOTHING;

-- =============================================================================
-- SEED DATA: Default Permission Sets
-- =============================================================================
INSERT INTO permission_sets (name, display_name, description) VALUES
    ('api_access', 'API Access', 'Programmatic API access for integrations'),
    ('data_export', 'Data Export', 'Export data to CSV/Excel formats'),
    ('delete_records', 'Delete Records', 'Ability to delete records'),
    ('view_all_data', 'View All Data', 'View all records regardless of ownership'),
    ('manage_templates', 'Manage Templates', 'Create and edit templates')
ON CONFLICT (name) DO NOTHING;

-- Permission set permissions
INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, 'core:api:access' FROM permission_sets ps WHERE ps.name = 'api_access'
ON CONFLICT DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, 'core:export:*' FROM permission_sets ps WHERE ps.name = 'data_export'
ON CONFLICT DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, '*:*:delete' FROM permission_sets ps WHERE ps.name = 'delete_records'
ON CONFLICT DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, '*:*:read:all' FROM permission_sets ps WHERE ps.name = 'view_all_data'
ON CONFLICT DO NOTHING;

INSERT INTO permission_set_permissions (permission_set_id, permission)
SELECT ps.id, 'sales:templates:*' FROM permission_sets ps WHERE ps.name = 'manage_templates'
ON CONFLICT DO NOTHING;

-- =============================================================================
-- SEED DATA: Default Modules
-- =============================================================================
INSERT INTO modules (name, display_name, description, icon, is_active, is_default, sort_order, required_permission) VALUES
    ('sales', 'Sales Bot', 'Sales proposal generation, mockups, and booking orders', 'chart-bar', true, true, 1, 'sales:*:read'),
    ('core', 'Administration', 'System administration and user management', 'shield', true, false, 100, 'core:*:read')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- SEED DATA: Permissions Reference
-- =============================================================================
-- These are stored for reference/audit purposes. Actual permission checks
-- happen in the RBAC layer using profile_permissions and permission_set_permissions.
INSERT INTO permissions (name, description, module, resource, action) VALUES
    ('core:users:read', 'View users', 'core', 'users', 'read'),
    ('core:users:create', 'Create users', 'core', 'users', 'create'),
    ('core:users:update', 'Update users', 'core', 'users', 'update'),
    ('core:users:delete', 'Delete users', 'core', 'users', 'delete'),
    ('core:users:manage', 'Full user management', 'core', 'users', 'manage'),
    ('core:profiles:read', 'View profiles', 'core', 'profiles', 'read'),
    ('core:profiles:manage', 'Manage profiles', 'core', 'profiles', 'manage'),
    ('core:permission_sets:read', 'View permission sets', 'core', 'permission_sets', 'read'),
    ('core:permission_sets:manage', 'Manage permission sets', 'core', 'permission_sets', 'manage'),
    ('core:teams:read', 'View teams', 'core', 'teams', 'read'),
    ('core:teams:manage', 'Manage teams', 'core', 'teams', 'manage'),
    ('core:modules:read', 'View modules', 'core', 'modules', 'read'),
    ('core:modules:manage', 'Manage modules', 'core', 'modules', 'manage'),
    ('core:ai_costs:read', 'View AI costs', 'core', 'ai_costs', 'read'),
    ('sales:proposals:read', 'View proposals', 'sales', 'proposals', 'read'),
    ('sales:proposals:create', 'Create proposals', 'sales', 'proposals', 'create'),
    ('sales:proposals:update', 'Update proposals', 'sales', 'proposals', 'update'),
    ('sales:proposals:delete', 'Delete proposals', 'sales', 'proposals', 'delete'),
    ('sales:mockups:read', 'View mockups', 'sales', 'mockups', 'read'),
    ('sales:mockups:create', 'Create mockups', 'sales', 'mockups', 'create'),
    ('sales:mockups:manage', 'Manage mockups (setup frames)', 'sales', 'mockups', 'manage'),
    ('sales:booking_orders:read', 'View booking orders', 'sales', 'booking_orders', 'read'),
    ('sales:booking_orders:create', 'Create booking orders', 'sales', 'booking_orders', 'create'),
    ('sales:booking_orders:update', 'Update booking orders', 'sales', 'booking_orders', 'update'),
    ('sales:templates:read', 'View templates', 'sales', 'templates', 'read'),
    ('sales:templates:manage', 'Manage templates', 'sales', 'templates', 'manage')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- Done! Your UI database is ready with Enterprise RBAC.
-- =============================================================================
