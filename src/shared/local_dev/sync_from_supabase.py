#!/usr/bin/env python3
"""
Sync data from Dev Supabase to local SQLite databases and storage.

This script pulls data from the development Supabase instances and
populates local SQLite databases and file storage, allowing fully offline development.

Usage:
    python sync_from_supabase.py                  # Sync all tables
    python sync_from_supabase.py --tables users,profiles  # Specific tables
    python sync_from_supabase.py --schema backlite_dubai  # Specific company
    python sync_from_supabase.py --dry-run        # Preview only
    python sync_from_supabase.py --clear          # Clear local before sync
    python sync_from_supabase.py --storage        # Also sync file storage
    python sync_from_supabase.py --storage-only   # Only sync file storage
    python sync_from_supabase.py --buckets proposals,mockups  # Specific buckets

Environment Variables Required:
    UI_DEV_SUPABASE_URL
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY
    SALESBOT_DEV_SUPABASE_URL
    SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY

Optional (for asset/security storage):
    ASSETMGMT_DEV_SUPABASE_URL
    ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY
    SECURITY_DEV_SUPABASE_URL
    SECURITY_DEV_SUPABASE_SERVICE_ROLE_KEY
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

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

# Local paths (at repo root: CRM/data/)
# Path: src/shared/local_dev/sync_from_supabase.py -> go up 4 levels to CRM/
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
LOCAL_DB_DIR = DATA_DIR / "local"
STORAGE_DIR = DATA_DIR / "storage"
SALES_DB = LOCAL_DB_DIR / "sales.db"
ASSETS_DB = LOCAL_DB_DIR / "assets.db"
UI_DB = LOCAL_DB_DIR / "ui.db"
SECURITY_DB = LOCAL_DB_DIR / "security.db"

# Storage bucket configuration per Supabase project
# Format: {project: {bucket_name: local_folder_name}}
STORAGE_BUCKETS = {
    "sales": {
        "proposals": "proposals",
        "mockups": "mockups",
        "documents": "documents",
        "templates": "templates",
        "uploads": "uploads",
    },
    "assets": {
        "location-images": "location-images",
        "network-assets": "network-assets",
    },
    "ui": {
        "avatars": "avatars",
    },
    "security": {
        "audit-exports": "audit-exports",
    },
}

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
    files_synced: int = 0
    bytes_synced: int = 0
    buckets_synced: int = 0
    errors: list = field(default_factory=list)

    def format_bytes(self) -> str:
        """Format bytes as human-readable size."""
        size = self.bytes_synced
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# =============================================================================
# SUPABASE CLIENTS
# =============================================================================

def get_ui_supabase() -> tuple[Client | None, str | None, str | None]:
    """Get UI Supabase client and credentials."""
    url = os.getenv("UI_DEV_SUPABASE_URL")
    key = os.getenv("UI_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None, None, None
    return create_client(url, key), url, key


def get_sales_supabase() -> tuple[Client | None, str | None, str | None]:
    """Get Sales Supabase client and credentials."""
    url = os.getenv("SALESBOT_DEV_SUPABASE_URL")
    key = os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None, None, None
    return create_client(url, key), url, key


def get_assets_supabase() -> tuple[Client | None, str | None, str | None]:
    """Get Asset Management Supabase client and credentials."""
    url = os.getenv("ASSETMGMT_DEV_SUPABASE_URL")
    key = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None, None, None
    return create_client(url, key), url, key


def get_security_supabase() -> tuple[Client | None, str | None, str | None]:
    """Get Security Supabase client and credentials."""
    url = os.getenv("SECURITY_DEV_SUPABASE_URL")
    key = os.getenv("SECURITY_DEV_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None, None, None
    return create_client(url, key), url, key


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

    client, _, _ = get_ui_supabase()
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

    client, _, _ = get_sales_supabase()
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


# =============================================================================
# STORAGE SYNC FUNCTIONS
# =============================================================================

def list_bucket_files(
    supabase_url: str,
    service_key: str,
    bucket_name: str,
    path: str = "",
) -> list[dict]:
    """
    List all files in a Supabase Storage bucket.

    Uses the Storage API directly since the Python SDK has limited support.

    Returns list of file objects with: name, id, metadata, etc.
    """
    storage_url = f"{supabase_url}/storage/v1/object/list/{bucket_name}"

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }

    payload = {
        "prefix": path,
        "limit": 1000,  # Max per request
        "offset": 0,
    }

    all_files = []

    try:
        with httpx.Client(timeout=60.0) as client:
            while True:
                response = client.post(storage_url, headers=headers, json=payload)
                response.raise_for_status()
                files = response.json()

                if not files:
                    break

                # Filter out folders (they have null id and name ending with /)
                for f in files:
                    if f.get("id") is not None:
                        all_files.append(f)
                    elif f.get("name", "").endswith("/"):
                        # It's a folder, recurse into it
                        subfolder = path + f["name"] if path else f["name"]
                        subfiles = list_bucket_files(supabase_url, service_key, bucket_name, subfolder)
                        all_files.extend(subfiles)

                if len(files) < payload["limit"]:
                    break

                payload["offset"] += len(files)

    except httpx.HTTPError as e:
        print(f"  Warning: Failed to list bucket {bucket_name}: {e}")

    return all_files


def download_file(
    supabase_url: str,
    service_key: str,
    bucket_name: str,
    file_path: str,
    local_path: Path,
) -> int:
    """
    Download a single file from Supabase Storage.

    Returns file size in bytes, or 0 if failed.
    """
    download_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{file_path}"

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(download_url, headers=headers)
            response.raise_for_status()

            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            local_path.write_bytes(response.content)
            return len(response.content)

    except httpx.HTTPError as e:
        print(f"  Warning: Failed to download {file_path}: {e}")
        return 0


def sync_bucket(
    supabase_url: str,
    service_key: str,
    bucket_name: str,
    local_folder: str,
    dry_run: bool = False,
    clear: bool = False,
    max_workers: int = 4,
) -> tuple[int, int]:
    """
    Sync a single Supabase Storage bucket to local filesystem.

    Args:
        supabase_url: Supabase project URL
        service_key: Service role key
        bucket_name: Name of the storage bucket
        local_folder: Local folder name under STORAGE_DIR
        dry_run: If True, don't actually download
        clear: If True, clear local folder first
        max_workers: Number of parallel download threads

    Returns:
        Tuple of (files_synced, bytes_synced)
    """
    local_path = STORAGE_DIR / local_folder
    files_synced = 0
    bytes_synced = 0

    print(f"\n  Bucket: {bucket_name} -> {local_folder}/")

    # Clear local folder if requested
    if clear and local_path.exists() and not dry_run:
        shutil.rmtree(local_path)
        print(f"    Cleared existing folder")

    # List files in bucket
    print(f"    Listing files...", end=" ")
    files = list_bucket_files(supabase_url, service_key, bucket_name)
    print(f"found {len(files)} files")

    if not files:
        return 0, 0

    if dry_run:
        total_size = sum(f.get("metadata", {}).get("size", 0) for f in files)
        print(f"    Would download: {len(files)} files")
        return len(files), total_size

    # Create local folder
    local_path.mkdir(parents=True, exist_ok=True)

    # Download files in parallel
    print(f"    Downloading...", end=" ", flush=True)

    def download_single(file_info: dict) -> int:
        file_name = file_info.get("name", "")
        file_local = local_path / file_name
        return download_file(supabase_url, service_key, bucket_name, file_name, file_local)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_single, f): f for f in files}

        for future in as_completed(futures):
            size = future.result()
            if size > 0:
                files_synced += 1
                bytes_synced += size

    print(f"done ({files_synced}/{len(files)} files)")
    return files_synced, bytes_synced


def sync_storage(
    dry_run: bool = False,
    clear: bool = False,
    buckets_filter: list[str] = None,
    projects_filter: list[str] = None,
) -> SyncStats:
    """
    Sync file storage from Supabase Storage to local filesystem.

    Downloads files from all configured storage buckets across all
    Supabase projects (Sales, Assets, UI, Security).

    Args:
        dry_run: If True, don't actually download files
        clear: If True, clear local storage first
        buckets_filter: Only sync these bucket names
        projects_filter: Only sync these projects (sales, assets, ui, security)
    """
    stats = SyncStats()

    print("\n" + "=" * 60)
    print("Syncing File Storage")
    print("=" * 60)

    # Ensure storage directory exists
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Get all Supabase clients
    clients = {
        "sales": get_sales_supabase(),
        "assets": get_assets_supabase(),
        "ui": get_ui_supabase(),
        "security": get_security_supabase(),
    }

    # Sync each project's buckets
    for project_name, (client, url, key) in clients.items():
        # Skip if project filter is set and this project isn't in it
        if projects_filter and project_name not in projects_filter:
            continue

        # Skip if no credentials
        if not client:
            print(f"\n  {project_name.upper()}: Not configured (skipping)")
            continue

        print(f"\n  {project_name.upper()} Storage:")

        # Get buckets for this project
        project_buckets = STORAGE_BUCKETS.get(project_name, {})

        for bucket_name, local_folder in project_buckets.items():
            # Skip if bucket filter is set and this bucket isn't in it
            if buckets_filter and bucket_name not in buckets_filter:
                continue

            try:
                files, bytes_ = sync_bucket(
                    url, key, bucket_name, local_folder,
                    dry_run=dry_run, clear=clear,
                )
                stats.files_synced += files
                stats.bytes_synced += bytes_
                stats.buckets_synced += 1
            except Exception as e:
                stats.errors.append(f"{project_name}/{bucket_name}: {e}")
                print(f"    Error: {e}")

    return stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sync data from Dev Supabase to local SQLite databases and storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python sync_from_supabase.py                    # Sync all databases
    python sync_from_supabase.py --dry-run          # Preview only
    python sync_from_supabase.py --clear            # Clear and re-sync
    python sync_from_supabase.py --tables users,profiles
    python sync_from_supabase.py --schema backlite_dubai

Storage sync:
    python sync_from_supabase.py --storage          # Also sync file storage
    python sync_from_supabase.py --storage-only     # Only sync file storage
    python sync_from_supabase.py --storage --buckets proposals,mockups
    python sync_from_supabase.py --storage --projects sales,assets
        """
    )

    # Database sync options
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--clear", action="store_true", help="Clear local data before sync")
    parser.add_argument("--tables", help="Comma-separated list of tables to sync")
    parser.add_argument("--schema", help="Specific company schema to sync")
    parser.add_argument("--ui-only", action="store_true", help="Only sync UI database")
    parser.add_argument("--sales-only", action="store_true", help="Only sync Sales database")

    # Storage sync options
    parser.add_argument("--storage", action="store_true", help="Also sync file storage from Supabase")
    parser.add_argument("--storage-only", action="store_true", help="Only sync file storage (skip databases)")
    parser.add_argument("--buckets", help="Comma-separated list of buckets to sync (e.g., proposals,mockups)")
    parser.add_argument("--projects", help="Comma-separated list of projects for storage sync (sales,assets,ui,security)")

    args = parser.parse_args()

    tables = args.tables.split(",") if args.tables else None
    schemas = [args.schema] if args.schema else None
    buckets = args.buckets.split(",") if args.buckets else None
    projects = args.projects.split(",") if args.projects else None

    print("\n" + "=" * 60)
    print("MMG DEV SUPABASE → LOCAL SYNC")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Clear: {args.clear}")
    print(f"Local DB dir: {LOCAL_DB_DIR}")
    print(f"Storage dir: {STORAGE_DIR}")

    total_stats = SyncStats()

    # Sync databases (unless storage-only mode)
    if not args.storage_only:
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
    if args.storage or args.storage_only:
        stats = sync_storage(
            dry_run=args.dry_run,
            clear=args.clear,
            buckets_filter=buckets,
            projects_filter=projects,
        )
        total_stats.files_synced += stats.files_synced
        total_stats.bytes_synced += stats.bytes_synced
        total_stats.buckets_synced += stats.buckets_synced
        total_stats.errors.extend(stats.errors)

    # Summary
    print("\n" + "=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)

    if not args.storage_only:
        print(f"Tables synced: {total_stats.tables_synced}")
        print(f"Rows synced: {total_stats.rows_synced}")

    if args.storage or args.storage_only:
        print(f"Buckets synced: {total_stats.buckets_synced}")
        print(f"Files synced: {total_stats.files_synced}")
        print(f"Data synced: {total_stats.format_bytes()}")

    if total_stats.errors:
        print(f"\nErrors: {len(total_stats.errors)}")
        for err in total_stats.errors:
            print(f"  - {err}")

    if not args.dry_run:
        if not args.storage_only:
            print(f"\nLocal databases created at:")
            print(f"  UI:    {UI_DB}")
            print(f"  Sales: {SALES_DB}")
        if args.storage or args.storage_only:
            print(f"\nLocal storage at: {STORAGE_DIR}")


if __name__ == "__main__":
    main()
