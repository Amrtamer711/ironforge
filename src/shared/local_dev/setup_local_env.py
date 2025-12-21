#!/usr/bin/env python3
"""
Local Development Environment Setup Script.

This script sets up a fully offline development environment:
- Creates necessary directories
- Validates personas.yaml
- Optionally syncs data from Dev Supabase
- Creates sample .env.local file

Usage:
    python setup_local_env.py           # Quick setup (no sync)
    python setup_local_env.py --sync    # Setup with Supabase sync
    python setup_local_env.py --check   # Validate existing setup

Environment Variables (for --sync):
    UI_DEV_SUPABASE_URL
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY
    SALESBOT_DEV_SUPABASE_URL
    SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Paths (from src/shared/local_dev/setup_local_env.py -> go up 4 levels to CRM/)
REPO_ROOT = Path(__file__).parent.parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
SHARED_DIR = SRC_DIR / "shared"
DATA_DIR = REPO_ROOT / "data"  # At repo root, not inside src/
LOCAL_DB_DIR = DATA_DIR / "local"
STORAGE_DIR = DATA_DIR / "storage"
PERSONAS_FILE = SHARED_DIR / "testing" / "personas.yaml"

# Color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def create_directories():
    """Create necessary directories for local development."""
    print_header("Creating Directories")

    directories = [
        LOCAL_DB_DIR,
        STORAGE_DIR / "proposals",
        STORAGE_DIR / "mockups",
        STORAGE_DIR / "uploads",
        STORAGE_DIR / "templates",
        STORAGE_DIR / "documents",
    ]

    for dir_path in directories:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print_success(f"Created: {dir_path.relative_to(REPO_ROOT)}")
        else:
            print_info(f"Exists: {dir_path.relative_to(REPO_ROOT)}")


def validate_personas():
    """Validate that personas.yaml exists and is valid."""
    print_header("Validating Test Personas")

    if not PERSONAS_FILE.exists():
        print_error(f"personas.yaml not found at: {PERSONAS_FILE}")
        print_info("Create personas.yaml to enable local authentication")
        return False

    try:
        import yaml
        with open(PERSONAS_FILE) as f:
            data = yaml.safe_load(f)

        personas = data.get("personas", [])
        profiles = data.get("profiles", {})
        companies = data.get("companies", [])

        print_success(f"Found {len(personas)} test personas")
        print_success(f"Found {len(profiles)} profiles defined")
        print_success(f"Found {len(companies)} companies defined")

        # List personas
        print("\nAvailable test personas:")
        for p in personas[:5]:  # Show first 5
            print(f"  • {p['id']}: {p['email']} ({p.get('profile', 'unknown')})")
        if len(personas) > 5:
            print(f"  ... and {len(personas) - 5} more")

        return True

    except ImportError:
        print_error("PyYAML not installed. Install with: pip install pyyaml")
        return False
    except Exception as e:
        print_error(f"Error parsing personas.yaml: {e}")
        return False


def check_supabase_env():
    """Check if Supabase credentials are available."""
    print_header("Checking Supabase Credentials")

    ui_url = os.getenv("UI_DEV_SUPABASE_URL")
    ui_key = os.getenv("UI_DEV_SUPABASE_SERVICE_ROLE_KEY")
    sales_url = os.getenv("SALESBOT_DEV_SUPABASE_URL")
    sales_key = os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY")

    has_ui = bool(ui_url and ui_key)
    has_sales = bool(sales_url and sales_key)

    if has_ui:
        print_success("UI Supabase credentials found")
    else:
        print_warning("UI Supabase credentials not set")
        print_info("Set UI_DEV_SUPABASE_URL and UI_DEV_SUPABASE_SERVICE_ROLE_KEY")

    if has_sales:
        print_success("Sales Supabase credentials found")
    else:
        print_warning("Sales Supabase credentials not set")
        print_info("Set SALESBOT_DEV_SUPABASE_URL and SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY")

    return has_ui or has_sales


def sync_from_supabase():
    """Run the Supabase sync script."""
    print_header("Syncing from Dev Supabase")

    sync_script = SHARED_DIR / "local_dev" / "sync_from_supabase.py"
    if not sync_script.exists():
        print_error(f"Sync script not found: {sync_script}")
        return False

    import subprocess
    result = subprocess.run(
        [sys.executable, str(sync_script)],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )

    return result.returncode == 0


def create_env_local():
    """Create a sample .env.local file if it doesn't exist."""
    print_header("Creating .env.local Template")

    env_local = REPO_ROOT / ".env.local"

    if env_local.exists():
        print_info(".env.local already exists, skipping")
        return

    content = """\
# =============================================================================
# LOCAL DEVELOPMENT ENVIRONMENT
# =============================================================================
# This file configures fully offline development mode.
# Copy this to .env and modify as needed.

# Environment mode
ENVIRONMENT=local

# Auth provider: 'supabase' (default) or 'local' (offline)
AUTH_PROVIDER=local

# Database backend: 'supabase' (default) or 'sqlite' (offline)
DB_BACKEND=sqlite

# Storage provider: 'supabase' (default) or 'local' (offline)
STORAGE_PROVIDER=local

# Local SQLite database path (optional, defaults to data/local/)
# LOCAL_DB_PATH=/path/to/local/ui.db

# =============================================================================
# DEV SUPABASE (Optional - for syncing to local)
# =============================================================================
# Set these to sync data from Dev Supabase to local SQLite:
# UI_DEV_SUPABASE_URL=
# UI_DEV_SUPABASE_SERVICE_ROLE_KEY=
# SALESBOT_DEV_SUPABASE_URL=
# SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=

# =============================================================================
# LOCAL STORAGE
# =============================================================================
# Local file storage path (defaults to data/storage/)
# LOCAL_STORAGE_PATH=/path/to/storage/

# =============================================================================
# SERVICE PORTS (Local)
# =============================================================================
UI_PORT=3005
SALES_MODULE_PORT=8000
ASSET_MGMT_PORT=8001
"""

    env_local.write_text(content)
    print_success(f"Created: .env.local")
    print_info("Copy to .env and modify for your local setup")


