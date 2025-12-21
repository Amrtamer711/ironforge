#!/usr/bin/env python3
"""
MMG Testing CLI - Quick test user management and context switching.

Usage:
    python cli.py setup              # Full setup: create auth users + seed RBAC
    python cli.py seed               # Seed RBAC data only (users must exist in Auth)
    python cli.py reset              # Clear and re-seed all test data
    python cli.py list               # List all test personas
    python cli.py login <persona>    # Get login credentials for a persona
    python cli.py token <persona>    # Get a fresh JWT token for API testing
    python cli.py headers <persona>  # Get curl headers for direct API testing
    python cli.py impersonate <persona>  # Set up browser impersonation
"""

import argparse
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import yaml

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("Warning: supabase package not installed. Some features disabled.")

# =============================================================================
# CONFIGURATION
# =============================================================================

PERSONAS_FILE = Path(__file__).parent / "personas.yaml"
SQL_DIR = Path(__file__).parent / "sql"
DEFAULT_PASSWORD = "TestUser123!"

# Load personas
def load_personas() -> dict:
    """Load personas from YAML file."""
    with open(PERSONAS_FILE) as f:
        return yaml.safe_load(f)


@dataclass
class TestPersona:
    """A test persona for quick access."""
    id: str
    email: str
    name: str
    description: str
    profile: str | None
    companies: list[str]
    use_for: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "TestPersona":
        return cls(
            id=data["id"],
            email=data["email"],
            name=data["name"],
            description=data.get("description", ""),
            profile=data.get("profile"),
            companies=data.get("companies", []),
            use_for=data.get("use_for", []),
        )


def get_personas() -> list[TestPersona]:
    """Get all test personas."""
    data = load_personas()
    return [TestPersona.from_dict(p) for p in data.get("personas", [])]


def get_persona(persona_id: str) -> TestPersona | None:
    """Get a specific persona by ID."""
    for p in get_personas():
        if p.id == persona_id:
            return p
    return None


# =============================================================================
# SUPABASE HELPERS
# =============================================================================

def get_supabase_client() -> "Client | None":
    """Get Supabase client from environment."""
    if not HAS_SUPABASE:
        return None

    url = os.getenv("UI_DEV_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = os.getenv("UI_DEV_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("Error: Set UI_DEV_SUPABASE_URL and UI_DEV_SUPABASE_SERVICE_ROLE_KEY")
        return None

    return create_client(url, key)


def create_auth_user(client: "Client", email: str, password: str, name: str) -> dict | None:
    """Create a user in Supabase Auth."""
    try:
        result = client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"name": name},
        })
        return {"id": result.user.id, "email": result.user.email}
    except Exception as e:
        if "already been registered" in str(e):
            # User exists, get their ID
            users = client.auth.admin.list_users()
            for user in users:
                if user.email == email:
                    return {"id": user.id, "email": user.email}
        print(f"Error creating user {email}: {e}")
        return None


def get_user_token(client: "Client", email: str, password: str) -> str | None:
    """Get a JWT token for a user."""
    try:
        result = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        return result.session.access_token
    except Exception as e:
        print(f"Error getting token for {email}: {e}")
        return None


def run_sql_file(client: "Client", sql_file: Path) -> bool:
    """Run a SQL file against Supabase."""
    try:
        with open(sql_file) as f:
            sql = f.read()
        client.postgrest.rpc("exec_sql", {"sql": sql}).execute()
        return True
    except Exception as e:
        print(f"Error running {sql_file.name}: {e}")
        # Try via raw connection if RPC not available
        print("Tip: Run SQL files directly in Supabase SQL Editor")
        return False


# =============================================================================
# CLI COMMANDS
# =============================================================================

def cmd_list(args):
    """List all test personas."""
    personas = get_personas()

    print("\n" + "=" * 70)
    print("MMG TEST PERSONAS")
    print("=" * 70)

    # Group by role
    groups = {}
    for p in personas:
        role = p.profile or "no_profile"
        if role not in groups:
            groups[role] = []
        groups[role].append(p)

    for role, members in sorted(groups.items()):
        print(f"\n{role.upper().replace('_', ' ')}:")
        print("-" * 40)
        for p in members:
            companies = ", ".join(p.companies) if p.companies else "none"
            print(f"  {p.id:<25} {p.email}")
            print(f"    └─ Companies: {companies}")
            if p.use_for:
                print(f"    └─ Use for: {p.use_for[0]}")

    print("\n" + "=" * 70)
    print(f"Total: {len(personas)} personas")
    print("=" * 70 + "\n")


def cmd_login(args):
    """Show login credentials for a persona."""
    persona = get_persona(args.persona)
    if not persona:
        print(f"Error: Persona '{args.persona}' not found")
        print("Use 'python cli.py list' to see available personas")
        return

    print(f"\n{'=' * 50}")
    print(f"LOGIN: {persona.name}")
    print(f"{'=' * 50}")
    print(f"Email:    {persona.email}")
    print(f"Password: {DEFAULT_PASSWORD}")
    print(f"Profile:  {persona.profile or 'None'}")
    print(f"Companies: {', '.join(persona.companies) if persona.companies else 'None'}")
    print(f"{'=' * 50}\n")


