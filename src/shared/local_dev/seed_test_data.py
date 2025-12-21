#!/usr/bin/env python3
"""
Seed local SQLite databases with test data for offline development.

This script populates local databases with:
- Test personas and their RBAC context
- Sample proposals, booking orders, approval workflows
- Location data with rate cards
- Company/team structure

NO NETWORK REQUIRED - works fully offline.

Usage:
    python seed_test_data.py              # Seed all test data
    python seed_test_data.py --clear      # Clear and reseed
    python seed_test_data.py --proposals  # Only seed proposals
    python seed_test_data.py --dry-run    # Preview changes
"""

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# =============================================================================
# CONFIGURATION
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "local"
UI_DB = DATA_DIR / "ui.db"
SALES_DB = DATA_DIR / "sales.db"

PERSONAS_FILE = REPO_ROOT / "src" / "shared" / "testing" / "personas.yaml"

# =============================================================================
# DATABASE HELPERS
# =============================================================================

def ensure_data_dir():
    """Ensure local data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get SQLite connection."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")  # Allow seeding without FK constraints
    return conn


def load_personas() -> dict:
    """Load personas from YAML file."""
    if not PERSONAS_FILE.exists():
        print(f"Error: Personas file not found: {PERSONAS_FILE}")
        return {}

    with open(PERSONAS_FILE) as f:
        return yaml.safe_load(f) or {}


# =============================================================================
# UI DATABASE SEEDING
# =============================================================================

def create_ui_schema(conn: sqlite3.Connection):
    """Create UI database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            description TEXT,
            is_system BOOLEAN DEFAULT false
        );

        CREATE TABLE IF NOT EXISTS profile_permissions (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER REFERENCES profiles(id),
            permission TEXT NOT NULL,
            UNIQUE(profile_id, permission)
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            profile_id INTEGER REFERENCES profiles(id),
            manager_id TEXT REFERENCES users(id),
            is_active BOOLEAN DEFAULT true,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            currency TEXT DEFAULT 'AED'
        );

        CREATE TABLE IF NOT EXISTS user_companies (
            id INTEGER PRIMARY KEY,
            user_id TEXT REFERENCES users(id),
            company_id INTEGER REFERENCES companies(id),
            is_primary BOOLEAN DEFAULT false,
            UNIQUE(user_id, company_id)
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            parent_team_id INTEGER REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY,
            team_id INTEGER REFERENCES teams(id),
            user_id TEXT REFERENCES users(id),
            role TEXT DEFAULT 'member',
            UNIQUE(team_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS permission_sets (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS permission_set_permissions (
            id INTEGER PRIMARY KEY,
            permission_set_id INTEGER REFERENCES permission_sets(id),
            permission TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_permission_sets (
            id INTEGER PRIMARY KEY,
            user_id TEXT REFERENCES users(id),
            permission_set_id INTEGER REFERENCES permission_sets(id),
            UNIQUE(user_id, permission_set_id)
        );
    """)
    conn.commit()


def seed_ui_data(conn: sqlite3.Connection, data: dict):
    """Seed UI database with personas data."""
    print("Seeding UI database (profiles, users, companies, teams)...")

    # Seed companies
    companies = data.get("companies", [])
    for company in companies:
        conn.execute("""
            INSERT OR REPLACE INTO companies (id, code, name, currency)
            VALUES (?, ?, ?, ?)
        """, (company["id"], company["code"], company["name"], company.get("currency", "AED")))
    print(f"  Companies: {len(companies)}")

    # Seed teams
    teams = data.get("teams", [])
    for team in teams:
        conn.execute("""
            INSERT OR REPLACE INTO teams (id, name, parent_team_id)
            VALUES (?, ?, ?)
        """, (team["id"], team["name"], team.get("parent_team_id")))
    print(f"  Teams: {len(teams)}")

    # Seed profiles
    profiles = data.get("profiles", {})
    profile_id_map = {}
    idx = 1
    for name, profile in profiles.items():
        profile_id_map[name] = idx
        conn.execute("""
            INSERT OR REPLACE INTO profiles (id, name, display_name, description, is_system)
            VALUES (?, ?, ?, ?, ?)
        """, (idx, name, profile.get("display_name", name), profile.get("description"), True))

        # Seed profile permissions
        for perm in profile.get("permissions", []):
            conn.execute("""
                INSERT OR IGNORE INTO profile_permissions (profile_id, permission)
                VALUES (?, ?)
            """, (idx, perm))
        idx += 1
    print(f"  Profiles: {len(profiles)}")

    # Seed personas (users)
    personas = data.get("personas", [])
    for persona in personas:
        user_id = f"test-{persona['id']}"
        profile_id = profile_id_map.get(persona.get("profile"))
        manager = persona.get("manager")
        manager_id = f"test-{manager}" if manager else None

        conn.execute("""
            INSERT OR REPLACE INTO users (id, email, name, profile_id, manager_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, persona["email"], persona["name"], profile_id, manager_id, True))

        # Seed user companies
        for company_code in persona.get("companies", []):
            # Find company ID
            cursor = conn.execute("SELECT id FROM companies WHERE code = ?", (company_code,))
            row = cursor.fetchone()
            if row:
                conn.execute("""
                    INSERT OR IGNORE INTO user_companies (user_id, company_id, is_primary)
                    VALUES (?, ?, ?)
                """, (user_id, row["id"], True))

        # Seed team memberships
        for team_ref in persona.get("teams", []):
            team_id = team_ref.get("team_id")
            role = team_ref.get("role", "member")
            conn.execute("""
                INSERT OR IGNORE INTO team_members (team_id, user_id, role)
                VALUES (?, ?, ?)
            """, (team_id, user_id, role))

    print(f"  Users (personas): {len(personas)}")
    conn.commit()


# =============================================================================
# SALES DATABASE SEEDING
# =============================================================================

def create_sales_schema(conn: sqlite3.Connection):
    """Create Sales database schema (minimal for testing)."""
    conn.executescript("""
        -- Networks
        CREATE TABLE IF NOT EXISTS backlite_dubai_networks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        );

        -- Asset types
        CREATE TABLE IF NOT EXISTS backlite_dubai_asset_types (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT
        );

        -- Locations
        CREATE TABLE IF NOT EXISTS backlite_dubai_locations (
            id INTEGER PRIMARY KEY,
            location_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            network_id INTEGER,
            type_id INTEGER,
            lat REAL,
            lng REAL,
            is_active BOOLEAN DEFAULT true
        );

        -- Rate cards
        CREATE TABLE IF NOT EXISTS backlite_dubai_rate_cards (
            id INTEGER PRIMARY KEY,
            location_id INTEGER,
            rate_type TEXT,
            weekly_rate REAL,
            upload_fee REAL,
            production_fee REAL,
            valid_from TEXT
        );

        -- Proposals
        CREATE TABLE IF NOT EXISTS proposals_log (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            submitted_by TEXT NOT NULL,
            client_name TEXT NOT NULL,
            date_generated TEXT DEFAULT CURRENT_TIMESTAMP,
            package_type TEXT,
            total_amount TEXT,
            currency TEXT DEFAULT 'AED',
            locations TEXT,
            proposal_data TEXT
        );

        CREATE TABLE IF NOT EXISTS proposal_locations (
            id INTEGER PRIMARY KEY,
            proposal_id INTEGER,
            location_key TEXT,
            location_company TEXT,
            location_display_name TEXT,
            start_date TEXT,
            duration_weeks INTEGER,
            net_rate REAL,
            upload_fee REAL,
            production_fee REAL
        );

        -- Booking orders
        CREATE TABLE IF NOT EXISTS booking_orders (
            id INTEGER PRIMARY KEY,
            bo_ref TEXT UNIQUE NOT NULL,
            user_id TEXT,
            company TEXT NOT NULL,
            original_file_path TEXT,
            original_file_type TEXT,
            bo_number TEXT,
            client TEXT,
            agency TEXT,
            brand_campaign TEXT,
            net_pre_vat REAL,
            vat_value REAL,
            gross_amount REAL,
            sales_person TEXT,
            locations_json TEXT,
            extraction_method TEXT,
            needs_review BOOLEAN DEFAULT false,
            parsed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            parsed_by TEXT
        );

        CREATE TABLE IF NOT EXISTS bo_locations (
            id INTEGER PRIMARY KEY,
            bo_id INTEGER,
            location_key TEXT,
            location_company TEXT,
            start_date TEXT,
            end_date TEXT,
            duration_weeks INTEGER,
            net_rate REAL
        );

        CREATE TABLE IF NOT EXISTS bo_approval_workflows (
            workflow_id TEXT PRIMARY KEY,
            bo_id INTEGER,
            workflow_data TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def seed_sales_data(conn: sqlite3.Connection, data: dict):
    """Seed sales database with test data."""
    print("Seeding Sales database (locations, proposals, BOs)...")

    # Seed networks
    networks = [
        (1, "Digital Network", "Premium digital advertising network"),
        (2, "Static Network", "Traditional static billboard network"),
        (3, "Airport Network", "DXB Airport exclusive placements"),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO backlite_dubai_networks (id, name, description) VALUES (?, ?, ?)
    """, networks)
    print(f"  Networks: {len(networks)}")

    # Seed asset types
    asset_types = [
        (1, "digital_screen", "Digital Screen"),
        (2, "billboard", "Billboard"),
        (3, "unipole", "Unipole"),
        (4, "bridge_banner", "Bridge Banner"),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO backlite_dubai_asset_types (id, name, display_name) VALUES (?, ?, ?)
    """, asset_types)
    print(f"  Asset types: {len(asset_types)}")

    # Seed locations
    locations = [
        (1, "SZR-001", "Sheikh Zayed Road - Interchange 1", 1, 1, 25.0657, 55.1713, True),
        (2, "SZR-002", "Sheikh Zayed Road - Mall of Emirates", 1, 1, 25.1185, 55.2004, True),
        (3, "MARINA-001", "Dubai Marina - JBR Walk", 1, 1, 25.0763, 55.1390, True),
        (4, "DOWNTOWN-001", "Downtown - Burj Khalifa View", 2, 2, 25.1972, 55.2744, True),
        (5, "DXB-T1-001", "DXB Terminal 1 - Arrivals", 3, 1, 25.2528, 55.3644, True),
        (6, "DXB-T3-001", "DXB Terminal 3 - Concourse A", 3, 1, 25.2544, 55.3656, True),
        (7, "BUSINESS-001", "Business Bay - Canal Walk", 2, 3, 25.1850, 55.2707, True),
        (8, "JLT-001", "JLT Cluster D - Main Boulevard", 2, 2, 25.0689, 55.1460, True),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO backlite_dubai_locations
        (id, location_key, name, network_id, type_id, lat, lng, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, locations)
    print(f"  Locations: {len(locations)}")

    # Seed rate cards
    rate_cards = [
        (1, 1, "standard", 15000.00, 500.00, 2500.00, "2024-01-01"),
        (2, 2, "standard", 18000.00, 500.00, 2500.00, "2024-01-01"),
        (3, 3, "standard", 12000.00, 400.00, 2000.00, "2024-01-01"),
        (4, 4, "standard", 22000.00, 600.00, 3000.00, "2024-01-01"),
        (5, 5, "premium", 35000.00, 800.00, 4000.00, "2024-01-01"),
        (6, 6, "premium", 38000.00, 800.00, 4000.00, "2024-01-01"),
        (7, 7, "standard", 14000.00, 450.00, 2200.00, "2024-01-01"),
        (8, 8, "standard", 11000.00, 400.00, 1800.00, "2024-01-01"),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO backlite_dubai_rate_cards
        (id, location_id, rate_type, weekly_rate, upload_fee, production_fee, valid_from)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rate_cards)
    print(f"  Rate cards: {len(rate_cards)}")

    # Seed proposals
    proposals = [
        (1, "test-rep_dubai_1", "rep.dubai1@mmg.ae", "Emirates NBD", "combined", "165000", "AED",
         "SZR-001, SZR-002, MARINA-001", json.dumps({"status": "draft", "duration_weeks": 4})),
        (2, "test-rep_dubai_1", "rep.dubai1@mmg.ae", "Etisalat", "separate", "312000", "AED",
         "DOWNTOWN-001, DXB-T1-001", json.dumps({"status": "submitted", "duration_weeks": 8})),
        (3, "test-rep_dubai_2", "rep.dubai2@mmg.ae", "Majid Al Futtaim", "combined", "88000", "AED",
         "JLT-001, BUSINESS-001", json.dumps({"status": "approved", "duration_weeks": 4})),
        (4, "test-rep_dubai_1", "rep.dubai1@mmg.ae", "Noon", "combined", "520000", "AED",
         "SZR-001, SZR-002, MARINA-001, DOWNTOWN-001, DXB-T1-001",
         json.dumps({"status": "submitted", "duration_weeks": 12, "requires_coordinator_review": True})),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO proposals_log
        (id, user_id, submitted_by, client_name, package_type, total_amount, currency, locations, proposal_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, proposals)
    print(f"  Proposals: {len(proposals)}")

    # Seed booking orders
    booking_orders = [
        (1, "BO-2025-001", "test-rep_dubai_1", "backlite_dubai", "/uploads/bos/emirates.pdf", "pdf",
         "ENBD-2025-001", "Emirates NBD", "Leo Burnett", "Q1 Campaign",
         165000.00, 8250.00, 173250.00, "rep.dubai1@mmg.ae",
         json.dumps([{"location": "SZR-001", "weeks": 4}]), "ai_extraction", False, "test-rep_dubai_1"),
        (2, "BO-2025-002", "test-rep_dubai_1", "backlite_dubai", "/uploads/bos/etisalat.pdf", "pdf",
         "ETI-2025-001", "Etisalat", "Publicis", "Digital Transformation",
         312000.00, 15600.00, 327600.00, "rep.dubai1@mmg.ae",
         json.dumps([{"location": "DOWNTOWN-001", "weeks": 8}]), "ai_extraction", False, "test-rep_dubai_1"),
        (3, "BO-2025-003", "test-rep_dubai_2", "backlite_dubai", "/uploads/bos/maf.pdf", "pdf",
         "MAF-2025-001", "Majid Al Futtaim", "OMD", "Retail Summer",
         88000.00, 4400.00, 92400.00, "rep.dubai2@mmg.ae",
         json.dumps([{"location": "JLT-001", "weeks": 4}]), "ai_extraction", False, "test-rep_dubai_2"),
        (4, "BO-2025-004", "test-rep_dubai_1", "backlite_dubai", "/uploads/bos/incomplete.pdf", "pdf",
         None, "Unknown", None, None,
         50000.00, 2500.00, 52500.00, "rep.dubai1@mmg.ae",
         json.dumps([{"location": "SZR-001"}]), "manual_entry", True, "test-rep_dubai_1"),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO booking_orders
        (id, bo_ref, user_id, company, original_file_path, original_file_type, bo_number, client, agency,
         brand_campaign, net_pre_vat, vat_value, gross_amount, sales_person, locations_json,
         extraction_method, needs_review, parsed_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, booking_orders)
    print(f"  Booking orders: {len(booking_orders)}")

    # Seed approval workflows
    workflows = [
        ("WF-001", 1, "pending", json.dumps({
            "submitted_by": "test-rep_dubai_1",
            "steps": [{"step": "coordinator", "status": "pending"}, {"step": "hos", "status": "pending"}]
        })),
        ("WF-002", 2, "coordinator_approved", json.dumps({
            "submitted_by": "test-rep_dubai_1",
            "steps": [
                {"step": "coordinator", "status": "approved", "approved_by": "test-coordinator_1"},
                {"step": "hos", "status": "pending"}
            ]
        })),
        ("WF-003", 3, "hos_approved", json.dumps({
            "submitted_by": "test-rep_dubai_2",
            "steps": [
                {"step": "coordinator", "status": "approved", "approved_by": "test-coordinator_1"},
                {"step": "hos", "status": "approved", "approved_by": "test-hos_backlite"},
                {"step": "finance", "status": "pending"}
            ]
        })),
        ("WF-004", 4, "coordinator_rejected", json.dumps({
            "submitted_by": "test-rep_dubai_1",
            "steps": [{"step": "coordinator", "status": "rejected", "reason": "Missing fields"}]
        })),
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO bo_approval_workflows
        (workflow_id, bo_id, status, workflow_data)
        VALUES (?, ?, ?, ?)
    """, workflows)
    print(f"  Approval workflows: {len(workflows)}")

    conn.commit()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed local SQLite databases with test data")
    parser.add_argument("--clear", action="store_true", help="Clear databases before seeding")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument("--ui-only", action="store_true", help="Only seed UI database")
    parser.add_argument("--sales-only", action="store_true", help="Only seed Sales database")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("MMG LOCAL TEST DATA SEEDING")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Data dir: {DATA_DIR}")
    print(f"Personas file: {PERSONAS_FILE}")

    if args.dry_run:
        print("\nDry run - no changes will be made")
        return

    ensure_data_dir()
    data = load_personas()

    if not data:
        print("Error: Could not load personas data")
        return

    # Seed UI database
    if not args.sales_only:
        print("\n" + "-" * 40)
        if args.clear and UI_DB.exists():
            UI_DB.unlink()
            print(f"Cleared: {UI_DB}")

        conn = get_connection(UI_DB)
        create_ui_schema(conn)
        seed_ui_data(conn, data)
        conn.close()
        print(f"Created: {UI_DB}")

    # Seed Sales database
    if not args.ui_only:
        print("\n" + "-" * 40)
        if args.clear and SALES_DB.exists():
            SALES_DB.unlink()
            print(f"Cleared: {SALES_DB}")

        conn = get_connection(SALES_DB)
        create_sales_schema(conn)
        seed_sales_data(conn, data)
        conn.close()
        print(f"Created: {SALES_DB}")

    print("\n" + "=" * 60)
    print("SEEDING COMPLETE")
    print("=" * 60)
    print("\nYou can now run the application in local mode:")
    print("  export ENVIRONMENT=local")
    print("  export AUTH_PROVIDER=local")
    print("  python run_all_services.py")
    print("\nTest with persona tokens:")
    print("  curl -H 'Authorization: Bearer local-rep_dubai_1' http://localhost:3005/api/...")


if __name__ == "__main__":
    main()