def check_local_setup():
    """Validate the complete local setup."""
    print_header("Validating Local Setup")

    all_good = True

    # Check directories
    if LOCAL_DB_DIR.exists():
        print_success(f"Local DB directory exists")
    else:
        print_error(f"Local DB directory missing: {LOCAL_DB_DIR}")
        all_good = False

    if STORAGE_DIR.exists():
        print_success(f"Storage directory exists")
    else:
        print_error(f"Storage directory missing: {STORAGE_DIR}")
        all_good = False

    # Check personas
    if PERSONAS_FILE.exists():
        print_success(f"personas.yaml exists")
    else:
        print_warning(f"personas.yaml missing (required for local auth)")

    # Check databases
    ui_db = LOCAL_DB_DIR / "ui.db"
    sales_db = LOCAL_DB_DIR / "sales.db"

    if ui_db.exists():
        size_kb = ui_db.stat().st_size / 1024
        print_success(f"UI database exists ({size_kb:.1f} KB)")
    else:
        print_warning(f"UI database not synced yet")

    if sales_db.exists():
        size_kb = sales_db.stat().st_size / 1024
        print_success(f"Sales database exists ({size_kb:.1f} KB)")
    else:
        print_warning(f"Sales database not synced yet")

    # Check storage buckets
    buckets = ["proposals", "mockups", "uploads", "templates", "documents"]
    for bucket in buckets:
        bucket_path = STORAGE_DIR / bucket
        if bucket_path.exists():
            file_count = len(list(bucket_path.iterdir()))
            print_success(f"Storage bucket '{bucket}/' exists ({file_count} files)")
        else:
            print_warning(f"Storage bucket '{bucket}/' missing")

    return all_good


def get_directory_size(path: Path) -> tuple[int, int]:
    """Get total size and file count of a directory."""
    total_size = 0
    file_count = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
    return total_size, file_count


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def clean_local_data(dry_run: bool = False, keep_env: bool = True):
    """
    Clean up all local development data.

    Args:
        dry_run: If True, only show what would be deleted
        keep_env: If True, preserve .env.local file
    """
    print_header("Cleaning Local Development Data")

    items_to_clean = []
    env_local = REPO_ROOT / ".env.local"
    delete_env = False

    # SQLite databases
    if LOCAL_DB_DIR.exists():
        size, count = get_directory_size(LOCAL_DB_DIR)
        items_to_clean.append((LOCAL_DB_DIR, f"SQLite databases ({count} files, {format_size(size)})"))

    # Storage files
    if STORAGE_DIR.exists():
        size, count = get_directory_size(STORAGE_DIR)
        items_to_clean.append((STORAGE_DIR, f"Local storage ({count} files, {format_size(size)})"))

    # .env.local requires special approval
    if not keep_env and env_local.exists():
        print(f"{Colors.RED}{Colors.BOLD}⚠️  WARNING: --clean-all will delete .env.local{Colors.END}")
        print(f"{Colors.RED}   This file contains your local configuration settings.{Colors.END}")
        print(f"{Colors.RED}   You will need to reconfigure your environment after deletion.{Colors.END}\n")

        if not dry_run:
            env_confirm = input(f"{Colors.RED}Delete .env.local? Type 'DELETE' to confirm: {Colors.END}")
            if env_confirm == 'DELETE':
                delete_env = True
                items_to_clean.append((env_local, ".env.local config file"))
                print_success("Approved: .env.local will be deleted")
            else:
                print_info("Skipping .env.local (not approved)")
        else:
            items_to_clean.append((env_local, ".env.local config file (requires 'DELETE' confirmation)"))

    if not items_to_clean:
        print_info("Nothing to clean - local data directory is empty")
        return

    # Show what will be deleted
    print("\nThe following will be deleted:\n")
    total_size = 0
    for path, desc in items_to_clean:
        if path.is_dir():
            size, _ = get_directory_size(path)
        else:
            size = path.stat().st_size
        total_size += size
        print(f"  • {path.relative_to(REPO_ROOT)}")
        print(f"    {desc}")

    print(f"\n  Total: {format_size(total_size)}")

    if dry_run:
        print(f"\n{Colors.YELLOW}DRY RUN - No files were deleted{Colors.END}")
        return

    # Confirm deletion (skip if only env and already confirmed)
    if len(items_to_clean) > 1 or (len(items_to_clean) == 1 and not delete_env):
        print()
        confirm = input(f"{Colors.YELLOW}Are you sure you want to delete these files? [y/N]: {Colors.END}")
        if confirm.lower() != 'y':
            print_info("Cleanup cancelled")
            return

    # Delete files
    for path, desc in items_to_clean:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print_success(f"Deleted: {path.relative_to(REPO_ROOT)}")
        except Exception as e:
            print_error(f"Failed to delete {path}: {e}")

    print(f"\n{Colors.GREEN}✓ Cleanup complete! Freed {format_size(total_size)}{Colors.END}")


