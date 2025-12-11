-- =============================================================================
-- INITIAL ADMIN SETUP - Sales Proposals UI Database
-- =============================================================================
-- Run this AFTER ui_schema.sql to create the initial admin invite token.
--
-- This script:
-- 1. Verifies the schema is correctly deployed
-- 2. Creates an initial admin invite token for bootstrap
-- 3. The first user to sign up with this token becomes system_admin
--
-- IMPORTANT: Run this ONCE on a fresh database. Do NOT run on existing data.
-- =============================================================================

-- Verify schema is deployed by checking for required tables
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'profiles') THEN
        RAISE EXCEPTION 'Schema not deployed. Run reset_ui.sql then ui_schema.sql first.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'invite_tokens') THEN
        RAISE EXCEPTION 'Schema not deployed. Run reset_ui.sql then ui_schema.sql first.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM profiles WHERE name = 'system_admin') THEN
        RAISE EXCEPTION 'Default profiles not seeded. Run ui_schema.sql to seed default data.';
    END IF;
END $$;

-- =============================================================================
-- CREATE INITIAL ADMIN INVITE TOKEN
-- =============================================================================
-- Token format: A secure random string (32 bytes base64url encoded)
-- This will be output at the end so you can copy it

-- First, check if any admin users exist
DO $$
DECLARE
    admin_count INTEGER;
    existing_admin_invite INTEGER;
BEGIN
    -- Check for existing admin users
    SELECT COUNT(*) INTO admin_count
    FROM users u
    JOIN profiles p ON u.profile_id = p.id
    WHERE p.name = 'system_admin';

    IF admin_count > 0 THEN
        RAISE NOTICE '============================================================';
        RAISE NOTICE 'WARNING: % admin user(s) already exist in the database.', admin_count;
        RAISE NOTICE 'Initial admin setup may not be necessary.';
        RAISE NOTICE '============================================================';
    END IF;

    -- Check for existing unused admin invite
    SELECT COUNT(*) INTO existing_admin_invite
    FROM invite_tokens
    WHERE profile_name = 'system_admin'
      AND used_at IS NULL
      AND is_revoked = FALSE
      AND expires_at > NOW();

    IF existing_admin_invite > 0 THEN
        RAISE NOTICE '============================================================';
        RAISE NOTICE 'An unused admin invite token already exists.';
        RAISE NOTICE 'Query invite_tokens table to retrieve it.';
        RAISE NOTICE '============================================================';
    END IF;
END $$;

-- Generate a secure token using PostgreSQL's gen_random_uuid()
-- We'll use two UUIDs concatenated and base64-encoded for extra security
INSERT INTO invite_tokens (
    token,
    email,
    profile_name,
    created_by,
    created_at,
    expires_at,
    is_revoked
) VALUES (
    -- Generate a secure token: encode(gen_random_bytes(32), 'base64') equivalent
    replace(replace(
        encode(gen_random_uuid()::text::bytea || gen_random_uuid()::text::bytea, 'base64'),
        '+', '-'), '/', '_'),
    -- CHANGE THIS TO YOUR ADMIN EMAIL
    'admin@example.com',
    'system_admin',
    'SYSTEM_BOOTSTRAP',
    NOW(),
    NOW() + INTERVAL '7 days',
    FALSE
)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- OUTPUT THE INVITE TOKEN
-- =============================================================================
DO $$
DECLARE
    admin_token TEXT;
    admin_email TEXT;
    token_expires TIMESTAMPTZ;
BEGIN
    -- Get the most recent admin invite token
    SELECT token, email, expires_at
    INTO admin_token, admin_email, token_expires
    FROM invite_tokens
    WHERE profile_name = 'system_admin'
      AND used_at IS NULL
      AND is_revoked = FALSE
      AND expires_at > NOW()
    ORDER BY created_at DESC
    LIMIT 1;

    IF admin_token IS NOT NULL THEN
        RAISE NOTICE '';
        RAISE NOTICE '============================================================';
        RAISE NOTICE 'INITIAL ADMIN INVITE TOKEN CREATED SUCCESSFULLY';
        RAISE NOTICE '============================================================';
        RAISE NOTICE '';
        RAISE NOTICE 'Email: %', admin_email;
        RAISE NOTICE 'Token: %', admin_token;
        RAISE NOTICE 'Expires: %', token_expires;
        RAISE NOTICE '';
        RAISE NOTICE 'To complete setup:';
        RAISE NOTICE '1. Update the email in invite_tokens table to your actual admin email';
        RAISE NOTICE '2. Use this token when signing up at your application URL';
        RAISE NOTICE '3. The first user with this token will become system_admin';
        RAISE NOTICE '';
        RAISE NOTICE 'To update the email, run:';
        RAISE NOTICE 'UPDATE invite_tokens SET email = ''your-admin@company.com''';
        RAISE NOTICE 'WHERE token = ''%'';', admin_token;
        RAISE NOTICE '============================================================';
    ELSE
        RAISE NOTICE 'No admin invite token found. This may indicate an error.';
    END IF;
END $$;

-- =============================================================================
-- HELPER QUERY: View all pending invite tokens
-- =============================================================================
-- SELECT id, email, profile_name, token, created_at, expires_at
-- FROM invite_tokens
-- WHERE used_at IS NULL AND is_revoked = FALSE AND expires_at > NOW()
-- ORDER BY created_at DESC;
