-- =============================================================================
-- MIGRATION 07: Grant permissions on locations VIEW
-- =============================================================================
-- The locations VIEW was created in migration 04 but GRANT permissions were
-- only applied in migration 01 before the VIEW existed.
-- This migration grants SELECT on the locations VIEW to service_role.
-- =============================================================================

-- Grant SELECT on locations VIEW for each company schema
GRANT SELECT ON backlite_dubai.locations TO service_role;
GRANT SELECT ON backlite_abudhabi.locations TO service_role;
GRANT SELECT ON viola.locations TO service_role;
GRANT SELECT ON backlite_uk.locations TO service_role;

-- Also update the schema creation function to include VIEW grants for new companies
-- (This is already handled by GRANT ALL ON ALL TABLES but we add explicit grant for views)
