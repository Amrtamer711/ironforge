"""
Tests for mockup generation endpoints.

These tests verify:
- Mockup endpoints require authentication
- Admin-only endpoints require admin role
- Input validation works correctly
"""

from fastapi.testclient import TestClient


class TestMockupEndpoints:
    """Test suite for mockup endpoints."""

    def test_locations_requires_auth(self, client: TestClient):
        """Test that /api/mockup/locations requires authentication."""
        response = client.get("/api/mockup/locations")

        assert response.status_code == 401

    def test_locations_with_auth(self, client: TestClient, mock_auth, mock_db):
        """Test that /api/mockup/locations works with authentication."""
        response = client.get("/api/mockup/locations")

        assert response.status_code == 200
        data = response.json()
        assert "locations" in data

    def test_mockup_setup_requires_admin(self, client: TestClient, mock_auth):
        """Test that /mockup setup page requires admin role."""
        response = client.get("/mockup")

        # Regular user should be forbidden
        assert response.status_code in [401, 403]

    def test_save_frame_requires_admin(self, client: TestClient, mock_auth):
        """Test that save-frame requires admin role."""
        response = client.post(
            "/api/mockup/save-frame",
            data={
                "location_key": "test",
                "frames_data": "[]",
            }
        )

        # Regular user should be forbidden
        assert response.status_code in [401, 403]

    def test_delete_photo_requires_admin(self, client: TestClient, mock_auth):
        """Test that delete photo requires admin role."""
        response = client.delete(
            "/api/mockup/photo/test-location",
            params={"photo_filename": "test.jpg"}
        )

        # Regular user should be forbidden
        assert response.status_code in [401, 403]

    def test_generate_mockup_requires_auth(self, client: TestClient):
        """Test that generate mockup requires authentication."""
        response = client.post(
            "/api/mockup/generate",
            data={"location_key": "test"}
        )

        assert response.status_code == 401


class TestMockupValidation:
    """Test input validation for mockup endpoints."""

    def test_invalid_location_rejected(self, client: TestClient, mock_admin_auth):
        """Test that invalid location keys are rejected."""
        response = client.post(
            "/api/mockup/save-frame",
            data={
                "location_key": "../../../etc/passwd",  # Path traversal attempt
                "frames_data": "[]",
            },
            files={"photo": ("test.jpg", b"fake image", "image/jpeg")}
        )

        assert response.status_code == 400

    def test_invalid_time_of_day_rejected(self, client: TestClient, mock_admin_auth):
        """Test that invalid time_of_day values are rejected."""
        response = client.post(
            "/api/mockup/save-frame",
            data={
                "location_key": "test",
                "time_of_day": "invalid",
                "frames_data": "[]",
            },
            files={"photo": ("test.jpg", b"fake image", "image/jpeg")}
        )

        assert response.status_code == 400
