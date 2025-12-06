"""
Pytest configuration and fixtures for testing.

This module provides:
- Test client for FastAPI
- Mock authentication fixtures
- Database fixtures for isolated testing
- Common test utilities
"""

import os
import pytest
from typing import Generator, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["DB_BACKEND"] = "sqlite"
os.environ["AUTH_PROVIDER"] = "static"
os.environ["RBAC_PROVIDER"] = "static"

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from api.server import app
from integrations.auth import AuthUser


# =============================================================================
# TEST CLIENT FIXTURES
# =============================================================================


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a synchronous test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client() -> AsyncClient:
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# AUTHENTICATION FIXTURES
# =============================================================================


@pytest.fixture
def mock_user() -> AuthUser:
    """Create a mock authenticated user."""
    return AuthUser(
        id="test-user-123",
        email="test@example.com",
        name="Test User",
        provider="static",
        metadata={"roles": ["user"]},
    )


@pytest.fixture
def mock_admin_user() -> AuthUser:
    """Create a mock admin user."""
    return AuthUser(
        id="admin-user-456",
        email="admin@example.com",
        name="Admin User",
        provider="static",
        metadata={"roles": ["admin"]},
    )


@pytest.fixture
def auth_headers(mock_user: AuthUser) -> Dict[str, str]:
    """Create auth headers for a regular user."""
    # For static auth, we can use a simple token format
    return {"Authorization": f"Bearer test-token-{mock_user.id}"}


@pytest.fixture
def admin_auth_headers(mock_admin_user: AuthUser) -> Dict[str, str]:
    """Create auth headers for an admin user."""
    return {"Authorization": f"Bearer test-token-{mock_admin_user.id}"}


@pytest.fixture
def mock_auth(mock_user: AuthUser):
    """Mock the authentication dependency to return a test user."""
    from api import auth

    async def override_require_auth():
        return mock_user

    app.dependency_overrides[auth.require_auth] = override_require_auth
    yield mock_user
    app.dependency_overrides.clear()


@pytest.fixture
def mock_admin_auth(mock_admin_user: AuthUser):
    """Mock the authentication dependency to return an admin user."""
    from api import auth

    async def override_require_auth():
        return mock_admin_user

    # Also mock the role check
    original_require_any_role = auth.require_any_role

    def mock_require_any_role(*roles):
        async def dependency():
            return mock_admin_user
        return dependency

    app.dependency_overrides[auth.require_auth] = lambda: mock_admin_user
    auth.require_any_role = mock_require_any_role

    yield mock_admin_user

    app.dependency_overrides.clear()
    auth.require_any_role = original_require_any_role


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database for isolated testing."""
    from unittest.mock import MagicMock
    from db import database

    original_db = database.db
    mock = MagicMock()

    # Set up common return values
    mock.get_proposals_summary.return_value = {"total": 0, "by_status": {}}
    mock.list_mockup_photos.return_value = []
    mock.list_mockup_variations.return_value = {}

    database.db = mock
    yield mock
    database.db = original_db


# =============================================================================
# UTILITY FIXTURES
# =============================================================================


@pytest.fixture
def sample_proposal_data() -> Dict[str, Any]:
    """Sample proposal data for testing."""
    return {
        "client_name": "Test Client",
        "location": "test-location",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "currency": "AED",
        "items": [
            {
                "description": "Billboard Rental",
                "quantity": 1,
                "unit_price": 10000,
            }
        ],
    }


@pytest.fixture
def sample_mockup_data() -> Dict[str, Any]:
    """Sample mockup data for testing."""
    return {
        "location_key": "test-location",
        "time_of_day": "day",
        "finish": "gold",
    }


# =============================================================================
# CLEANUP FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Clean up after each test."""
    yield
    # Clear any dependency overrides
    app.dependency_overrides.clear()
