-- =============================================================================
-- SLACK IDENTITY LINKING
-- =============================================================================
-- This migration adds support for:
-- 1. Tracking Slack users who interact with the bot
-- 2. Linking Slack identities to platform users (optional)
-- 3. Global setting to require platform auth for Slack access
--
-- Strategy:
-- - NOW: Slack users can use the bot freely, we just track their identity
-- - LATER: When admin adds user to platform, link their Slack identity
-- - FUTURE: Enable require_platform_auth to block unapproved Slack users
--
-- Run this in: UI-Module-Dev (and UI-Module-Prod when ready)
-- =============================================================================

-- =============================================================================
-- SLACK IDENTITIES TABLE
-- =============================================================================
-- Tracks all Slack users who have interacted with the bot
-- user_id is NULL until they're linked to a platform user
CREATE TABLE IF NOT EXISTS slack_identities (
    id BIGSERIAL PRIMARY KEY,

    -- Slack identification
    slack_user_id TEXT NOT NULL UNIQUE,      -- Slack's U... ID
    slack_workspace_id TEXT NOT NULL,        -- Slack's T... workspace ID

    -- Profile info from Slack API
    slack_email TEXT,                        -- Email from Slack profile
    slack_display_name TEXT,                 -- Display name from Slack
    slack_real_name TEXT,                    -- Real name from Slack
    slack_avatar_url TEXT,                   -- Avatar URL

    -- Link to platform user (NULL until linked)
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,

    -- Timestamps
    first_seen_at TIMESTAMPTZ DEFAULT NOW(), -- When they first used the bot
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),  -- Last interaction
    linked_at TIMESTAMPTZ,                   -- When linked to platform user
    linked_by TEXT,                          -- Who linked them (admin user id)

    -- Status
    is_blocked BOOLEAN DEFAULT FALSE,        -- Manual block by admin
    blocked_reason TEXT,
    blocked_at TIMESTAMPTZ,
    blocked_by TEXT,

    -- Metadata for extensibility
    metadata_json JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_slack_identities_user_id ON slack_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_slack_identities_email ON slack_identities(slack_email);
CREATE INDEX IF NOT EXISTS idx_slack_identities_workspace ON slack_identities(slack_workspace_id);
CREATE INDEX IF NOT EXISTS idx_slack_identities_last_seen ON slack_identities(last_seen_at DESC);

-- =============================================================================
-- SYSTEM SETTINGS TABLE
-- =============================================================================
-- Global configuration for the platform
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
);

