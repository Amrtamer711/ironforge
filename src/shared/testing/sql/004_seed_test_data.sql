-- ============================================================================
-- MMG TESTING FRAMEWORK: Business Test Data
-- ============================================================================
-- This file seeds realistic business data for testing:
-- - Proposals in various states
-- - Booking orders in different approval stages
-- - Approval workflows at each step
-- - Sample locations and rate cards per company
--
-- Run this AFTER 003_seed_test_users.sql
-- Target: Sales Module Supabase (proposals, booking orders)
-- ============================================================================

-- ============================================================================
-- LOCATIONS (Company Schema: backlite_dubai)
-- ============================================================================

-- Ensure company schema exists (should already exist)
INSERT INTO backlite_dubai.networks (id, name, description) VALUES
    (1, 'Digital Network', 'Premium digital advertising network'),
    (2, 'Static Network', 'Traditional static billboard network'),
    (3, 'Airport Network', 'DXB Airport exclusive placements')
ON CONFLICT (id) DO NOTHING;

INSERT INTO backlite_dubai.asset_types (id, name, display_name) VALUES
    (1, 'digital_screen', 'Digital Screen'),
    (2, 'billboard', 'Billboard'),
    (3, 'unipole', 'Unipole'),
    (4, 'bridge_banner', 'Bridge Banner')
ON CONFLICT (id) DO NOTHING;

INSERT INTO backlite_dubai.locations (id, location_key, name, network_id, type_id, lat, lng, is_active) VALUES
    (1, 'SZR-001', 'Sheikh Zayed Road - Interchange 1', 1, 1, 25.0657, 55.1713, true),
    (2, 'SZR-002', 'Sheikh Zayed Road - Mall of Emirates', 1, 1, 25.1185, 55.2004, true),
    (3, 'MARINA-001', 'Dubai Marina - JBR Walk', 1, 1, 25.0763, 55.1390, true),
    (4, 'DOWNTOWN-001', 'Downtown - Burj Khalifa View', 2, 2, 25.1972, 55.2744, true),
    (5, 'DXB-T1-001', 'DXB Terminal 1 - Arrivals', 3, 1, 25.2528, 55.3644, true),
    (6, 'DXB-T3-001', 'DXB Terminal 3 - Concourse A', 3, 1, 25.2544, 55.3656, true),
    (7, 'BUSINESS-001', 'Business Bay - Canal Walk', 2, 3, 25.1850, 55.2707, true),
    (8, 'JLT-001', 'JLT Cluster D - Main Boulevard', 2, 2, 25.0689, 55.1460, true)
ON CONFLICT (id) DO UPDATE SET is_active = EXCLUDED.is_active;

-- Rate cards for Dubai locations
INSERT INTO backlite_dubai.rate_cards (location_id, rate_type, weekly_rate, upload_fee, production_fee, valid_from) VALUES
    (1, 'standard', 15000.00, 500.00, 2500.00, '2024-01-01'),
    (2, 'standard', 18000.00, 500.00, 2500.00, '2024-01-01'),
    (3, 'standard', 12000.00, 400.00, 2000.00, '2024-01-01'),
    (4, 'standard', 22000.00, 600.00, 3000.00, '2024-01-01'),
    (5, 'premium', 35000.00, 800.00, 4000.00, '2024-01-01'),
    (6, 'premium', 38000.00, 800.00, 4000.00, '2024-01-01'),
    (7, 'standard', 14000.00, 450.00, 2200.00, '2024-01-01'),
    (8, 'standard', 11000.00, 400.00, 1800.00, '2024-01-01')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- PROPOSALS (Various States)
-- ============================================================================

-- Proposal 1: Draft by rep_dubai_1 (Dubai sales rep)
INSERT INTO public.proposals_log (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data) VALUES
    (1, 'test-rep_dubai_1', 'rep.dubai1@mmg.ae', 'Emirates NBD', 'combined', '165000', 'AED',
     'SZR-001, SZR-002, MARINA-001',
     '{"status": "draft", "duration_weeks": 4, "start_date": "2025-02-01", "locations": [
        {"key": "SZR-001", "name": "Sheikh Zayed Road - Interchange 1", "weekly_rate": 15000, "upload_fee": 500},
        {"key": "SZR-002", "name": "Sheikh Zayed Road - Mall of Emirates", "weekly_rate": 18000, "upload_fee": 500},
        {"key": "MARINA-001", "name": "Dubai Marina - JBR Walk", "weekly_rate": 12000, "upload_fee": 400}
     ], "client_contact": "Mohammed Ali", "notes": "Premium placement request"}'
    )
