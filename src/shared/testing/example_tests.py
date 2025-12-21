"""
Example tests demonstrating the MMG pytest fixtures.

Run these tests with:
    pytest src/shared/testing/example_tests.py -v

To use these fixtures in your own tests:
1. Copy conftest.py to your test directory, OR
2. Add this to your conftest.py:
    pytest_plugins = ["shared.testing.conftest"]
"""

import pytest


# =============================================================================
# BASIC PERSONA USAGE
# =============================================================================

class TestPersonaFixtures:
    """Test persona fixtures are working correctly."""

    def test_persona_has_correct_profile(self, persona_rep_dubai_1):
        """Verify rep persona has sales_rep profile."""
        assert persona_rep_dubai_1.profile == "sales_rep"

    def test_admin_has_all_permissions(self, persona_test_admin):
        """Verify admin has wildcard permissions."""
        assert "*:*:*" in persona_test_admin.permissions

    def test_viewer_has_limited_permissions(self, persona_viewer_only):
        """Verify viewer has read-only permissions."""
        assert "sales:proposals:read" in persona_viewer_only.permissions
        assert "sales:proposals:create" not in persona_viewer_only.permissions

    def test_persona_has_companies(self, persona_rep_dubai_1):
        """Verify rep has company access."""
        assert "backlite_dubai" in persona_rep_dubai_1.companies

    def test_persona_has_teams(self, persona_rep_dubai_1):
        """Verify rep has team membership."""
        assert len(persona_rep_dubai_1.teams) > 0
        assert persona_rep_dubai_1.teams[0]["role"] == "member"


# =============================================================================
# AUTH HEADERS USAGE
# =============================================================================

class TestAuthHeaderFixtures:
    """Test auth header fixtures produce valid headers."""

    def test_headers_have_required_fields(self, auth_headers_rep_dubai_1):
        """Verify headers contain all required fields."""
        required = [
            "X-Trusted-User-Id",
            "X-Trusted-User-Email",
            "X-Trusted-User-Profile",
            "X-Trusted-User-Permissions",
            "X-Trusted-User-Companies",
        ]
        for header in required:
            assert header in auth_headers_rep_dubai_1

    def test_headers_have_correct_values(self, auth_headers_rep_dubai_1):
        """Verify header values are correct."""
        assert "test-rep_dubai_1" in auth_headers_rep_dubai_1["X-Trusted-User-Id"]
        assert "rep.dubai1@mmg.ae" in auth_headers_rep_dubai_1["X-Trusted-User-Email"]


# =============================================================================
# FACTORY FIXTURES
# =============================================================================

class TestFactoryFixtures:
    """Test factory fixtures for dynamic persona access."""

    def test_get_persona_by_id(self, get_persona):
        """Test getting persona by ID."""
        admin = get_persona("test_admin")
        rep = get_persona("rep_dubai_1")

        assert admin.profile == "system_admin"
        assert rep.profile == "sales_rep"

    def test_get_auth_headers_by_id(self, get_auth_headers):
        """Test getting headers by persona ID."""
        admin_headers = get_auth_headers("test_admin")
        rep_headers = get_auth_headers("rep_dubai_1")

        assert "test-test_admin" in admin_headers["X-Trusted-User-Id"]
        assert "test-rep_dubai_1" in rep_headers["X-Trusted-User-Id"]

    def test_invalid_persona_raises_error(self, get_persona):
        """Test that invalid persona ID raises an error."""
        with pytest.raises(ValueError, match="Unknown persona"):
            get_persona("nonexistent_persona")


# =============================================================================
# PERMISSION HELPERS
# =============================================================================

class TestPermissionHelpers:
    """Test permission assertion helpers."""

    def test_assert_has_permission(self, assert_has_permission):
        """Test permission assertion passes for valid permission."""
        assert_has_permission("rep_dubai_1", "sales:proposals:create")

    def test_assert_has_permission_wildcard(self, assert_has_permission):
        """Test permission assertion works with wildcards."""
        # rep has "sales:proposals:*" which should match "sales:proposals:update"
        assert_has_permission("rep_dubai_1", "sales:proposals:update")

    def test_assert_lacks_permission(self, assert_lacks_permission):
        """Test lack of permission assertion."""
        # Viewer doesn't have create permission
        assert_lacks_permission("viewer_only", "sales:proposals:create")

    def test_assert_lacks_permission_fails(self, assert_has_permission):
        """Test that assertion fails for missing permission."""
        with pytest.raises(AssertionError, match="does not have permission"):
            assert_has_permission("viewer_only", "sales:proposals:create")


# =============================================================================
# COMPANY ACCESS HELPERS
# =============================================================================

class TestCompanyAccessHelpers:
    """Test company access assertion helpers."""

    def test_assert_can_access_company(self, assert_can_access_company):
        """Test company access assertion passes."""
        assert_can_access_company("rep_dubai_1", "backlite_dubai")

    def test_assert_cannot_access_company(self, assert_cannot_access_company):
        """Test lack of company access assertion."""
        assert_cannot_access_company("rep_dubai_1", "viola")

    def test_multi_company_access(self, assert_can_access_company):
        """Test multi-company persona has access to both."""
        assert_can_access_company("rep_multi_company", "backlite_dubai")
        assert_can_access_company("rep_multi_company", "viola")