def cmd_token(args):
    """Get a fresh JWT token for a persona."""
    persona = get_persona(args.persona)
    if not persona:
        print(f"Error: Persona '{args.persona}' not found")
        return

    client = get_supabase_client()
    if not client:
        return

    token = get_user_token(client, persona.email, DEFAULT_PASSWORD)
    if token:
        print(f"\n# Token for {persona.name}")
        print(f"export AUTH_TOKEN='{token}'")
        print(f"\n# Or use directly:")
        print(f"curl -H 'Authorization: Bearer {token}' http://localhost:8000/api/v1/...")


def cmd_headers(args):
    """Get curl headers for direct API testing."""
    persona = get_persona(args.persona)
    if not persona:
        print(f"Error: Persona '{args.persona}' not found")
        return

    client = get_supabase_client()
    if not client:
        # Fallback: show mock headers for local testing
        print(f"\n# Mock headers for local testing (bypasses auth)")
        print(f"# Use these when running with AUTH_PROVIDER=static\n")
        headers = {
            "X-Trusted-User-Id": f"test-{persona.id}",
            "X-Trusted-User-Email": persona.email,
            "X-Trusted-User-Name": persona.name,
            "X-Trusted-User-Profile": persona.profile or "",
            "X-Trusted-User-Companies": json.dumps(persona.companies),
        }
        for k, v in headers.items():
            print(f'-H "{k}: {v}" \\')
        return

    token = get_user_token(client, persona.email, DEFAULT_PASSWORD)
    if token:
        print(f"\n# Headers for {persona.name}")
        print(f'-H "Authorization: Bearer {token}" \\')
        print(f'-H "Content-Type: application/json"')


def cmd_setup(args):
    """Full setup: create auth users + seed RBAC data."""
    print("\n" + "=" * 50)
    print("MMG TEST SETUP")
    print("=" * 50)

    client = get_supabase_client()
    if not client:
        print("\nManual setup required:")
        print("1. Create users in Supabase Auth dashboard")
        print("2. Run SQL files in this order:")
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            print(f"   - {sql_file.name}")
        return

    # Create auth users
    print("\n1. Creating auth users...")
    personas = get_personas()
    created = 0
    for p in personas:
        result = create_auth_user(client, p.email, DEFAULT_PASSWORD, p.name)
        if result:
            print(f"   ✓ {p.email} ({result['id'][:8]}...)")
            created += 1
        else:
            print(f"   ✗ {p.email} (failed)")
    print(f"   Created/verified {created}/{len(personas)} users")

    # Run SQL seed files
    print("\n2. Running SQL seed files...")
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        print(f"   Running {sql_file.name}...")
        # Note: Direct SQL execution may need to be done via dashboard
        print(f"   → Run in Supabase SQL Editor")

    print("\n" + "=" * 50)
    print("Setup complete! Run SQL files in Supabase SQL Editor.")
    print("=" * 50 + "\n")


def cmd_seed(args):
    """Seed RBAC data only (assumes auth users exist)."""
    print("\nRun these SQL files in order in Supabase SQL Editor:\n")
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        print(f"  {sql_file.name}")
    print(f"\nSQL files location: {SQL_DIR}")


def cmd_reset(args):
    """Reset test data."""
    print("\nTo reset test data:")
    print("1. Delete test users from Supabase Auth (emails ending in @mmg.ae)")
    print("2. Run: DELETE FROM users WHERE email LIKE '%@mmg.ae'")
    print("3. Re-run: python cli.py setup")


def cmd_scenarios(args):
    """List available test scenarios."""
    data = load_personas()
    scenarios = data.get("scenarios", {})

    print("\n" + "=" * 50)
    print("TEST SCENARIOS")
    print("=" * 50)

    for name, scenario in scenarios.items():
        print(f"\n{name}:")
        print(f"  {scenario.get('description', '')}")
        print(f"  Personas: {', '.join(scenario.get('personas', []))}")
        if scenario.get("test_cases"):
            print("  Test cases:")
            for tc in scenario["test_cases"]:
                print(f"    - {tc}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="MMG Testing CLI - Quick test user management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py list                  # Show all personas
  python cli.py login rep_dubai_1     # Get login credentials
  python cli.py token hos_backlite    # Get JWT token
  python cli.py headers viewer_only   # Get curl headers
  python cli.py setup                 # Full setup
  python cli.py scenarios             # Show test scenarios
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # list
    subparsers.add_parser("list", help="List all test personas")

    # login
    p_login = subparsers.add_parser("login", help="Get login credentials")
    p_login.add_argument("persona", help="Persona ID (e.g., rep_dubai_1)")

    # token
    p_token = subparsers.add_parser("token", help="Get JWT token")
    p_token.add_argument("persona", help="Persona ID")

    # headers
    p_headers = subparsers.add_parser("headers", help="Get curl headers")
    p_headers.add_argument("persona", help="Persona ID")

    # setup
    subparsers.add_parser("setup", help="Full setup (create users + seed)")

    # seed
    subparsers.add_parser("seed", help="Show SQL seed files to run")

    # reset
    subparsers.add_parser("reset", help="Reset test data")

    # scenarios
    subparsers.add_parser("scenarios", help="List test scenarios")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "list": cmd_list,
        "login": cmd_login,
        "token": cmd_token,
        "headers": cmd_headers,
        "setup": cmd_setup,
        "seed": cmd_seed,
        "reset": cmd_reset,
        "scenarios": cmd_scenarios,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