ON CONFLICT (id) DO NOTHING;

-- Proposal 2: Submitted by rep_dubai_1, pending approval
INSERT INTO public.proposals_log (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data) VALUES
    (2, 'test-rep_dubai_1', 'rep.dubai1@mmg.ae', 'Etisalat', 'separate', '312000', 'AED',
     'DOWNTOWN-001, DXB-T1-001, DXB-T3-001',
     '{"status": "submitted", "duration_weeks": 8, "start_date": "2025-03-01", "locations": [
        {"key": "DOWNTOWN-001", "name": "Downtown - Burj Khalifa View", "weekly_rate": 22000, "upload_fee": 600},
        {"key": "DXB-T1-001", "name": "DXB Terminal 1 - Arrivals", "weekly_rate": 35000, "upload_fee": 800},
        {"key": "DXB-T3-001", "name": "DXB Terminal 3 - Concourse A", "weekly_rate": 38000, "upload_fee": 800}
     ], "client_contact": "Fatima Hassan", "agency": "Publicis", "submitted_at": "2025-01-15T10:30:00Z"}'
    )
ON CONFLICT (id) DO NOTHING;

-- Proposal 3: Approved by rep_dubai_2 (for cross-user visibility testing)
INSERT INTO public.proposals_log (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data) VALUES
    (3, 'test-rep_dubai_2', 'rep.dubai2@mmg.ae', 'Majid Al Futtaim', 'combined', '88000', 'AED',
     'JLT-001, BUSINESS-001',
     '{"status": "approved", "duration_weeks": 4, "start_date": "2025-01-20", "locations": [
        {"key": "JLT-001", "name": "JLT Cluster D - Main Boulevard", "weekly_rate": 11000, "upload_fee": 400},
        {"key": "BUSINESS-001", "name": "Business Bay - Canal Walk", "weekly_rate": 14000, "upload_fee": 450}
     ], "client_contact": "Ahmed Rashid", "approved_at": "2025-01-18T14:00:00Z", "approved_by": "hos_backlite"}'
    )
ON CONFLICT (id) DO NOTHING;

-- Proposal 4: Large proposal for coordinator approval testing
INSERT INTO public.proposals_log (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data) VALUES
    (4, 'test-rep_dubai_1', 'rep.dubai1@mmg.ae', 'Noon', 'combined', '520000', 'AED',
     'SZR-001, SZR-002, MARINA-001, DOWNTOWN-001, DXB-T1-001',
     '{"status": "submitted", "duration_weeks": 12, "start_date": "2025-04-01", "locations": [
        {"key": "SZR-001", "name": "Sheikh Zayed Road - Interchange 1", "weekly_rate": 15000},
        {"key": "SZR-002", "name": "Sheikh Zayed Road - Mall of Emirates", "weekly_rate": 18000},
        {"key": "MARINA-001", "name": "Dubai Marina - JBR Walk", "weekly_rate": 12000},
        {"key": "DOWNTOWN-001", "name": "Downtown - Burj Khalifa View", "weekly_rate": 22000},
        {"key": "DXB-T1-001", "name": "DXB Terminal 1 - Arrivals", "weekly_rate": 35000}
     ], "client_contact": "Sara Al Maktoum", "brand": "Noon Express", "campaign": "UAE National Day 2025", "requires_coordinator_review": true}'
    )
ON CONFLICT (id) DO NOTHING;

