#!/usr/bin/env python3
"""
MIGRATION 06B: MIGRATE MOCKUP STORAGE PATHS
============================================
Migrates mockup photos in Supabase Storage from old path structure to new.

OLD PATH: mockups/{company}/{location_key}/{time_of_day}/{finish}/{photo}
NEW PATH: mockups/{company}/{location_key}/outdoor/{time_of_day}/{side}/{photo}

Changes:
1. Add 'outdoor' environment level (all existing photos are outdoor)
2. Rename 'black' folders to 'single_side'

Run this AFTER the database migration (06_mockup_frames_rename_finish_to_side.sql)

Usage:
    # Dry run (preview changes without executing):
    python 06b_migrate_mockup_storage.py --dry-run

    # Execute migration:
    python 06b_migrate_mockup_storage.py --execute

    # Execute for specific company only:
    python 06b_migrate_mockup_storage.py --execute --company backlite_dubai
"""

import os
import sys
import argparse
import logging
from dataclasses import dataclass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from supabase import create_client, Client
except ImportError:
    logger.error("supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


# =============================================================================
# CONFIGURATION
# =============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
BUCKET_NAME = "mockups"

COMPANIES = ["backlite_dubai", "backlite_uk", "backlite_abudhabi", "viola"]

# Old finish values -> new side values
FINISH_TO_SIDE = {
    "gold": "gold",
    "silver": "silver",
    "black": "single_side",
}


@dataclass
class MigrationItem:
    """Represents a file to migrate."""
    old_path: str
    new_path: str
    company: str
    location_key: str


def get_supabase_client() -> Client:
    """Create authenticated Supabase client."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError(
            "Missing environment variables. Set:\n"
            "  SUPABASE_URL\n"
            "  SUPABASE_SERVICE_ROLE_KEY"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def list_bucket_files(client: Client, prefix: str = "") -> list[dict]:
    """List all files in bucket under given prefix."""
    all_files = []
    offset = 0
    limit = 1000

    while True:
        response = client.storage.from_(BUCKET_NAME).list(
            path=prefix,
            options={"limit": limit, "offset": offset}
        )

        if not response:
            break

        all_files.extend(response)

        if len(response) < limit:
            break

        offset += limit

    return all_files


def discover_migration_items(client: Client, companies: list[str]) -> list[MigrationItem]:
    """
    Discover all files that need migration.

    Old structure: {company}/{location_key}/{time_of_day}/{finish}/{photo}
    New structure: {company}/{location_key}/outdoor/{time_of_day}/{side}/{photo}
    """
    items = []

    for company in companies:
        logger.info(f"Scanning company: {company}")

        # List location folders under company
        locations = list_bucket_files(client, company)

        for loc_item in locations:
            if loc_item.get("id") is None:  # It's a folder
                location_key = loc_item["name"]
                location_prefix = f"{company}/{location_key}"

                # Check if this location already has 'outdoor' or 'indoor' folders
                # (already migrated or new structure)
                sub_items = list_bucket_files(client, location_prefix)
                sub_names = [s["name"] for s in sub_items if s.get("id") is None]

                if "outdoor" in sub_names or "indoor" in sub_names:
                    logger.debug(f"  {location_key}: Already migrated (has outdoor/indoor)")
                    continue

                # Old structure - check for time_of_day folders (day/night)
                for tod_item in sub_items:
                    if tod_item.get("id") is None:  # It's a folder
                        time_of_day = tod_item["name"]

                        if time_of_day not in ("day", "night"):
                            logger.warning(f"  {location_key}: Unexpected folder '{time_of_day}', skipping")
                            continue

                        tod_prefix = f"{location_prefix}/{time_of_day}"

                        # Check finish folders (gold/silver/black)
                        finish_items = list_bucket_files(client, tod_prefix)

                        for finish_item in finish_items:
                            if finish_item.get("id") is None:  # It's a folder
                                old_finish = finish_item["name"]

                                if old_finish not in FINISH_TO_SIDE:
                                    logger.warning(f"  {location_key}/{time_of_day}: Unknown finish '{old_finish}'")
                                    continue

                                new_side = FINISH_TO_SIDE[old_finish]
                                finish_prefix = f"{tod_prefix}/{old_finish}"

                                # List photos in this finish folder
                                photos = list_bucket_files(client, finish_prefix)

                                for photo_item in photos:
                                    if photo_item.get("id") is not None:  # It's a file
                                        photo_name = photo_item["name"]

                                        old_path = f"{company}/{location_key}/{time_of_day}/{old_finish}/{photo_name}"
                                        new_path = f"{company}/{location_key}/outdoor/{time_of_day}/{new_side}/{photo_name}"

                                        items.append(MigrationItem(
                                            old_path=old_path,
                                            new_path=new_path,
                                            company=company,
                                            location_key=location_key,
                                        ))

    return items


def migrate_file(client: Client, item: MigrationItem, dry_run: bool = True) -> bool:
    """
    Migrate a single file from old path to new path.

    Strategy: Copy to new location, then delete old.
    """
    if dry_run:
        logger.info(f"  [DRY RUN] Would move: {item.old_path} -> {item.new_path}")
        return True

    try:
        # Download file content
        response = client.storage.from_(BUCKET_NAME).download(item.old_path)

        if not response:
            logger.error(f"  Failed to download: {item.old_path}")
            return False

        # Upload to new path
        upload_response = client.storage.from_(BUCKET_NAME).upload(
            path=item.new_path,
            file=response,
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )

        if not upload_response:
            logger.error(f"  Failed to upload: {item.new_path}")
            return False

        # Delete old file
        delete_response = client.storage.from_(BUCKET_NAME).remove([item.old_path])

        if not delete_response:
            logger.warning(f"  Uploaded but failed to delete old: {item.old_path}")
            # Still consider success since new file exists

        logger.info(f"  Migrated: {item.old_path} -> {item.new_path}")
        return True

    except Exception as e:
        logger.error(f"  Error migrating {item.old_path}: {e}")
        return False


def run_migration(dry_run: bool = True, company_filter: str | None = None):
    """Run the full migration."""
    logger.info("=" * 60)
    logger.info("MOCKUP STORAGE MIGRATION")
    logger.info("=" * 60)
    logger.info(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE'}")
    logger.info("")

    # Initialize client
    try:
        client = get_supabase_client()
        logger.info("Connected to Supabase")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return False

    # Filter companies if specified
    companies = [company_filter] if company_filter else COMPANIES
    logger.info(f"Companies to process: {companies}")
    logger.info("")

    # Discover files to migrate
    logger.info("Discovering files to migrate...")
    items = discover_migration_items(client, companies)

    if not items:
        logger.info("No files need migration. Storage is already up to date!")
        return True

    logger.info(f"Found {len(items)} files to migrate")
    logger.info("")

    # Group by company for reporting
    by_company = {}
    for item in items:
        by_company.setdefault(item.company, []).append(item)

    for company, company_items in by_company.items():
        logger.info(f"{company}: {len(company_items)} files")

    logger.info("")

    if dry_run:
        logger.info("DRY RUN - Showing first 20 migrations:")
        for item in items[:20]:
            logger.info(f"  {item.old_path}")
            logger.info(f"    -> {item.new_path}")
        if len(items) > 20:
            logger.info(f"  ... and {len(items) - 20} more")
        logger.info("")
        logger.info("To execute migration, run with --execute flag")
        return True

    # Execute migration
    logger.info("Executing migration...")
    success_count = 0
    fail_count = 0

    for i, item in enumerate(items, 1):
        logger.info(f"[{i}/{len(items)}] Migrating {item.location_key}...")

        if migrate_file(client, item, dry_run=False):
            success_count += 1
        else:
            fail_count += 1

    logger.info("")
    logger.info("=" * 60)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Success: {success_count}")
    logger.info(f"Failed:  {fail_count}")
    logger.info(f"Total:   {len(items)}")

    return fail_count == 0


def main():
    parser = argparse.ArgumentParser(
        description="Migrate mockup storage paths to new structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing (default)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration"
    )
    parser.add_argument(
        "--company",
        type=str,
        help="Only migrate specific company (e.g., backlite_dubai)"
    )

    args = parser.parse_args()

    # Default to dry-run unless --execute specified
    dry_run = not args.execute

    if args.execute:
        logger.warning("=" * 60)
        logger.warning("WARNING: This will modify files in Supabase Storage!")
        logger.warning("Make sure database migration has been run first.")
        logger.warning("=" * 60)
        response = input("Type 'yes' to continue: ")
        if response.lower() != "yes":
            logger.info("Aborted.")
            return

    success = run_migration(dry_run=dry_run, company_filter=args.company)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
