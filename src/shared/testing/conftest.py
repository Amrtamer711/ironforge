"""
Pytest fixtures for MMG testing framework.

Usage:
    # In your test file
    import pytest

    def test_proposal_creation(auth_as_rep_dubai_1, test_client):
        response = test_client.get("/api/sales/proposals")
        assert response.status_code == 200

    def test_admin_only_feature(auth_as_test_admin, test_client):
        response = test_client.post("/api/admin/users")
        assert response.status_code == 200

    def test_permission_denied(auth_as_viewer_only, test_client):
        response = test_client.post("/api/sales/proposals", json={...})
        assert response.status_code == 403

Fixtures automatically:
- Load personas from personas.yaml
- Create trusted headers for API testing
- Provide mock user contexts for unit tests
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml


# =============================================================================
# LOAD PERSONAS FROM YAML
# =============================================================================

PERSONAS_FILE = Path(__file__).parent / "personas.yaml"


def _load_personas() -> dict:
    """Load personas from YAML file."""
    if not PERSONAS_FILE.exists():
        raise FileNotFoundError(f"personas.yaml not found at {PERSONAS_FILE}")

    with open(PERSONAS_FILE) as f:
        return yaml.safe_load(f)


def _get_profile_permissions(data: dict, profile_name: str | None) -> list[str]:
    """Get permissions for a profile."""
    if not profile_name:
        return []

    profiles = data.get("profiles", {})
    profile = profiles.get(profile_name, {})
    return profile.get("permissions", [])


def _build_persona_context(data: dict, persona: dict) -> dict:
    """Build full context for a persona."""
    profile_name = persona.get("profile")
    permissions = _get_profile_permissions(data, profile_name)

    # Build team info
    teams = []
    team_ids = []
    teams_config = {t["id"]: t for t in data.get("teams", [])}

    for team_entry in persona.get("teams", []):
        team_id = team_entry.get("team_id")
        if team_id in teams_config:
            team_info = teams_config[team_id]
            teams.append({
                "id": team_id,
                "name": team_info.get("name"),
                "company": team_info.get("company"),
                "role": team_entry.get("role", "member"),
            })
            team_ids.append(team_id)

    # Build subordinate IDs
    subordinate_ids = [f"test-{sub}" for sub in persona.get("subordinates", [])]

    # Build manager ID
    manager_id = None
    if persona.get("manager"):
        manager_id = f"test-{persona['manager']}"

    return {
        "id": f"test-{persona['id']}",
        "email": persona["email"],
        "name": persona.get("name", persona["id"]),
        "profile": profile_name,
        "permissions": permissions,
        "companies": persona.get("companies", []),
        "teams": teams,
        "team_ids": team_ids,
        "manager_id": manager_id,
        "subordinate_ids": subordinate_ids,
        "sharing_rules": [],
        "shared_records": {},
        "shared_from_user_ids": [],
    }


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PersonaContext:
    """Full context for a test persona."""
    id: str
    email: str
    name: str
    profile: str | None
    permissions: list[str]
    companies: list[str]
    teams: list[dict]
    team_ids: list[int]
    manager_id: str | None = None
    subordinate_ids: list[str] = field(default_factory=list)
    sharing_rules: list[dict] = field(default_factory=list)
    shared_records: dict[str, list[str]] = field(default_factory=dict)
    shared_from_user_ids: list[str] = field(default_factory=list)

    def to_trusted_headers(self, include_proxy_secret: str | None = None) -> dict[str, str]:
        """Convert to trusted headers for API testing."""
        headers = {
            "X-Trusted-User-Id": self.id,
            "X-Trusted-User-Email": self.email,
            "X-Trusted-User-Name": self.name or "",
            "X-Trusted-User-Profile": self.profile or "",
            "X-Trusted-User-Permissions": json.dumps(self.permissions),
            "X-Trusted-User-Companies": json.dumps(self.companies),
            "X-Trusted-User-Teams": json.dumps(self.teams),
            "X-Trusted-User-Team-Ids": json.dumps(self.team_ids),
            "X-Trusted-User-Subordinate-Ids": json.dumps(self.subordinate_ids),
            "X-Trusted-User-Sharing-Rules": json.dumps(self.sharing_rules),
            "X-Trusted-User-Shared-Records": json.dumps(self.shared_records),
            "X-Trusted-User-Shared-From-User-Ids": json.dumps(self.shared_from_user_ids),
        }

        if self.manager_id:
            headers["X-Trusted-User-Manager-Id"] = self.manager_id

        if include_proxy_secret:
            headers["X-Proxy-Secret"] = include_proxy_secret

        return headers

    def to_dict(self) -> dict[str, Any]:
        """Convert to TrustedUserContext-compatible dict."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "profile": self.profile,
            "permissions": self.permissions,
            "companies": self.companies,
            "teams": self.teams,
            "team_ids": self.team_ids,
            "manager_id": self.manager_id,
            "subordinate_ids": self.subordinate_ids,
            "sharing_rules": self.sharing_rules,
            "shared_records": self.shared_records,
            "shared_from_user_ids": self.shared_from_user_ids,
        }