-- Link proposals to locations
INSERT INTO public.proposal_locations (proposal_id, location_key, location_company, location_display_name, start_date, duration_weeks, net_rate, upload_fee, production_fee)
SELECT 1, 'SZR-001', 'backlite_dubai', 'Sheikh Zayed Road - Interchange 1', '2025-02-01', 4, 15000, 500, 2500 WHERE NOT EXISTS (SELECT 1 FROM public.proposal_locations WHERE proposal_id = 1 AND location_key = 'SZR-001');
INSERT INTO public.proposal_locations (proposal_id, location_key, location_company, location_display_name, start_date, duration_weeks, net_rate, upload_fee, production_fee)
SELECT 1, 'SZR-002', 'backlite_dubai', 'Sheikh Zayed Road - Mall of Emirates', '2025-02-01', 4, 18000, 500, 2500 WHERE NOT EXISTS (SELECT 1 FROM public.proposal_locations WHERE proposal_id = 1 AND location_key = 'SZR-002');
INSERT INTO public.proposal_locations (proposal_id, location_key, location_company, location_display_name, start_date, duration_weeks, net_rate, upload_fee, production_fee)
SELECT 1, 'MARINA-001', 'backlite_dubai', 'Dubai Marina - JBR Walk', '2025-02-01', 4, 12000, 400, 2000 WHERE NOT EXISTS (SELECT 1 FROM public.proposal_locations WHERE proposal_id = 1 AND location_key = 'MARINA-001');

-- ============================================================================
-- BOOKING ORDERS (Different Approval States)
-- ============================================================================

-- BO 1: Pending coordinator review
INSERT INTO public.booking_orders (id, bo_ref, user_id, company, original_file_path, original_file_type, bo_number, client, agency, brand_campaign, net_pre_vat, vat_value, gross_amount, sales_person, locations_json, extraction_method, parsed_by) VALUES
    (1, 'BO-2025-001', 'test-rep_dubai_1', 'backlite_dubai', '/uploads/bos/emirates_nbd_q1.pdf', 'pdf',
     'ENBD-2025-001', 'Emirates NBD', 'Leo Burnett', 'Q1 Brand Campaign',
     165000.00, 8250.00, 173250.00, 'rep.dubai1@mmg.ae',
     '[{"location": "SZR-001", "start_date": "2025-02-01", "weeks": 4}, {"location": "SZR-002", "start_date": "2025-02-01", "weeks": 4}]',
     'ai_extraction', 'test-rep_dubai_1'
    )
ON CONFLICT (id) DO NOTHING;

-- BO 2: Approved by coordinator, pending HOS
INSERT INTO public.booking_orders (id, bo_ref, user_id, company, original_file_path, original_file_type, bo_number, client, agency, brand_campaign, net_pre_vat, vat_value, gross_amount, sales_person, locations_json, extraction_method, parsed_by) VALUES
    (2, 'BO-2025-002', 'test-rep_dubai_1', 'backlite_dubai', '/uploads/bos/etisalat_campaign.pdf', 'pdf',
     'ETI-2025-001', 'Etisalat', 'Publicis', 'Digital Transformation',
     312000.00, 15600.00, 327600.00, 'rep.dubai1@mmg.ae',
     '[{"location": "DOWNTOWN-001", "start_date": "2025-03-01", "weeks": 8}, {"location": "DXB-T1-001", "start_date": "2025-03-01", "weeks": 8}]',
     'ai_extraction', 'test-rep_dubai_1'
    )
ON CONFLICT (id) DO NOTHING;

-- BO 3: Fully approved, ready for finance
INSERT INTO public.booking_orders (id, bo_ref, user_id, company, original_file_path, original_file_type, bo_number, client, agency, brand_campaign, net_pre_vat, vat_value, gross_amount, sales_person, locations_json, extraction_method, parsed_by) VALUES
    (3, 'BO-2025-003', 'test-rep_dubai_2', 'backlite_dubai', '/uploads/bos/maf_retail.pdf', 'pdf',
     'MAF-2025-001', 'Majid Al Futtaim', 'OMD', 'Retail Summer Campaign',
     88000.00, 4400.00, 92400.00, 'rep.dubai2@mmg.ae',
     '[{"location": "JLT-001", "start_date": "2025-01-20", "weeks": 4}, {"location": "BUSINESS-001", "start_date": "2025-01-20", "weeks": 4}]',
     'ai_extraction', 'test-rep_dubai_2'
    )