def show_storage_usage():
    """Show current local storage usage."""
    print_header("Local Storage Usage")

    items = [
        (LOCAL_DB_DIR, "SQLite Databases"),
        (STORAGE_DIR, "File Storage"),
    ]

    total_size = 0
    total_files = 0

    for path, name in items:
        if path.exists():
            size, count = get_directory_size(path)
            total_size += size
            total_files += count
            print(f"  {name}:")
            print(f"    Path: {path.relative_to(REPO_ROOT)}/")
            print(f"    Size: {format_size(size)} ({count} files)")

            # Show breakdown for storage buckets
            if path == STORAGE_DIR:
                for bucket in path.iterdir():
                    if bucket.is_dir():
                        b_size, b_count = get_directory_size(bucket)
                        if b_count > 0:
                            print(f"      └─ {bucket.name}/: {format_size(b_size)} ({b_count} files)")
            print()
        else:
            print(f"  {name}: (not created)")
            print()

    print(f"  {Colors.BOLD}Total: {format_size(total_size)} ({total_files} files){Colors.END}")


def print_usage_instructions():
    """Print instructions for using local mode."""
    print_header("Usage Instructions")

    print(f"""\
{Colors.BOLD}To run in fully offline mode:{Colors.END}

1. Set environment variables:
   export ENVIRONMENT=local
   export AUTH_PROVIDER=local
   export DB_BACKEND=sqlite
   export STORAGE_PROVIDER=local

2. Use test personas for authentication:
   curl -H "Authorization: Bearer local-test_admin" http://localhost:3005/api/...
   curl -H "Authorization: Bearer local-rep_dubai_1" http://localhost:3005/api/...

3. Or use email as token:
   curl -H "Authorization: Bearer test.admin@mmg.ae" http://localhost:3005/api/...

{Colors.BOLD}Available test personas:{Colors.END}
  • test_admin     - Full system admin
  • hos_backlite   - Head of Sales (Backlite group)
  • hos_viola      - Head of Sales (Viola)
  • rep_dubai_1    - Sales Rep (Dubai)
  • coordinator_1  - Operations Coordinator
  • finance_1      - Finance Team
  • viewer_only    - Read-only viewer

{Colors.BOLD}To sync data from Dev Supabase:{Colors.END}
  python src/shared/local_dev/sync_from_supabase.py

{Colors.BOLD}To use the Dev Panel UI:{Colors.END}
  Open http://localhost:3005/dev-panel.html in your browser

{Colors.BOLD}To clean up local data:{Colors.END}
  python src/shared/local_dev/setup_local_env.py --clean
""")


def main():
    parser = argparse.ArgumentParser(
        description="Set up local development environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python setup_local_env.py                # Set up local environment
    python setup_local_env.py --sync         # Set up with Supabase sync
    python setup_local_env.py --check        # Validate existing setup
    python setup_local_env.py --usage        # Show storage usage
    python setup_local_env.py --clean        # Clean all local data
    python setup_local_env.py --clean --dry-run  # Preview cleanup
        """,
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sync data from Dev Supabase to local SQLite",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only validate existing setup, don't create anything",
    )
    parser.add_argument(
        "--skip-personas",
        action="store_true",
        help="Skip personas.yaml validation",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean up all local data (databases and storage files)",
    )
    parser.add_argument(
        "--clean-all",
        action="store_true",
        help="Clean everything including .env.local",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Show current local storage usage",
    )

    args = parser.parse_args()

    print(f"\n{Colors.BOLD}🏠 MMG Local Development Setup{Colors.END}\n")
    print(f"Repository: {REPO_ROOT}")

    # Usage check
    if args.usage:
        show_storage_usage()
        return

    # Clean mode
    if args.clean or args.clean_all:
        clean_local_data(
            dry_run=args.dry_run,
            keep_env=not args.clean_all,
        )
        return

    # Check mode
    if args.check:
        check_local_setup()
        return

    # Full setup
    create_directories()

    if not args.skip_personas:
        validate_personas()

    if args.sync:
        if check_supabase_env():
            sync_from_supabase()
        else:
            print_warning("Skipping sync: Supabase credentials not configured")
    else:
        print_info("Use --sync to sync data from Dev Supabase")

    create_env_local()
    check_local_setup()
    print_usage_instructions()

    print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Local environment setup complete!{Colors.END}\n")


if __name__ == "__main__":
    main()
