"""
Tests for health check endpoints.

These tests verify:
- Basic health endpoint returns correct status
- Ready endpoint checks dependencies
- Metrics endpoint requires authentication
"""

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_health_endpoint_returns_healthy(self, client: TestClient):
        """Test that /health returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "environment" in data

    def test_health_endpoint_includes_timezone(self, client: TestClient):
        """Test that /health includes timezone info."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "UAE (GMT+4)"

    def test_ready_endpoint_returns_status(self, client: TestClient):
        """Test that /health/ready returns dependency status."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "slack" in data["checks"]
        assert "llm" in data["checks"]

    def test_metrics_requires_auth(self, client: TestClient):
        """Test that /metrics requires authentication."""
        response = client.get("/metrics")

        # Should return 401 without auth
        assert response.status_code == 401

    def test_metrics_with_auth(self, client: TestClient, mock_auth):
        """Test that /metrics works with authentication."""
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "memory" in data
        assert "cpu" in data
        assert "timestamp" in data