ON CONFLICT (id) DO NOTHING;

-- BO 4: Rejected by coordinator (for testing rejection flows)
INSERT INTO public.booking_orders (id, bo_ref, user_id, company, original_file_path, original_file_type, bo_number, client, agency, brand_campaign, net_pre_vat, vat_value, gross_amount, sales_person, locations_json, extraction_method, needs_review, parsed_by) VALUES
    (4, 'BO-2025-004', 'test-rep_dubai_1', 'backlite_dubai', '/uploads/bos/incomplete_bo.pdf', 'pdf',
     NULL, 'Unknown Client', NULL, NULL,
     50000.00, 2500.00, 52500.00, 'rep.dubai1@mmg.ae',
     '[{"location": "SZR-001", "start_date": null, "weeks": null}]',
     'manual_entry', true, 'test-rep_dubai_1'
    )
ON CONFLICT (id) DO NOTHING;

-- BO Locations
INSERT INTO public.bo_locations (bo_id, location_key, location_company, start_date, end_date, duration_weeks, net_rate)
SELECT 1, 'SZR-001', 'backlite_dubai', '2025-02-01', '2025-03-01', 4, 60000.00 WHERE NOT EXISTS (SELECT 1 FROM public.bo_locations WHERE bo_id = 1 AND location_key = 'SZR-001');
INSERT INTO public.bo_locations (bo_id, location_key, location_company, start_date, end_date, duration_weeks, net_rate)
SELECT 1, 'SZR-002', 'backlite_dubai', '2025-02-01', '2025-03-01', 4, 72000.00 WHERE NOT EXISTS (SELECT 1 FROM public.bo_locations WHERE bo_id = 1 AND location_key = 'SZR-002');

-- ============================================================================
-- APPROVAL WORKFLOWS (Each stage represented)
-- ============================================================================

-- Workflow 1: Pending coordinator
INSERT INTO public.bo_approval_workflows (workflow_id, bo_id, status, workflow_data) VALUES
    ('WF-001', 1, 'pending',
     '{"submitted_at": "2025-01-15T09:00:00Z", "submitted_by": "test-rep_dubai_1", "assigned_coordinator": null, "steps": [
        {"step": "coordinator", "status": "pending", "assigned_to": null},
        {"step": "hos", "status": "pending", "assigned_to": "test-hos_backlite"},
        {"step": "finance", "status": "pending", "assigned_to": "test-finance_1"}
     ]}'
    )
ON CONFLICT (workflow_id) DO UPDATE SET status = 'pending';

-- Workflow 2: Coordinator approved, pending HOS
INSERT INTO public.bo_approval_workflows (workflow_id, bo_id, status, workflow_data) VALUES
    ('WF-002', 2, 'coordinator_approved',
     '{"submitted_at": "2025-01-10T10:00:00Z", "submitted_by": "test-rep_dubai_1", "steps": [
        {"step": "coordinator", "status": "approved", "approved_by": "test-coordinator_1", "approved_at": "2025-01-11T14:00:00Z", "notes": "All details verified"},
        {"step": "hos", "status": "pending", "assigned_to": "test-hos_backlite"},
        {"step": "finance", "status": "pending", "assigned_to": "test-finance_1"}
     ]}'
    )
ON CONFLICT (workflow_id) DO UPDATE SET status = 'coordinator_approved';

-- Workflow 3: HOS approved, pending finance (completed approval chain)
INSERT INTO public.bo_approval_workflows (workflow_id, bo_id, status, workflow_data) VALUES
    ('WF-003', 3, 'hos_approved',
     '{"submitted_at": "2025-01-05T08:00:00Z", "submitted_by": "test-rep_dubai_2", "steps": [
        {"step": "coordinator", "status": "approved", "approved_by": "test-coordinator_1", "approved_at": "2025-01-06T10:00:00Z"},
        {"step": "hos", "status": "approved", "approved_by": "test-hos_backlite", "approved_at": "2025-01-07T11:00:00Z", "notes": "Good margins approved"},
        {"step": "finance", "status": "pending", "assigned_to": "test-finance_1"}
     ]}'
    )
