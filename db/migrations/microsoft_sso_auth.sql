-- =============================================================================
-- MICROSOFT SSO AUTHENTICATION UPDATE
-- =============================================================================
-- This migration updates the auth trigger to support:
-- 1. Admin pre-creates users with email + profile + team + modules
-- 2. User signs in via Microsoft SSO
-- 3. If pre-created → link and activate
-- 4. If not pre-created → create as INACTIVE (blocked)
--
-- Run this in: UI-Module-Dev (and UI-Module-Prod when ready)
-- =============================================================================

-- =============================================================================
-- UPDATE: Sync users from auth.users with pre-approval support
-- =============================================================================
CREATE OR REPLACE FUNCTION public.sync_user_from_auth()
RETURNS TRIGGER AS $$
DECLARE
    pending_user RECORD;
    default_profile_id BIGINT;
    user_name TEXT;
BEGIN
    -- Extract name from Microsoft SSO metadata
    user_name := COALESCE(
        NEW.raw_user_meta_data->>'name',
        NEW.raw_user_meta_data->>'full_name',
        split_part(NEW.email, '@', 1)  -- Fallback to email prefix
    );

    -- Check if admin has pre-created this user (by email)
    SELECT * INTO pending_user
    FROM public.users
    WHERE email = NEW.email;

    IF pending_user IS NOT NULL THEN
        -- User was PRE-CREATED by admin
        -- Link the auth.users id and update metadata
        UPDATE public.users
        SET
            id = NEW.id::TEXT,
            name = COALESCE(user_name, pending_user.name),
            avatar_url = COALESCE(NEW.raw_user_meta_data->>'avatar_url', pending_user.avatar_url),
            -- Keep is_active as set by admin (should be TRUE for pre-created)
            -- Keep profile_id as set by admin
            last_login_at = NOW(),
            updated_at = NOW()
        WHERE email = NEW.email;

    ELSE
        -- User NOT pre-approved by admin
        -- Create as INACTIVE - they cannot access the app until admin approves
        SELECT id INTO default_profile_id
        FROM public.profiles
        WHERE name = 'viewer';  -- Minimal permissions profile

        INSERT INTO public.users (
            id,
            email,
            name,
            avatar_url,
            profile_id,
            is_active,  -- FALSE = blocked until admin approves
            created_at,
            updated_at
        )
        VALUES (
            NEW.id::TEXT,
            NEW.email,
            user_name,
            NEW.raw_user_meta_data->>'avatar_url',
            default_profile_id,
            FALSE,  -- BLOCKED - requires admin approval
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            name = COALESCE(EXCLUDED.name, users.name),
            avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
            last_login_at = NOW(),
            updated_at = NOW();
            -- Note: is_active and profile_id are NOT updated on conflict
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Ensure trigger exists
DROP TRIGGER IF EXISTS on_auth_user_sync ON auth.users;
CREATE TRIGGER on_auth_user_sync
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.sync_user_from_auth();

-- =============================================================================
-- HELPER: Function for admin to pre-create users
-- =============================================================================
-- This function allows admins to create user records before the user signs in
-- The id will be NULL until the user actually signs in via Microsoft SSO

CREATE OR REPLACE FUNCTION public.admin_create_pending_user(
    p_email TEXT,
    p_name TEXT DEFAULT NULL,
    p_profile_name TEXT DEFAULT 'sales_user',
    p_team_id BIGINT DEFAULT NULL,
    p_created_by TEXT DEFAULT NULL
)
RETURNS TABLE(user_id TEXT, email TEXT, profile_name TEXT, is_active BOOLEAN) AS $$
DECLARE
    v_profile_id BIGINT;
    v_user_id TEXT;
BEGIN
    -- Get profile ID
    SELECT id INTO v_profile_id
    FROM public.profiles
    WHERE name = p_profile_name;

    IF v_profile_id IS NULL THEN
        RAISE EXCEPTION 'Profile not found: %', p_profile_name;
    END IF;

    -- Check if user already exists
    IF EXISTS (SELECT 1 FROM public.users WHERE users.email = p_email) THEN
        RAISE EXCEPTION 'User with email % already exists', p_email;
    END IF;

    -- Generate a temporary UUID for the user (will be replaced on SSO login)
    v_user_id := 'pending-' || gen_random_uuid()::TEXT;

    -- Create the pending user
    INSERT INTO public.users (
        id,
        email,
        name,
        profile_id,
        is_active,
        created_at,
        updated_at,
        metadata_json
    )
    VALUES (
        v_user_id,
        p_email,
        p_name,
        v_profile_id,
        TRUE,  -- Active when pre-created by admin
        NOW(),
        NOW(),
        jsonb_build_object('created_by', p_created_by, 'pending_sso', true)
    );

    -- Add to team if specified
    IF p_team_id IS NOT NULL THEN
        INSERT INTO public.team_members (team_id, user_id, role, joined_at)
        VALUES (p_team_id, v_user_id, 'member', NOW())
        ON CONFLICT DO NOTHING;
    END IF;

    -- Return the created user info
    RETURN QUERY
    SELECT
        v_user_id,
        p_email,
        p_profile_name,
        TRUE::BOOLEAN;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- HELPER: Function to approve a pending (unapproved) user
-- =============================================================================
CREATE OR REPLACE FUNCTION public.admin_approve_user(
    p_user_id TEXT,
    p_profile_name TEXT DEFAULT NULL,
    p_approved_by TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_profile_id BIGINT;
BEGIN
    -- Get new profile ID if specified
    IF p_profile_name IS NOT NULL THEN
        SELECT id INTO v_profile_id
        FROM public.profiles
        WHERE name = p_profile_name;

        IF v_profile_id IS NULL THEN
            RAISE EXCEPTION 'Profile not found: %', p_profile_name;
        END IF;
    END IF;

    -- Update user
    UPDATE public.users
    SET
        is_active = TRUE,
        profile_id = COALESCE(v_profile_id, profile_id),
        updated_at = NOW(),
        metadata_json = COALESCE(metadata_json, '{}'::jsonb) ||
            jsonb_build_object('approved_by', p_approved_by, 'approved_at', NOW())
    WHERE id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'User not found: %', p_user_id;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- VIEW: Pending users awaiting approval
-- =============================================================================
CREATE OR REPLACE VIEW public.pending_users AS
SELECT
    u.id,
    u.email,
    u.name,
    u.is_active,
    u.created_at,
    p.name as profile_name,
    p.display_name as profile_display_name,
    u.metadata_json->>'pending_sso' as is_pending_sso
FROM public.users u
LEFT JOIN public.profiles p ON u.profile_id = p.id
WHERE u.is_active = FALSE
   OR u.id LIKE 'pending-%'
ORDER BY u.created_at DESC;

-- Grant access to service role
GRANT SELECT ON public.pending_users TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_create_pending_user TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_approve_user TO service_role;

-- =============================================================================
-- Done!
-- =============================================================================
-- Admin workflow:
-- 1. Call admin_create_pending_user('email@company.com', 'John Doe', 'sales_manager')
-- 2. User signs in with Microsoft SSO
-- 3. Trigger links the auth.users id to the pre-created user
-- 4. User has immediate access with correct profile
--
-- For unapproved users (signed in without pre-creation):
-- 1. User signs in with Microsoft SSO
-- 2. Trigger creates user with is_active = FALSE
-- 3. User sees "Access Pending" screen
-- 4. Admin calls admin_approve_user('user-id', 'sales_user')
-- 5. User can now access the app
-- =============================================================================