# =============================================================================
# PERSONA REGISTRY
# =============================================================================

class PersonaRegistry:
    """Registry for all test personas."""

    def __init__(self):
        self._data: dict | None = None
        self._personas: dict[str, PersonaContext] | None = None

    def _ensure_loaded(self):
        """Ensure personas are loaded."""
        if self._data is None:
            self._data = _load_personas()
            self._personas = {}

            for persona in self._data.get("personas", []):
                persona_id = persona["id"]
                context = _build_persona_context(self._data, persona)
                self._personas[persona_id] = PersonaContext(**context)

    def get(self, persona_id: str) -> PersonaContext:
        """Get a specific persona."""
        self._ensure_loaded()
        if persona_id not in self._personas:
            raise ValueError(
                f"Unknown persona: {persona_id}. "
                f"Available: {list(self._personas.keys())}"
            )
        return self._personas[persona_id]

    def all(self) -> dict[str, PersonaContext]:
        """Get all personas."""
        self._ensure_loaded()
        return self._personas

    def by_profile(self, profile: str) -> list[PersonaContext]:
        """Get all personas with a specific profile."""
        self._ensure_loaded()
        return [p for p in self._personas.values() if p.profile == profile]

    def by_company(self, company: str) -> list[PersonaContext]:
        """Get all personas with access to a specific company."""
        self._ensure_loaded()
        return [p for p in self._personas.values() if company in p.companies]

    @property
    def raw_data(self) -> dict:
        """Get raw YAML data."""
        self._ensure_loaded()
        return self._data


# Global registry
_registry = PersonaRegistry()


# =============================================================================
# CORE FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def personas() -> PersonaRegistry:
    """Get the persona registry."""
    return _registry


@pytest.fixture(scope="session")
def default_password() -> str:
    """Get the default test user password."""
    return _registry.raw_data.get("default_password", "TestUser123!")


# =============================================================================
# PERSONA CONTEXT FIXTURES
# =============================================================================

@pytest.fixture
def persona_test_admin() -> PersonaContext:
    """System admin persona."""
    return _registry.get("test_admin")


@pytest.fixture
def persona_hos_backlite() -> PersonaContext:
    """Head of Sales - Backlite persona."""
    return _registry.get("hos_backlite")


@pytest.fixture
def persona_hos_viola() -> PersonaContext:
    """Head of Sales - Viola persona."""
    return _registry.get("hos_viola")


@pytest.fixture
def persona_rep_dubai_1() -> PersonaContext:
    """Sales rep Dubai 1 persona."""
    return _registry.get("rep_dubai_1")


@pytest.fixture
def persona_rep_dubai_2() -> PersonaContext:
    """Sales rep Dubai 2 persona."""
    return _registry.get("rep_dubai_2")


@pytest.fixture
def persona_rep_uk_1() -> PersonaContext:
    """Sales rep UK persona."""
    return _registry.get("rep_uk_1")


@pytest.fixture
def persona_rep_viola_1() -> PersonaContext:
    """Sales rep Viola persona."""
    return _registry.get("rep_viola_1")