-- Default setting: Slack auth NOT required (open access)
INSERT INTO system_settings (key, value, description)
VALUES (
    'slack_require_platform_auth',
    'false'::jsonb,
    'When true, Slack users must be linked to an active platform user to use the bot'
)
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- FUNCTION: Record Slack user interaction
-- =============================================================================
-- Called by the bot when a Slack user interacts
-- Updates existing record or creates new one
CREATE OR REPLACE FUNCTION record_slack_interaction(
    p_slack_user_id TEXT,
    p_slack_workspace_id TEXT,
    p_slack_email TEXT DEFAULT NULL,
    p_slack_display_name TEXT DEFAULT NULL,
    p_slack_real_name TEXT DEFAULT NULL,
    p_slack_avatar_url TEXT DEFAULT NULL
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
BEGIN
    -- Get require_platform_auth setting
    SELECT (value)::boolean INTO v_require_auth
    FROM system_settings
    WHERE key = 'slack_require_platform_auth';

    v_require_auth := COALESCE(v_require_auth, FALSE);

    -- Upsert slack identity
    INSERT INTO slack_identities (
        slack_user_id,
        slack_workspace_id,
        slack_email,
        slack_display_name,
        slack_real_name,
        slack_avatar_url,
        last_seen_at
    )
    VALUES (
        p_slack_user_id,
        p_slack_workspace_id,
        p_slack_email,
        p_slack_display_name,
        p_slack_real_name,
        p_slack_avatar_url,
        NOW()
    )
    ON CONFLICT (slack_user_id) DO UPDATE SET
        slack_email = COALESCE(EXCLUDED.slack_email, slack_identities.slack_email),
        slack_display_name = COALESCE(EXCLUDED.slack_display_name, slack_identities.slack_display_name),
        slack_real_name = COALESCE(EXCLUDED.slack_real_name, slack_identities.slack_real_name),
        slack_avatar_url = COALESCE(EXCLUDED.slack_avatar_url, slack_identities.slack_avatar_url),
        last_seen_at = NOW(),
        updated_at = NOW()
    RETURNING id, user_id, is_blocked INTO v_identity_id, v_user_id, v_is_blocked;

    -- Return the identity info
    RETURN QUERY SELECT
        v_identity_id,
        v_user_id,
        (v_user_id IS NOT NULL)::BOOLEAN,
        v_is_blocked,
        v_require_auth;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- FUNCTION: Check if Slack user is authorized
-- =============================================================================
-- Quick check for whether a Slack user can use the bot
CREATE OR REPLACE FUNCTION check_slack_authorization(
    p_slack_user_id TEXT
)
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
BEGIN
    -- Get setting
    SELECT (value)::boolean INTO v_require_auth
    FROM system_settings
    WHERE key = 'slack_require_platform_auth';

    v_require_auth := COALESCE(v_require_auth, FALSE);

    -- Get slack identity
    SELECT * INTO v_identity
    FROM slack_identities
    WHERE slack_user_id = p_slack_user_id;

    -- Case 1: Unknown user, auth not required -> authorized
    IF v_identity IS NULL AND NOT v_require_auth THEN
        RETURN QUERY SELECT TRUE, 'open_access'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Case 2: Unknown user, auth required -> not authorized
    IF v_identity IS NULL AND v_require_auth THEN
        RETURN QUERY SELECT FALSE, 'unknown_user'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Case 3: Known but blocked
    IF v_identity.is_blocked THEN
        RETURN QUERY SELECT FALSE, 'blocked'::TEXT, v_identity.user_id, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Case 4: Not linked, auth not required -> authorized
    IF v_identity.user_id IS NULL AND NOT v_require_auth THEN
        RETURN QUERY SELECT TRUE, 'open_access'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Case 5: Not linked, auth required -> not authorized
    IF v_identity.user_id IS NULL AND v_require_auth THEN
        RETURN QUERY SELECT FALSE, 'not_linked'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Case 6: Linked - check if platform user is active
    SELECT u.*, p.name as profile_name INTO v_user
    FROM users u
    LEFT JOIN profiles p ON u.profile_id = p.id
    WHERE u.id = v_identity.user_id;

    IF v_user IS NULL THEN
        RETURN QUERY SELECT FALSE, 'user_not_found'::TEXT, v_identity.user_id, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF NOT v_user.is_active THEN
        RETURN QUERY SELECT FALSE, 'user_inactive'::TEXT, v_identity.user_id, v_user.name, v_user.profile_name;
        RETURN;
    END IF;

    -- Authorized!
    RETURN QUERY SELECT TRUE, 'linked_active'::TEXT, v_identity.user_id, v_user.name, v_user.profile_name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- FUNCTION: Link Slack identity to platform user
-- =============================================================================
-- Admin function to manually link a Slack identity to a user
CREATE OR REPLACE FUNCTION link_slack_identity(
    p_slack_user_id TEXT,
    p_platform_user_id TEXT,
    p_linked_by TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_existing_link TEXT;
BEGIN
    -- Check if this Slack ID is already linked to someone else
    SELECT user_id INTO v_existing_link
    FROM slack_identities
    WHERE slack_user_id = p_slack_user_id
    AND user_id IS NOT NULL
    AND user_id != p_platform_user_id;

    IF v_existing_link IS NOT NULL THEN
        RAISE EXCEPTION 'Slack user % is already linked to platform user %', p_slack_user_id, v_existing_link;
    END IF;

    -- Check if platform user exists
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_platform_user_id) THEN
        RAISE EXCEPTION 'Platform user not found: %', p_platform_user_id;
    END IF;

    -- Update or create the link
    UPDATE slack_identities
    SET
        user_id = p_platform_user_id,
        linked_at = NOW(),
        linked_by = p_linked_by,
        updated_at = NOW()
    WHERE slack_user_id = p_slack_user_id;

    IF NOT FOUND THEN
        -- Create a minimal record if it doesn't exist
        INSERT INTO slack_identities (slack_user_id, slack_workspace_id, user_id, linked_at, linked_by)
        VALUES (p_slack_user_id, 'unknown', p_platform_user_id, NOW(), p_linked_by);
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- FUNCTION: Auto-link by email
-- =============================================================================
-- Attempts to automatically link Slack identities to platform users by email
CREATE OR REPLACE FUNCTION auto_link_slack_by_email()
RETURNS TABLE(
    slack_user_id TEXT,
    slack_email TEXT,
    platform_user_id TEXT,
    platform_user_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH linkable AS (
        SELECT si.slack_user_id, si.slack_email, u.id as user_id, u.name as user_name
        FROM slack_identities si
        INNER JOIN users u ON LOWER(si.slack_email) = LOWER(u.email)
        WHERE si.user_id IS NULL
        AND si.slack_email IS NOT NULL
        AND u.is_active = TRUE
    ),
    updated AS (
        UPDATE slack_identities si
        SET
            user_id = l.user_id,
            linked_at = NOW(),
            linked_by = 'auto_link_by_email',
            updated_at = NOW()
        FROM linkable l
        WHERE si.slack_user_id = l.slack_user_id
        RETURNING si.slack_user_id
    )
    SELECT l.slack_user_id, l.slack_email, l.user_id, l.user_name
    FROM linkable l;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- FUNCTION: Unlink Slack identity
-- =============================================================================
CREATE OR REPLACE FUNCTION unlink_slack_identity(
    p_slack_user_id TEXT
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE slack_identities
    SET
        user_id = NULL,
        linked_at = NULL,
        linked_by = NULL,
        updated_at = NOW()
    WHERE slack_user_id = p_slack_user_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- FUNCTION: Block/Unblock Slack user
-- =============================================================================
CREATE OR REPLACE FUNCTION set_slack_blocked(
    p_slack_user_id TEXT,
    p_blocked BOOLEAN,
    p_reason TEXT DEFAULT NULL,
    p_blocked_by TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE slack_identities
    SET
        is_blocked = p_blocked,
        blocked_reason = CASE WHEN p_blocked THEN p_reason ELSE NULL END,
        blocked_at = CASE WHEN p_blocked THEN NOW() ELSE NULL END,
        blocked_by = CASE WHEN p_blocked THEN p_blocked_by ELSE NULL END,
        updated_at = NOW()
    WHERE slack_user_id = p_slack_user_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- VIEW: Slack users pending linking
-- =============================================================================
-- Shows Slack users who aren't linked but have matching emails in users table
CREATE OR REPLACE VIEW slack_pending_links AS
SELECT
    si.id,
    si.slack_user_id,
    si.slack_workspace_id,
    si.slack_email,
    si.slack_display_name,
    si.slack_real_name,
    si.first_seen_at,
    si.last_seen_at,
    u.id as potential_user_id,
    u.name as potential_user_name,
    u.email as potential_user_email,
    p.display_name as potential_user_profile
FROM slack_identities si
LEFT JOIN users u ON LOWER(si.slack_email) = LOWER(u.email)
LEFT JOIN profiles p ON u.profile_id = p.id
WHERE si.user_id IS NULL
AND si.is_blocked = FALSE
ORDER BY
    (u.id IS NOT NULL) DESC,  -- Potential matches first
    si.last_seen_at DESC;

-- =============================================================================
-- VIEW: All Slack identities with platform user info
-- =============================================================================
CREATE OR REPLACE VIEW slack_identities_full AS
SELECT
    si.*,
    u.name as platform_user_name,
    u.email as platform_user_email,
    u.is_active as platform_user_active,
    p.name as platform_profile_name,
    p.display_name as platform_profile_display
FROM slack_identities si
LEFT JOIN users u ON si.user_id = u.id
LEFT JOIN profiles p ON u.profile_id = p.id
ORDER BY si.last_seen_at DESC;

-- =============================================================================
-- GRANTS
-- =============================================================================
GRANT SELECT ON slack_identities TO service_role;
GRANT SELECT ON slack_pending_links TO service_role;
GRANT SELECT ON slack_identities_full TO service_role;
GRANT SELECT ON system_settings TO service_role;
GRANT EXECUTE ON FUNCTION record_slack_interaction TO service_role;
GRANT EXECUTE ON FUNCTION check_slack_authorization TO service_role;
GRANT EXECUTE ON FUNCTION link_slack_identity TO service_role;
GRANT EXECUTE ON FUNCTION unlink_slack_identity TO service_role;
GRANT EXECUTE ON FUNCTION auto_link_slack_by_email TO service_role;
GRANT EXECUTE ON FUNCTION set_slack_blocked TO service_role;

-- =============================================================================
-- Done!
-- =============================================================================
-- Usage:
--
-- 1. Bot records interaction on every Slack event:
--    SELECT * FROM record_slack_interaction('U12345', 'T67890', 'user@company.com', 'John');
--
-- 2. (Optional) Bot checks authorization if strict mode is enabled:
--    SELECT * FROM check_slack_authorization('U12345');
--
-- 3. Admin links a Slack user to platform user:
--    SELECT link_slack_identity('U12345', 'user-uuid-here', 'admin-uuid');
--
-- 4. Admin enables strict mode (only linked users can use Slack):
--    UPDATE system_settings SET value = 'true' WHERE key = 'slack_require_platform_auth';
--
-- 5. Auto-link all Slack users who have matching emails:
--    SELECT * FROM auto_link_slack_by_email();
--
-- 6. View pending links (Slack users with potential matches):
--    SELECT * FROM slack_pending_links;
-- =============================================================================
