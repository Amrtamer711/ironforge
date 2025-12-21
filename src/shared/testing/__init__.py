"""
MMG Testing Framework

Quick test user management and RBAC testing utilities.

Usage:
    from shared.testing import get_personas, get_persona

    # Get all test personas
    personas = get_personas()

    # Get a specific persona
    admin = get_persona("test_admin")

Pytest Fixtures:
    # Copy conftest.py to your test directory or add src/shared/testing to conftest

    def test_something(persona_rep_dubai_1, auth_headers_rep_dubai_1):
        # persona_rep_dubai_1 is a PersonaContext object
        # auth_headers_rep_dubai_1 is a dict of trusted headers

CLI Usage:
    python -m shared.testing.cli list
    python -m shared.testing.cli login rep_dubai_1
    python -m shared.testing.cli headers viewer_only
"""

from pathlib import Path
import yaml

PERSONAS_FILE = Path(__file__).parent / "personas.yaml"


def load_personas_data() -> dict:
    """Load raw personas data from YAML file."""
    if not PERSONAS_FILE.exists():
        return {"personas": [], "scenarios": {}, "profiles": {}, "companies": []}
    with open(PERSONAS_FILE) as f:
        return yaml.safe_load(f) or {}


def get_personas() -> list[dict]:
    """Get all test personas."""
    return load_personas_data().get("personas", [])


def get_persona(persona_id: str) -> dict | None:
    """Get a specific persona by ID."""
    for p in get_personas():
        if p["id"] == persona_id:
            return p
    return None


def get_scenarios() -> dict:
    """Get all test scenarios."""
    return load_personas_data().get("scenarios", {})


def get_profiles() -> dict:
    """Get all profile definitions."""
    return load_personas_data().get("profiles", {})


def get_companies() -> list[dict]:
    """Get all company definitions."""
    return load_personas_data().get("companies", [])


# Also export the pytest fixtures registry for programmatic use
try:
    from .conftest import PersonaContext, PersonaRegistry
except ImportError:
    # pytest not installed - fixtures not available
    PersonaContext = None
    PersonaRegistry = None


__all__ = [
    "load_personas_data",
    "get_personas",
    "get_persona",
    "get_scenarios",
    "get_profiles",
    "get_companies",
    "PersonaContext",
    "PersonaRegistry",
]