@pytest.fixture
def persona_rep_multi_company() -> PersonaContext:
    """Multi-company sales rep persona."""
    return _registry.get("rep_multi_company")


@pytest.fixture
def persona_coordinator_1() -> PersonaContext:
    """Coordinator persona."""
    return _registry.get("coordinator_1")


@pytest.fixture
def persona_finance_1() -> PersonaContext:
    """Finance persona."""
    return _registry.get("finance_1")


@pytest.fixture
def persona_viewer_only() -> PersonaContext:
    """View-only persona."""
    return _registry.get("viewer_only")


@pytest.fixture
def persona_no_permissions() -> PersonaContext:
    """No permissions persona."""
    return _registry.get("no_permissions")


@pytest.fixture
def persona_no_company() -> PersonaContext:
    """No company access persona."""
    return _registry.get("no_company")


@pytest.fixture
def persona_wrong_company() -> PersonaContext:
    """Wrong company persona (Viola trying Dubai)."""
    return _registry.get("wrong_company")


# =============================================================================
# AUTH HEADER FIXTURES
# =============================================================================

@pytest.fixture
def auth_headers_test_admin(persona_test_admin: PersonaContext) -> dict[str, str]:
    """Trusted headers for system admin."""
    return persona_test_admin.to_trusted_headers()


@pytest.fixture
def auth_headers_hos_backlite(persona_hos_backlite: PersonaContext) -> dict[str, str]:
    """Trusted headers for HoS Backlite."""
    return persona_hos_backlite.to_trusted_headers()


@pytest.fixture
def auth_headers_rep_dubai_1(persona_rep_dubai_1: PersonaContext) -> dict[str, str]:
    """Trusted headers for Dubai rep 1."""
    return persona_rep_dubai_1.to_trusted_headers()


@pytest.fixture
def auth_headers_rep_dubai_2(persona_rep_dubai_2: PersonaContext) -> dict[str, str]:
    """Trusted headers for Dubai rep 2."""
    return persona_rep_dubai_2.to_trusted_headers()


@pytest.fixture
def auth_headers_coordinator_1(persona_coordinator_1: PersonaContext) -> dict[str, str]:
    """Trusted headers for coordinator."""
    return persona_coordinator_1.to_trusted_headers()


@pytest.fixture
def auth_headers_finance_1(persona_finance_1: PersonaContext) -> dict[str, str]:
    """Trusted headers for finance."""
    return persona_finance_1.to_trusted_headers()


@pytest.fixture
def auth_headers_viewer_only(persona_viewer_only: PersonaContext) -> dict[str, str]:
    """Trusted headers for viewer."""
    return persona_viewer_only.to_trusted_headers()


@pytest.fixture
def auth_headers_no_permissions(persona_no_permissions: PersonaContext) -> dict[str, str]:
    """Trusted headers for no-permissions user."""
    return persona_no_permissions.to_trusted_headers()


# =============================================================================
# DYNAMIC FIXTURE FACTORY
# =============================================================================

@pytest.fixture
def get_persona():
    """Factory fixture to get any persona by ID.

    Usage:
        def test_something(get_persona):
            admin = get_persona("test_admin")
            rep = get_persona("rep_dubai_1")
    """
    def _get(persona_id: str) -> PersonaContext:
        return _registry.get(persona_id)
    return _get


@pytest.fixture
def get_auth_headers():
    """Factory fixture to get auth headers for any persona.

    Usage:
        def test_something(get_auth_headers, test_client):
            headers = get_auth_headers("rep_dubai_1")
            response = test_client.get("/api/...", headers=headers)
    """
    def _get(persona_id: str, proxy_secret: str | None = None) -> dict[str, str]:
        persona = _registry.get(persona_id)
        return persona.to_trusted_headers(include_proxy_secret=proxy_secret)
    return _get


# =============================================================================
# SCENARIO FIXTURES
# =============================================================================

@pytest.fixture
def scenario_basic_sales_flow() -> list[PersonaContext]:
    """Personas for basic sales flow testing."""
    return [
        _registry.get("rep_dubai_1"),
        _registry.get("coordinator_1"),
        _registry.get("hos_backlite"),
        _registry.get("finance_1"),
    ]


