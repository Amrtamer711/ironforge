#!/bin/bash
# ============================================================================
# MMG API Testing Examples
# ============================================================================
# Quick reference for testing APIs with different user contexts.
# Copy-paste these commands to test endpoints.
#
# MODES:
# 1. Local Auth Mode: Use "local-{persona_id}" tokens (no network required)
# 2. Supabase Mode: Use real JWT tokens from login
# 3. Dev Panel: Click "Switch to user" in http://localhost:3005/dev-panel.html
# ============================================================================

# Default URLs
UI_URL="http://localhost:3005"
SALES_URL="http://localhost:8000"
ASSETS_URL="http://localhost:8001"

# ============================================================================
# LOCAL AUTH MODE (Offline Development)
# ============================================================================
# When ENVIRONMENT=local and AUTH_PROVIDER=local, use these tokens:

# Test as sales rep (Dubai)
export REP_TOKEN="local-rep_dubai_1"

# Test as sales manager (HOS Backlite)
export MANAGER_TOKEN="local-hos_backlite"

# Test as coordinator
export COORD_TOKEN="local-coordinator_1"

# Test as finance
export FINANCE_TOKEN="local-finance_1"

# Test as admin
export ADMIN_TOKEN="local-test_admin"

# Test as viewer (read-only)
export VIEWER_TOKEN="local-viewer_only"

# Test as user with no permissions
export NO_PERMS_TOKEN="local-no_permissions"

# ============================================================================
# HEALTH CHECKS
# ============================================================================

echo "=== Health Checks ==="
curl -s "$UI_URL/health" | jq
curl -s "$SALES_URL/health" | jq
curl -s "$ASSETS_URL/health" | jq

# ============================================================================
# AUTHENTICATION / CONTEXT
# ============================================================================

echo "=== Get Current User Context ==="
# Through gateway (proxied)
curl -s "$UI_URL/api/dev/context" \
  -H "Cookie: dev_impersonate={...}" | jq

# ============================================================================
# PROPOSALS (Sales Module via Gateway)
# ============================================================================

echo "=== Proposals ==="

# List proposals (as sales rep)
curl -s "$UI_URL/api/sales/proposals" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# Get single proposal
curl -s "$UI_URL/api/sales/proposals/1" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# Create proposal (POST)
curl -s -X POST "$UI_URL/api/sales/proposals" \
  -H "Authorization: Bearer $REP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Test Client",
    "package_type": "combined",
    "locations": ["SZR-001", "MARINA-001"],
    "duration_weeks": 4,
    "start_date": "2025-03-01"
  }' | jq

# ============================================================================
# BOOKING ORDERS (Sales Module via Gateway)
# ============================================================================

echo "=== Booking Orders ==="

# List booking orders
curl -s "$UI_URL/api/sales/booking-orders" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# List booking orders pending coordinator review (as coordinator)
curl -s "$UI_URL/api/sales/booking-orders?status=pending" \
  -H "Authorization: Bearer $COORD_TOKEN" | jq

# List booking orders pending HOS approval (as manager)
curl -s "$UI_URL/api/sales/booking-orders?status=coordinator_approved" \
  -H "Authorization: Bearer $MANAGER_TOKEN" | jq

# Approve as coordinator
curl -s -X POST "$UI_URL/api/sales/booking-orders/1/approve" \
  -H "Authorization: Bearer $COORD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Verified all details"}' | jq

# Reject as coordinator
curl -s -X POST "$UI_URL/api/sales/booking-orders/4/reject" \
  -H "Authorization: Bearer $COORD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Missing required fields"}' | jq

# ============================================================================
# LOCATIONS (Asset Management via Gateway)
# ============================================================================

echo "=== Locations (via gateway) ==="

# List locations
curl -s "$UI_URL/api/assets/locations?companies=backlite_dubai" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# Get specific location
curl -s "$UI_URL/api/assets/locations/backlite_dubai/1" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# Direct to asset-management service (internal testing)
curl -s "$ASSETS_URL/api/v1/locations?companies=backlite_dubai" \
  -H "X-Trusted-User-Id: test-rep_dubai_1" \
  -H "X-Trusted-User-Email: rep.dubai1@mmg.ae" \
  -H "X-Trusted-User-Profile: sales_rep" \
  -H 'X-Trusted-User-Companies: ["backlite_dubai"]' | jq

# ============================================================================
# NETWORKS (Asset Management)
# ============================================================================

echo "=== Networks ==="

curl -s "$UI_URL/api/assets/networks?companies=backlite_dubai" \
  -H "Authorization: Bearer $REP_TOKEN" | jq

# ============================================================================
# PERMISSION TESTING
# ============================================================================

echo "=== Permission Tests ==="

# Viewer trying to create (should fail - 403)
curl -s -X POST "$UI_URL/api/sales/proposals" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Should Fail"}' | jq

# No permissions user trying to access (should fail - 403)
curl -s "$UI_URL/api/sales/proposals" \
  -H "Authorization: Bearer $NO_PERMS_TOKEN" | jq

# Cross-company access (rep from Viola trying Dubai - should fail)
curl -s "$UI_URL/api/sales/proposals?company=backlite_dubai" \
  -H "Authorization: Bearer local-hos_viola" | jq

# ============================================================================
# DEV PANEL API
# ============================================================================

echo "=== Dev Panel ==="

# Check dev panel status
curl -s "$UI_URL/api/dev/status" | jq

# List all personas
curl -s "$UI_URL/api/dev/personas" | jq

# Get quick switch options
curl -s "$UI_URL/api/dev/quick-switch" | jq

# Impersonate a user (sets cookie)
curl -s -X POST "$UI_URL/api/dev/impersonate" \
  -H "Content-Type: application/json" \
  -d '{"persona_id": "rep_dubai_1"}' \
  -c cookies.txt | jq

# Check context after impersonation
curl -s "$UI_URL/api/dev/context" \
  -b cookies.txt | jq

# Stop impersonation
curl -s -X POST "$UI_URL/api/dev/stop-impersonation" \
  -b cookies.txt -c cookies.txt | jq

# ============================================================================
# HTTPIE EXAMPLES (Alternative to curl)
# ============================================================================

# If you prefer httpie (https://httpie.io):

# List proposals
# http GET $UI_URL/api/sales/proposals "Authorization: Bearer $REP_TOKEN"

# Create proposal
# http POST $UI_URL/api/sales/proposals \
#   "Authorization: Bearer $REP_TOKEN" \
#   client_name="Test Client" \
#   package_type=combined

# Check approval workflow
# http GET $UI_URL/api/sales/booking-orders/1/workflow \
#   "Authorization: Bearer $COORD_TOKEN"

# ============================================================================
# TESTING SCENARIOS
# ============================================================================

echo "=== Testing Scenarios ==="

# Scenario 1: Complete BO Approval Flow
echo "1. Sales rep creates BO -> Coordinator approves -> HOS approves -> Finance confirms"

# Scenario 2: Data Isolation
echo "2. rep_dubai_1 creates data, rep_viola_1 cannot see it"

# Scenario 3: Permission Enforcement
echo "3. viewer_only can GET but not POST/PUT/DELETE"

# Scenario 4: Cross-company access
echo "4. rep_multi_company can see data from both companies"

# ============================================================================
# CLEANUP
# ============================================================================

rm -f cookies.txt

echo ""
echo "Testing complete!"
echo ""
echo "For browser testing, open: $UI_URL/dev-panel.html"
echo "For full docs, see: src/shared/testing/README.md"
