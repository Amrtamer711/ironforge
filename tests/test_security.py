"""
Tests for security features.

These tests verify:
- Security headers are present
- CORS is configured correctly
- Path traversal is prevented
- Input sanitization works
"""

import pytest
from fastapi.testclient import TestClient


class TestSecurityHeaders:
    """Test suite for security headers."""

    def test_security_headers_present(self, client: TestClient):
        """Test that security headers are added to responses."""
        response = client.get("/health")

        assert response.status_code == 200

        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in response.headers.get("Referrer-Policy", "")

    def test_permissions_policy_present(self, client: TestClient):
        """Test that Permissions-Policy header is present."""
        response = client.get("/health")

        permissions_policy = response.headers.get("Permissions-Policy", "")
        assert "camera=()" in permissions_policy
        assert "microphone=()" in permissions_policy


class TestCORS:
    """Test suite for CORS configuration."""

    def test_cors_preflight(self, client: TestClient):
        """Test CORS preflight request handling."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3005",
                "Access-Control-Request-Method": "GET",
            }
        )

        # Should allow the configured origins
        assert response.status_code in [200, 204]

    def test_cors_headers_on_response(self, client: TestClient):
        """Test that CORS headers are present on responses."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3005"}
        )

        assert response.status_code == 200
        # CORS header should be present for allowed origin
        assert "access-control-allow-origin" in [h.lower() for h in response.headers.keys()]


class TestPathTraversal:
    """Test suite for path traversal prevention."""

    def test_path_traversal_in_location_key(self, client: TestClient, mock_auth):
        """Test that path traversal in location_key is blocked."""
        response = client.get("/api/mockup/photo/../../../etc/passwd/test.jpg")

        # Should return 400 or 404, not expose file
        assert response.status_code in [400, 404]

    def test_path_traversal_in_filename(self, client: TestClient, mock_auth):
        """Test that path traversal in filename is blocked."""
        response = client.get("/api/mockup/photo/valid-location/../../etc/passwd")

        # Should return 400 or 404, not expose file
        assert response.status_code in [400, 404]

    def test_null_byte_injection(self, client: TestClient, mock_auth):
        """Test that null byte injection is blocked."""
        response = client.get("/api/mockup/photo/location/file.jpg%00.txt")

        # Should be handled safely
        assert response.status_code in [400, 404]


class TestInputSanitization:
    """Test suite for input sanitization."""

    def test_xss_in_query_params(self, client: TestClient, mock_auth):
        """Test that XSS attempts in query params are handled."""
        response = client.get(
            "/api/mockup/photos/test",
            params={"time_of_day": "<script>alert('xss')</script>"}
        )

        # Should not execute script, return error or sanitized response
        assert response.status_code in [200, 400, 422]
        if response.status_code == 200:
            # Response should not contain raw script tag
            assert "<script>" not in response.text

    def test_sql_injection_in_params(self, client: TestClient, mock_auth, mock_db):
        """Test that SQL injection attempts are handled."""
        response = client.get(
            "/api/mockup/photos/test'; DROP TABLE users; --"
        )

        # Should handle safely (parameterized queries)
        assert response.status_code in [200, 400, 404]