@pytest.fixture
def scenario_multi_company() -> list[PersonaContext]:
    """Personas for multi-company isolation testing."""
    return [
        _registry.get("rep_dubai_1"),
        _registry.get("rep_viola_1"),
        _registry.get("rep_multi_company"),
    ]


@pytest.fixture
def scenario_manager_hierarchy() -> list[PersonaContext]:
    """Personas for manager hierarchy testing."""
    return [
        _registry.get("hos_backlite"),
        _registry.get("rep_dubai_1"),
        _registry.get("rep_dubai_2"),
        _registry.get("rep_uk_1"),
    ]


@pytest.fixture
def scenario_permission_enforcement() -> list[PersonaContext]:
    """Personas for permission enforcement testing."""
    return [
        _registry.get("viewer_only"),
        _registry.get("no_permissions"),
        _registry.get("no_company"),
        _registry.get("wrong_company"),
    ]


# =============================================================================
# MOCK USER CONTEXT FIXTURES (for unit tests)
# =============================================================================

@pytest.fixture
def mock_user_context():
    """Factory to create mock TrustedUserContext dicts.

    Usage:
        def test_something(mock_user_context):
            user = mock_user_context("rep_dubai_1")
            result = some_function(user)
    """
    def _create(persona_id: str) -> dict[str, Any]:
        persona = _registry.get(persona_id)
        return persona.to_dict()
    return _create


# =============================================================================
# PERMISSION TESTING HELPERS
# =============================================================================

@pytest.fixture
def assert_has_permission():
    """Helper to assert a persona has a specific permission.

    Usage:
        def test_permissions(assert_has_permission):
            assert_has_permission("rep_dubai_1", "sales:proposals:create")
    """
    def _assert(persona_id: str, permission: str):
        persona = _registry.get(persona_id)

        # Check for exact match or wildcard
        for p in persona.permissions:
            if p == permission or p == "*:*:*":
                return

            # Check wildcard patterns
            p_parts = p.split(":")
            perm_parts = permission.split(":")

            if len(p_parts) == 3 and len(perm_parts) == 3:
                match = True
                for i in range(3):
                    if p_parts[i] != "*" and p_parts[i] != perm_parts[i]:
                        match = False
                        break
                if match:
                    return

        raise AssertionError(
            f"Persona {persona_id} does not have permission {permission}. "
            f"Has: {persona.permissions}"
        )

    return _assert


@pytest.fixture
def assert_lacks_permission():
    """Helper to assert a persona lacks a specific permission."""
    def _assert(persona_id: str, permission: str):
        persona = _registry.get(persona_id)

        for p in persona.permissions:
            if p == permission or p == "*:*:*":
                raise AssertionError(
                    f"Persona {persona_id} unexpectedly has permission {permission}"
                )

            # Check wildcard patterns
            p_parts = p.split(":")
            perm_parts = permission.split(":")

            if len(p_parts) == 3 and len(perm_parts) == 3:
                match = True
                for i in range(3):
                    if p_parts[i] != "*" and p_parts[i] != perm_parts[i]:
                        match = False
                        break
                if match:
                    raise AssertionError(
                        f"Persona {persona_id} unexpectedly has permission {permission} "
                        f"via {p}"
                    )

    return _assert


# =============================================================================
# COMPANY ACCESS HELPERS
# =============================================================================

@pytest.fixture
def assert_can_access_company():
    """Helper to assert a persona can access a company."""
    def _assert(persona_id: str, company: str):
        persona = _registry.get(persona_id)
        if company not in persona.companies:
            raise AssertionError(
                f"Persona {persona_id} cannot access company {company}. "
                f"Has access to: {persona.companies}"
            )

    return _assert


@pytest.fixture
def assert_cannot_access_company():
    """Helper to assert a persona cannot access a company."""
    def _assert(persona_id: str, company: str):
        persona = _registry.get(persona_id)
        if company in persona.companies:
            raise AssertionError(
                f"Persona {persona_id} unexpectedly can access company {company}"
            )

    return _assert
