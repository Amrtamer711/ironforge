#!/usr/bin/env python3
"""
Sync data from Dev Supabase to local SQLite databases.

This script pulls data from the development Supabase instance and
populates local SQLite databases, allowing fully offline development.

Usage:
    python sync_from_supabase.py                  # Sync all tables
    python sync_from_supabase.py --tables users,profiles  # Specific tables
    python sync_from_supabase.py --schema backlite_dubai  # Specific company
    python sync_from_supabase.py --dry-run        # Preview only
    python sync_from_supabase.py --clear          # Clear local before sync

Environment Variables Required:
    UI_DEV_SUPABASE_URL
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY
    SALESBOT_DEV_SUPABASE_URL
    SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY
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

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("Error: supabase package required. Install with: pip install supabase")
    sys.exit(1)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Local database paths (at repo root: CRM/data/local/)
# Path: src/shared/local_dev/sync_from_supabase.py -> go up 4 levels to CRM/
LOCAL_DB_DIR = Path(__file__).parent.parent.parent.parent / "data" / "local"
SALES_DB = LOCAL_DB_DIR / "sales.db"
ASSETS_DB = LOCAL_DB_DIR / "assets.db"
UI_DB = LOCAL_DB_DIR / "ui.db"

# Tables to sync from each Supabase project
UI_SUPABASE_TABLES = [
    # Core RBAC tables
    "users",
    "profiles",
    "profile_permissions",
    "permission_sets",
    "permission_set_permissions",
    "user_permission_sets",
    "teams",
    "team_members",
    "companies",
    "user_companies",
    "sharing_rules",
    "record_shares",
    "modules",
    "user_modules",
]

SALES_SUPABASE_TABLES = [
    # Public schema tables
    "proposals_log",
    "proposal_locations",
    "proposal_files",
    "booking_orders",
    "bo_locations",
    "bo_approval_workflows",
    "documents",
    "mockup_files",
    "ai_costs",
    "chat_sessions",
    "chat_messages",
]

# Company-specific schemas to sync
COMPANY_SCHEMAS = [
    "backlite_dubai",
    "backlite_uk",
    "backlite_abudhabi",
    "viola",
]

COMPANY_TABLES = [
    "networks",
    "asset_types",
    "locations",
    "packages",
    "package_items",
    "rate_cards",
    "mockup_frames",
]


@dataclass
class SyncStats:
    """Track sync statistics."""
    tables_synced: int = 0
    rows_synced: int = 0
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


# =============================================================================
# SUPABASE CLIENTS
# =============================================================================

def get_ui_supabase() -> Client | None:
    """Get UI Supabase client."""
    url = os.getenv("UI_DEV_SUPABASE_URL")
    key = os.getenv("UI_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def get_sales_supabase() -> Client | None:
    """Get Sales Supabase client."""
    url = os.getenv("SALESBOT_DEV_SUPABASE_URL")
    key = os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


# =============================================================================
# SQLITE HELPERS
# =============================================================================

def ensure_db_dir():
    """Ensure local database directory exists."""
    LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)


def get_sqlite_connection(db_path: Path) -> sqlite3.Connection:
    """Get SQLite connection with optimizations."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_table_from_data(conn: sqlite3.Connection, table_name: str, rows: list[dict]):
    """Create table schema from first row of data."""
    if not rows:
        return

    first_row = rows[0]
    columns = []

    for col_name, value in first_row.items():
        if col_name == "id":
            col_type = "TEXT PRIMARY KEY" if isinstance(value, str) else "INTEGER PRIMARY KEY"
        elif isinstance(value, bool):
            col_type = "BOOLEAN"
        elif isinstance(value, int):
            col_type = "INTEGER"
        elif isinstance(value, float):
            col_type = "REAL"
        elif isinstance(value, (dict, list)):
            col_type = "JSON"
        else:
            col_type = "TEXT"

        columns.append(f'"{col_name}" {col_type}')

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(columns)})'
    conn.execute(create_sql)


