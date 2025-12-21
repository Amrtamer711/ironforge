-- ============================================================================
-- SEED DATA FOR SECURITY SUPABASE
-- ============================================================================

-- Register known services
INSERT INTO service_registry (service_name, display_name, description, base_url, allowed_to_call, can_be_called_by)
VALUES
    ('unified-ui', 'Unified UI Gateway', 'API Gateway and authentication proxy', 'http://localhost:3005',
     ARRAY['sales-module', 'asset-management'], ARRAY[]::TEXT[]),

    ('sales-module', 'Sales Module', 'Proposals, bookings, and rate cards', 'http://localhost:8000',
     ARRAY['asset-management'], ARRAY['unified-ui', 'asset-management']),

    ('asset-management', 'Asset Management', 'Networks, locations, and packages', 'http://localhost:8001',
     ARRAY['sales-module'], ARRAY['unified-ui', 'sales-module'])

ON CONFLICT (service_name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    base_url = EXCLUDED.base_url,
    allowed_to_call = EXCLUDED.allowed_to_call,
    can_be_called_by = EXCLUDED.can_be_called_by,
    updated_at = NOW();
