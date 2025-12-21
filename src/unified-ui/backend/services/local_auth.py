"""
Local authentication service for fully offline development.

When ENVIRONMENT=local and AUTH_PROVIDER=local, this service provides:
- Mock JWT validation (accepts test persona tokens)
- SQLite-based user lookup
- Local RBAC data from synced database

Usage:
    Set environment variables:
        ENVIRONMENT=local
        AUTH_PROVIDER=local
        LOCAL_DB_PATH=/path/to/local/ui.db  # Optional, defaults to data/local/ui.db

Test tokens:
    Use tokens in format: "local-{persona_id}" or email
    Example: Authorization: Bearer local-rep_dubai_1
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("unified-ui")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default local database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "local" / "ui.db"

# Test personas file
PERSONAS_FILE = Path(__file__).parent.parent.parent.parent / "shared" / "testing" / "personas.yaml"


def get_local_db_path() -> Path:
    """Get path to local SQLite database."""
    env_path = os.getenv("LOCAL_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def is_local_auth_enabled() -> bool:
    """Check if local auth is enabled."""
    env = os.getenv("ENVIRONMENT", "local")
    provider = os.getenv("AUTH_PROVIDER", "supabase")
    return env == "local" and provider == "local"


# =============================================================================
# LOCAL USER MODEL
# =============================================================================

@dataclass
class LocalAuthUser:
    """User authenticated via local auth."""
    id: str
    email: str
    name: str | None = None
    role: str = "authenticated"
    user_metadata: dict[str, Any] | None = None

    # Extended data from local DB
    profile_id: int | None = None
    profile_name: str | None = None
    is_active: bool = True


@dataclass
class LocalRBACData:
    """RBAC data from local SQLite."""
    profile: str
    permissions: list[str]
    permission_sets: list[dict]
    teams: list[dict]
    team_ids: list[int]
    manager_id: str | None
    subordinate_ids: list[str]
    sharing_rules: list[dict]
    shared_records: dict[str, list[dict]]
    shared_from_user_ids: list[str]
    companies: list[str]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "permissions": self.permissions,
            "permissionSets": self.permission_sets,
            "teams": self.teams,
            "teamIds": self.team_ids,
            "managerId": self.manager_id,
            "subordinateIds": self.subordinate_ids,
            "sharingRules": self.sharing_rules,
            "sharedRecords": self.shared_records,
            "sharedFromUserIds": self.shared_from_user_ids,
            "companies": self.companies,
        }


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_db_connection() -> sqlite3.Connection | None:
    """Get connection to local SQLite database."""
    db_path = get_local_db_path()
    if not db_path.exists():
        logger.warning(f"[LOCAL AUTH] Database not found: {db_path}")
        logger.info("[LOCAL AUTH] Run: python src/shared/local_dev/sync_from_supabase.py")
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json(value: str | None, default: Any = None) -> Any:
    """Safely parse JSON from database."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


# =============================================================================
# PERSONAS HELPERS
# =============================================================================

def load_personas() -> dict:
    """Load test personas from YAML file."""
    if not PERSONAS_FILE.exists():
        return {}

    try:
        import yaml
        with open(PERSONAS_FILE) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        logger.warning("[LOCAL AUTH] PyYAML not installed, personas not available")
        return {}
    except Exception as e:
        logger.error(f"[LOCAL AUTH] Error loading personas: {e}")
        return {}


def get_persona_by_token(token: str) -> dict | None:
    """
    Find a persona by token.

    Tokens can be:
    - "local-{persona_id}" (e.g., "local-rep_dubai_1")
    - The persona's email (e.g., "rep.dubai1@mmg.ae")
    - The persona's ID directly (e.g., "rep_dubai_1")
    """
    data = load_personas()
    personas = data.get("personas", [])

    # Check for "local-" prefix
    if token.startswith("local-"):
        persona_id = token[6:]  # Remove "local-" prefix
    else:
        persona_id = token

    for p in personas:
        if p["id"] == persona_id or p["email"] == token:
            return p

    return None


# =============================================================================
# AUTH FUNCTIONS
# =============================================================================

def validate_local_token(token: str) -> LocalAuthUser | None:
    """
    Validate a local auth token.

    Accepts:
    - "local-{persona_id}" tokens for test personas
    - Direct persona email lookup
    - Database user lookup
    """
    # Try persona-based auth first
    persona = get_persona_by_token(token)
    if persona:
        logger.debug(f"[LOCAL AUTH] Authenticated via persona: {persona['id']}")
        return LocalAuthUser(
            id=f"test-{persona['id']}",
            email=persona["email"],
            name=persona["name"],
            profile_name=persona.get("profile"),
            user_metadata={"name": persona["name"]},
        )

    # Try database lookup
    conn = get_db_connection()
    if not conn:
        return None

    try:
        # Assume token is user ID or email
        cursor = conn.execute(
            """
            SELECT u.id, u.email, u.name, u.is_active, u.profile_id,
                   p.name as profile_name
            FROM users u
            LEFT JOIN profiles p ON u.profile_id = p.id
            WHERE u.id = ? OR u.email = ?
            """,
            (token, token)
        )
        row = cursor.fetchone()

        if not row:
            return None

        if not row["is_active"]:
            logger.warning(f"[LOCAL AUTH] User {row['email']} is deactivated")
            return None

        return LocalAuthUser(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            profile_id=row["profile_id"],
            profile_name=row["profile_name"],
            is_active=row["is_active"],
        )

    except Exception as e:
        logger.error(f"[LOCAL AUTH] Database error: {e}")
        return None
    finally:
        conn.close()


