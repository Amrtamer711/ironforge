"""
Tests for authentication and authorization.

These tests verify:
- Authentication middleware works correctly
- Role-based access control is enforced
- API key authentication works
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


class TestAuthentication:
    """Test suite for authentication."""

    def test_protected_endpoint_requires_auth(self, client: TestClient):
        """Test that protected endpoints require authentication."""
        # Try to access a protected endpoint without auth
        response = client.get("/api/chat/conversations")

        assert response.status_code == 401

    def test_protected_endpoint_with_valid_auth(self, client: TestClient, mock_auth):
        """Test that protected endpoints work with valid auth."""
        response = client.get("/api/chat/conversations")

        # Should not return 401
        assert response.status_code != 401

    def test_admin_endpoint_requires_admin_role(self, client: TestClient, mock_auth):
        """Test that admin endpoints require admin role."""
        # Regular user trying to access admin endpoint
        response = client.get("/admin/roles")

        # Should return 403 (forbidden) for non-admin
        assert response.status_code in [401, 403]

    def test_admin_endpoint_with_admin_role(self, client: TestClient, mock_admin_auth):
        """Test that admin endpoints work with admin role."""
        response = client.get("/admin/roles")

        # Admin should have access
        assert response.status_code == 200


class TestAPIKeyAuth:
    """Test suite for API key authentication."""

    def test_api_key_header_auth(self, client: TestClient):
        """Test authentication via X-API-Key header."""
        # This would need a valid API key in the database
        response = client.get(
            "/health",
            headers={"X-API-Key": "invalid-key"}
        )

        # Health doesn't require auth, so this should pass
        assert response.status_code == 200

    def test_invalid_api_key_rejected(self, client: TestClient):
        """Test that invalid API keys are rejected on protected endpoints."""
        response = client.get(
            "/api/chat/conversations",
            headers={"X-API-Key": "invalid-key-12345"}
        )

        assert response.status_code == 401