def insert_rows(conn: sqlite3.Connection, table_name: str, rows: list[dict]) -> int:
    """Insert rows into table."""
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?" for _ in columns])
    col_names = ", ".join([f'"{c}"' for c in columns])

    insert_sql = f'INSERT OR REPLACE INTO "{table_name}" ({col_names}) VALUES ({placeholders})'

    count = 0
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col)
            # Convert complex types to JSON
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            values.append(val)

        try:
            conn.execute(insert_sql, values)
            count += 1
        except sqlite3.Error as e:
            print(f"  Warning: Error inserting row into {table_name}: {e}")

    return count


# =============================================================================
# SYNC FUNCTIONS
# =============================================================================

def fetch_table_data(client: Client, table_name: str, schema: str = None) -> list[dict]:
    """Fetch all data from a Supabase table."""
    try:
        if schema:
            # For company-specific schemas
            response = client.from_(f"{schema}.{table_name}").select("*").execute()
        else:
            response = client.table(table_name).select("*").execute()
        return response.data or []
    except Exception as e:
        print(f"  Error fetching {table_name}: {e}")
        return []


def sync_table(
    client: Client,
    conn: sqlite3.Connection,
    table_name: str,
    schema: str = None,
    dry_run: bool = False,
) -> int:
    """Sync a single table from Supabase to SQLite."""
    full_name = f"{schema}.{table_name}" if schema else table_name
    print(f"  Syncing {full_name}...", end=" ")

    rows = fetch_table_data(client, table_name, schema)

    if not rows:
        print("(empty)")
        return 0

    if dry_run:
        print(f"(would sync {len(rows)} rows)")
        return len(rows)

    # Create table and insert data
    sqlite_table = f"{schema}_{table_name}" if schema else table_name
    create_table_from_data(conn, sqlite_table, rows)
    count = insert_rows(conn, sqlite_table, rows)
    conn.commit()

    print(f"({count} rows)")
    return count


def sync_ui_database(dry_run: bool = False, clear: bool = False, tables: list[str] = None) -> SyncStats:
    """Sync UI Supabase (auth/RBAC) to local SQLite."""
    stats = SyncStats()

    print("\n" + "=" * 60)
    print("Syncing UI Database (Auth/RBAC)")
    print("=" * 60)

    client = get_ui_supabase()
    if not client:
        stats.errors.append("UI Supabase not configured")
        print("Error: UI_DEV_SUPABASE_URL and UI_DEV_SUPABASE_SERVICE_ROLE_KEY required")
        return stats

    if not dry_run:
        ensure_db_dir()
        if clear and UI_DB.exists():
            UI_DB.unlink()
            print("Cleared existing UI database")

        conn = get_sqlite_connection(UI_DB)
    else:
        conn = None

    tables_to_sync = tables if tables else UI_SUPABASE_TABLES

    for table in tables_to_sync:
        if table not in UI_SUPABASE_TABLES:
            print(f"  Skipping {table} (not in UI tables)")
            continue

        try:
            count = sync_table(client, conn, table, dry_run=dry_run)
            stats.rows_synced += count
            stats.tables_synced += 1
        except Exception as e:
            stats.errors.append(f"{table}: {e}")
            print(f"  Error: {e}")

    if conn:
        conn.close()

    return stats


def sync_sales_database(
    dry_run: bool = False,
    clear: bool = False,
    tables: list[str] = None,
    schemas: list[str] = None,
) -> SyncStats:
    """Sync Sales Supabase to local SQLite."""
    stats = SyncStats()

    print("\n" + "=" * 60)
    print("Syncing Sales Database")
    print("=" * 60)

    client = get_sales_supabase()
    if not client:
        stats.errors.append("Sales Supabase not configured")
        print("Error: SALESBOT_DEV_SUPABASE_URL and SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY required")
        return stats

    if not dry_run:
        ensure_db_dir()
        if clear and SALES_DB.exists():
            SALES_DB.unlink()
            print("Cleared existing Sales database")

        conn = get_sqlite_connection(SALES_DB)
    else:
        conn = None

    # Sync public schema tables
    print("\nPublic schema tables:")
    tables_to_sync = tables if tables else SALES_SUPABASE_TABLES

    for table in tables_to_sync:
        if table in SALES_SUPABASE_TABLES:
            try:
                count = sync_table(client, conn, table, dry_run=dry_run)
                stats.rows_synced += count
                stats.tables_synced += 1
            except Exception as e:
                stats.errors.append(f"{table}: {e}")

    # Sync company-specific schemas
    schemas_to_sync = schemas if schemas else COMPANY_SCHEMAS

    for schema in schemas_to_sync:
        print(f"\n{schema} schema:")
        for table in COMPANY_TABLES:
            try:
                count = sync_table(client, conn, table, schema=schema, dry_run=dry_run)
                stats.rows_synced += count
                stats.tables_synced += 1
            except Exception as e:
                stats.errors.append(f"{schema}.{table}: {e}")

    if conn:
        conn.close()

    return stats