ON CONFLICT (workflow_id) DO UPDATE SET status = 'hos_approved';

-- Workflow 4: Rejected
INSERT INTO public.bo_approval_workflows (workflow_id, bo_id, status, workflow_data) VALUES
    ('WF-004', 4, 'coordinator_rejected',
     '{"submitted_at": "2025-01-14T15:00:00Z", "submitted_by": "test-rep_dubai_1", "steps": [
        {"step": "coordinator", "status": "rejected", "rejected_by": "test-coordinator_1", "rejected_at": "2025-01-14T16:30:00Z", "reason": "Missing required fields: start dates, client PO number"}
     ]}'
    )
ON CONFLICT (workflow_id) DO UPDATE SET status = 'coordinator_rejected';

-- ============================================================================
-- ADDITIONAL TEST SCENARIOS
-- ============================================================================

-- Multi-company proposal (for rep_multi_company testing)
INSERT INTO public.proposals_log (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data) VALUES
    (5, 'test-rep_multi_company', 'rep.multi@mmg.ae', 'Al Futtaim Motors', 'combined', '250000', 'AED',
     'SZR-001, MARINA-001',
     '{"status": "draft", "duration_weeks": 6, "start_date": "2025-05-01", "locations": [
        {"key": "SZR-001", "company": "backlite_dubai", "name": "Sheikh Zayed Road - Interchange 1"},
        {"key": "MARINA-001", "company": "backlite_dubai", "name": "Dubai Marina - JBR Walk"}
     ], "client_contact": "Yousef Al Futtaim", "notes": "Multi-company campaign - Dubai + Viola placements"}'
    )
ON CONFLICT (id) DO NOTHING;

-- Completed workflow for historical reference
INSERT INTO public.bo_approval_workflows (workflow_id, bo_id, status, workflow_data) VALUES
    ('WF-COMPLETE-001', NULL, 'completed',
     '{"submitted_at": "2024-12-01T09:00:00Z", "submitted_by": "test-rep_dubai_1", "client": "HSBC", "amount": 180000, "steps": [
        {"step": "coordinator", "status": "approved", "approved_by": "test-coordinator_1", "approved_at": "2024-12-02T10:00:00Z"},
        {"step": "hos", "status": "approved", "approved_by": "test-hos_backlite", "approved_at": "2024-12-03T11:00:00Z"},
        {"step": "finance", "status": "approved", "approved_by": "test-finance_1", "approved_at": "2024-12-04T09:00:00Z"}
     ], "completed_at": "2024-12-04T09:00:00Z"}'
    )
ON CONFLICT (workflow_id) DO UPDATE SET status = 'completed';

-- Reset sequences to avoid conflicts
SELECT setval('public.proposals_log_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM public.proposals_log), false);
SELECT setval('public.booking_orders_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM public.booking_orders), false);

-- ============================================================================
-- SUMMARY OF TEST DATA CREATED
-- ============================================================================
-- Proposals:
--   1. Draft proposal by rep_dubai_1 (Emirates NBD)
--   2. Submitted proposal by rep_dubai_1 (Etisalat) - pending approval
--   3. Approved proposal by rep_dubai_2 (Majid Al Futtaim)
--   4. Large proposal by rep_dubai_1 (Noon) - coordinator review needed
--   5. Multi-company proposal by rep_multi_company (Al Futtaim Motors)
--
-- Booking Orders:
--   1. BO-2025-001: Pending coordinator (rep_dubai_1)
--   2. BO-2025-002: Coordinator approved, pending HOS (rep_dubai_1)
--   3. BO-2025-003: HOS approved, pending finance (rep_dubai_2)
--   4. BO-2025-004: Rejected by coordinator (rep_dubai_1)
--
-- Approval Workflows:
--   WF-001: Pending coordinator
--   WF-002: Coordinator approved
--   WF-003: HOS approved
--   WF-004: Coordinator rejected
--   WF-COMPLETE-001: Fully completed (historical)
--
-- Locations (backlite_dubai):
--   8 locations across 3 networks with rate cards
-- ============================================================================