def get_local_user_rbac(user_id: str) -> LocalRBACData | None:
    """
    Get RBAC data for a user from local SQLite.

    For test personas, uses the persona definition.
    For database users, queries local SQLite.
    """
    # Check if this is a test persona
    if user_id.startswith("test-"):
        persona_id = user_id[5:]  # Remove "test-" prefix
        data = load_personas()

        for p in data.get("personas", []):
            if p["id"] == persona_id:
                # Get permissions from profile
                profiles = data.get("profiles", {})
                profile = profiles.get(p.get("profile"), {})
                permissions = profile.get("permissions", [])

                # Transform teams to match expected format (id, name, role, etc.)
                # personas.yaml uses team_id, but system expects id
                teams_def = {t["id"]: t for t in data.get("teams", [])}
                transformed_teams = []
                team_ids = []
                for team_ref in p.get("teams", []):
                    team_id = team_ref.get("team_id", 0)
                    team_ids.append(team_id)
                    team_info = teams_def.get(team_id, {})
                    transformed_teams.append({
                        "id": team_id,
                        "name": team_info.get("name", f"Team {team_id}"),
                        "displayName": team_info.get("name"),
                        "role": team_ref.get("role", "member"),
                        "parentTeamId": team_info.get("parent_team_id"),
                    })

                return LocalRBACData(
                    profile=p.get("profile") or "",
                    permissions=permissions,
                    permission_sets=[],
                    teams=transformed_teams,
                    team_ids=team_ids,
                    manager_id=p.get("manager"),
                    subordinate_ids=p.get("subordinates", []),
                    sharing_rules=[],
                    shared_records={},
                    shared_from_user_ids=p.get("shared_from", []),
                    companies=p.get("companies", []),
                )

        return None

    # Query from local database
    conn = get_db_connection()
    if not conn:
        return None

    try:
        # Get user with profile
        cursor = conn.execute(
            """
            SELECT u.id, u.email, u.name, u.profile_id, u.manager_id,
                   p.name as profile_name
            FROM users u
            LEFT JOIN profiles p ON u.profile_id = p.id
            WHERE u.id = ?
            """,
            (user_id,)
        )
        user_row = cursor.fetchone()

        if not user_row:
            return None

        profile_name = user_row["profile_name"] or ""

        # Get permissions from profile
        permissions = []
        if user_row["profile_id"]:
            cursor = conn.execute(
                "SELECT permission FROM profile_permissions WHERE profile_id = ?",
                (user_row["profile_id"],)
            )
            permissions = [row["permission"] for row in cursor.fetchall()]

        # Get companies
        cursor = conn.execute(
            """
            SELECT c.code
            FROM user_companies uc
            JOIN companies c ON uc.company_id = c.id
            WHERE uc.user_id = ?
            """,
            (user_id,)
        )
        companies = [row["code"] for row in cursor.fetchall()]

        # Get teams
        cursor = conn.execute(
            """
            SELECT t.id, t.name, tm.role
            FROM team_members tm
            JOIN teams t ON tm.team_id = t.id
            WHERE tm.user_id = ?
            """,
            (user_id,)
        )
        teams = [{"id": row["id"], "name": row["name"], "role": row["role"]} for row in cursor.fetchall()]
        team_ids = [t["id"] for t in teams]

        # Get subordinates (users where this user is manager)
        cursor = conn.execute(
            "SELECT id FROM users WHERE manager_id = ?",
            (user_id,)
        )
        subordinate_ids = [row["id"] for row in cursor.fetchall()]

        return LocalRBACData(
            profile=profile_name,
            permissions=permissions,
            permission_sets=[],  # Would need separate query
            teams=teams,
            team_ids=team_ids,
            manager_id=user_row["manager_id"],
            subordinate_ids=subordinate_ids,
            sharing_rules=[],  # Would need separate query
            shared_records={},
            shared_from_user_ids=[],
            companies=companies,
        )

    except Exception as e:
        logger.error(f"[LOCAL AUTH] Error getting RBAC data: {e}")
        return None
    finally:
        conn.close()


# =============================================================================
# PUBLIC API
# =============================================================================

def local_get_user(token: str) -> LocalAuthUser | None:
    """
    Validate token and get user - main entry point.

    Replaces Supabase auth.get_user() in local mode.
    """
    if not is_local_auth_enabled():
        return None

    return validate_local_token(token)


def local_get_rbac(user_id: str) -> LocalRBACData | None:
    """
    Get RBAC data for user - main entry point.

    Replaces database queries to Supabase in local mode.
    """
    if not is_local_auth_enabled():
        return None

    return get_local_user_rbac(user_id)