def sync_storage(dry_run: bool = False, clear: bool = False) -> SyncStats:
    """Sync file storage from Supabase Storage to local filesystem."""
    stats = SyncStats()

    print("\n" + "=" * 60)
    print("Syncing File Storage")
    print("=" * 60)

    # Storage sync would require downloading files from Supabase Storage
    # For now, just create the directory structure

    storage_dir = LOCAL_DB_DIR.parent / "storage"
    buckets = ["proposals", "mockups", "uploads", "templates", "documents"]

    for bucket in buckets:
        bucket_path = storage_dir / bucket
        if not dry_run:
            bucket_path.mkdir(parents=True, exist_ok=True)
            print(f"  Created bucket: {bucket}/")
        else:
            print(f"  Would create bucket: {bucket}/")

    print("\nNote: File download from Supabase Storage not implemented.")
    print("Files will be stored locally as you generate new mockups/proposals.")

    return stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sync data from Dev Supabase to local SQLite databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python sync_from_supabase.py                    # Sync all
    python sync_from_supabase.py --dry-run          # Preview only
    python sync_from_supabase.py --clear            # Clear and re-sync
    python sync_from_supabase.py --tables users,profiles
    python sync_from_supabase.py --schema backlite_dubai
        """
    )

    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--clear", action="store_true", help="Clear local databases before sync")
    parser.add_argument("--tables", help="Comma-separated list of tables to sync")
    parser.add_argument("--schema", help="Specific company schema to sync")
    parser.add_argument("--ui-only", action="store_true", help="Only sync UI database")
    parser.add_argument("--sales-only", action="store_true", help="Only sync Sales database")
    parser.add_argument("--storage", action="store_true", help="Also sync file storage")

    args = parser.parse_args()

    tables = args.tables.split(",") if args.tables else None
    schemas = [args.schema] if args.schema else None

    print("\n" + "=" * 60)
    print("MMG DEV SUPABASE → LOCAL SYNC")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Clear: {args.clear}")
    print(f"Local DB dir: {LOCAL_DB_DIR}")

    total_stats = SyncStats()

    # Sync UI database
    if not args.sales_only:
        stats = sync_ui_database(
            dry_run=args.dry_run,
            clear=args.clear,
            tables=tables,
        )
        total_stats.tables_synced += stats.tables_synced
        total_stats.rows_synced += stats.rows_synced
        total_stats.errors.extend(stats.errors)

    # Sync Sales database
    if not args.ui_only:
        stats = sync_sales_database(
            dry_run=args.dry_run,
            clear=args.clear,
            tables=tables,
            schemas=schemas,
        )
        total_stats.tables_synced += stats.tables_synced
        total_stats.rows_synced += stats.rows_synced
        total_stats.errors.extend(stats.errors)

    # Sync storage
    if args.storage:
        stats = sync_storage(dry_run=args.dry_run, clear=args.clear)

    # Summary
    print("\n" + "=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)
    print(f"Tables synced: {total_stats.tables_synced}")
    print(f"Rows synced: {total_stats.rows_synced}")

    if total_stats.errors:
        print(f"Errors: {len(total_stats.errors)}")
        for err in total_stats.errors:
            print(f"  - {err}")

    if not args.dry_run:
        print(f"\nLocal databases created at:")
        print(f"  UI:    {UI_DB}")
        print(f"  Sales: {SALES_DB}")


if __name__ == "__main__":
    main()