# =============================================================================
# SCENARIO FIXTURES
# =============================================================================

class TestScenarioFixtures:
    """Test scenario fixtures group personas correctly."""

    def test_basic_sales_flow_scenario(self, scenario_basic_sales_flow):
        """Verify basic sales flow includes correct personas."""
        persona_ids = [p.id for p in scenario_basic_sales_flow]
        assert "test-rep_dubai_1" in persona_ids
        assert "test-coordinator_1" in persona_ids
        assert "test-hos_backlite" in persona_ids
        assert "test-finance_1" in persona_ids

    def test_permission_enforcement_scenario(self, scenario_permission_enforcement):
        """Verify permission enforcement includes restricted personas."""
        persona_ids = [p.id for p in scenario_permission_enforcement]
        assert "test-viewer_only" in persona_ids
        assert "test-no_permissions" in persona_ids
        assert "test-no_company" in persona_ids

    def test_multi_company_scenario(self, scenario_multi_company):
        """Verify multi-company scenario includes cross-company personas."""
        for persona in scenario_multi_company:
            # Each persona should have at least one company
            # except multi_company which has multiple
            pass

        ids = [p.id for p in scenario_multi_company]
        assert "test-rep_multi_company" in ids


# =============================================================================
# MOCK USER CONTEXT (for unit tests)
# =============================================================================

class TestMockUserContext:
    """Test mock user context fixture for unit tests."""

    def test_mock_user_context_dict(self, mock_user_context):
        """Test mock user context returns valid dict."""
        user = mock_user_context("rep_dubai_1")

        assert isinstance(user, dict)
        assert user["id"] == "test-rep_dubai_1"
        assert user["email"] == "rep.dubai1@mmg.ae"
        assert user["profile"] == "sales_rep"

    def test_mock_user_has_permissions(self, mock_user_context):
        """Test mock user has permissions in dict."""
        user = mock_user_context("rep_dubai_1")

        assert isinstance(user["permissions"], list)
        assert len(user["permissions"]) > 0


# =============================================================================
# REGISTRY ACCESS
# =============================================================================

class TestPersonaRegistry:
    """Test persona registry fixture."""

    def test_registry_all_personas(self, personas):
        """Test registry returns all personas."""
        all_personas = personas.all()

        assert len(all_personas) > 10  # We have ~15 personas
        assert "test_admin" in all_personas
        assert "rep_dubai_1" in all_personas

    def test_registry_by_profile(self, personas):
        """Test filtering by profile."""
        reps = personas.by_profile("sales_rep")

        assert len(reps) > 3  # We have multiple sales reps
        for rep in reps:
            assert rep.profile == "sales_rep"

    def test_registry_by_company(self, personas):
        """Test filtering by company."""
        dubai_users = personas.by_company("backlite_dubai")

        assert len(dubai_users) > 2
        for user in dubai_users:
            assert "backlite_dubai" in user.companies


# =============================================================================
# INTEGRATION EXAMPLE (with FastAPI TestClient)
# =============================================================================

# Uncomment this when you have a FastAPI app to test
"""
from fastapi.testclient import TestClient
from your_app import app

class TestAPIWithPersonas:
    '''Example integration tests using personas.'''

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_rep_can_list_proposals(self, client, auth_headers_rep_dubai_1):
        '''Test rep can list their proposals.'''
        response = client.get(
            "/api/sales/proposals",
            headers=auth_headers_rep_dubai_1
        )
        assert response.status_code == 200

    def test_viewer_cannot_create_proposal(self, client, auth_headers_viewer_only):
        '''Test viewer cannot create proposals.'''
        response = client.post(
            "/api/sales/proposals",
            headers=auth_headers_viewer_only,
            json={"client_name": "Test Client"}
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "PERMISSION_DENIED"

    def test_wrong_company_denied(self, client, get_auth_headers):
        '''Test wrong company user is denied access to Dubai data.'''
        headers = get_auth_headers("wrong_company")  # Has Viola access only
        response = client.get(
            "/api/sales/proposals?company=backlite_dubai",
            headers=headers
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "COMPANY_ACCESS_DENIED"

    def test_approval_workflow(self, client, scenario_basic_sales_flow):
        '''Test complete approval workflow with multiple personas.'''
        rep, coordinator, hos, finance = scenario_basic_sales_flow

        # Rep creates proposal
        response = client.post(
            "/api/sales/proposals",
            headers=rep.to_trusted_headers(),
            json={"client_name": "Test Client"}
        )
        assert response.status_code == 201
        proposal_id = response.json()["id"]

        # Rep submits as BO
        response = client.post(
            f"/api/sales/proposals/{proposal_id}/submit-bo",
            headers=rep.to_trusted_headers()
        )
        assert response.status_code == 200
        bo_id = response.json()["bo_id"]

        # Coordinator approves
        response = client.post(
            f"/api/sales/booking-orders/{bo_id}/approve",
            headers=coordinator.to_trusted_headers()
        )
        assert response.status_code == 200

        # HoS approves
        response = client.post(
            f"/api/sales/booking-orders/{bo_id}/approve",
            headers=hos.to_trusted_headers()
        )
        assert response.status_code == 200

        # Finance confirms
        response = client.post(
            f"/api/sales/booking-orders/{bo_id}/confirm",
            headers=finance.to_trusted_headers()
        )
        assert response.status_code == 200
"""
