#!/usr/bin/env python3
"""
Asset Management Migration Script: Seed asset inventory to Supabase (Multi-Schema).

This script migrates asset/location inventory METADATA to Asset-Management Supabase:
1. Seeds locations from template metadata.txt files → {company}.standalone_assets
2. Creates initial network/package structures (if defined)

STORAGE ARCHITECTURE:
- Templates (.pptx) → Sales-Module Supabase Storage (used for proposal generation)
- Mockups/Frames → Sales-Module Supabase Storage (used for mockup generation)
- Asset Photos → Asset-Management Supabase Storage (real billboard photos)

This script does NOT upload templates - they belong in Sales-Module.

MULTI-SCHEMA ARCHITECTURE:
- Each company has its own schema (backlite_dubai, backlite_uk, etc.)
- Assets are migrated to the appropriate company schema based on company parameter

Usage:
    # Seed asset inventory (default - database only)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai

    # Dry run (preview)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai --dry-run

Prerequisites:
    - Schema must be applied: asset-management/db/migrations/01_schema.sql
    - Environment variables: ASSETMGMT_DEV_SUPABASE_URL, ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY

Valid company codes: backlite_dubai, backlite_uk, backlite_abudhabi, viola
"""

import argparse
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

# Load both .env and .env.secrets
load_dotenv()
load_dotenv(Path(__file__).parent.parent.parent / ".env.secrets")

import contextlib

from supabase import Client, create_client

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPO_ROOT = PROJECT_ROOT.parent.parent  # CRM root

# Template data lives in sales-module (source of truth for templates)
SALES_MODULE_DIR = REPO_ROOT / "src" / "sales-module"
BACKUP_DIR = SALES_MODULE_DIR / "data_backup_prod" / "data"
TEMPLATES_DIR = BACKUP_DIR / "templates"

# Also check render_main_data for files (production location)
RENDER_DATA_DIR = SALES_MODULE_DIR / "render_main_data"
RENDER_TEMPLATES_DIR = RENDER_DATA_DIR / "templates"

# Valid company schemas (must match schema.sql)
VALID_COMPANIES = ['backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola']

# Try DEV vars first, then PROD
SUPABASE_URL = (
    os.getenv("ASSETMGMT_DEV_SUPABASE_URL") or
    os.getenv("ASSETMGMT_PROD_SUPABASE_URL")
)
SUPABASE_KEY = (
    os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY") or
    os.getenv("ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY")
)

# Global company schema (set by --company argument)
COMPANY_SCHEMA = 'backlite_dubai'


def get_supabase() -> Client:
    """Get Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "Missing environment variables.\n"
            "Set ASSETMGMT_DEV_SUPABASE_URL and ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY\n"
            "(or ASSETMGMT_PROD_* for production)"
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_asset_key(text: str) -> str:
    """Normalize text to an asset_key format."""
    if not text:
        return ""
    # Remove common prefixes
    text = re.sub(r'^(the\s+)', '', text, flags=re.IGNORECASE)
    # Convert to lowercase, replace non-alphanumeric with underscores
    key = text.lower().strip()
    key = re.sub(r'[^a-z0-9]+', '_', key)
    key = key.strip('_')
    return key


def get_schema_table(supabase: Client, table: str):
    """Get a table reference with the correct schema."""
    return supabase.schema(COMPANY_SCHEMA).table(table)


def batch_insert(supabase: Client, table: str, records: list[dict],
                 batch_size: int = 50, on_conflict: str | None = None,
                 dry_run: bool = False) -> int:
    """Insert records in batches into company schema, return count of inserted records."""
    if not records:
        return 0

    if dry_run:
        return len(records)

    inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            if on_conflict:
                get_schema_table(supabase, table).upsert(batch, on_conflict=on_conflict).execute()
            else:
                get_schema_table(supabase, table).insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"    Error inserting batch {i//batch_size + 1}: {e}")
            # Try one by one to identify problematic records
            for record in batch:
                try:
                    if on_conflict:
                        get_schema_table(supabase, table).upsert(record, on_conflict=on_conflict).execute()
                    else:
                        get_schema_table(supabase, table).insert(record).execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    Failed record: {e2}")

    return inserted


# =============================================================================
# STORAGE UPLOAD FUNCTIONS
# =============================================================================

def get_mime_type(filepath: Path) -> str:
    """Get MIME type for a file."""
    mime_type, _ = mimetypes.guess_type(str(filepath))
    if mime_type:
        return mime_type

    # Fallback based on extension
    ext = filepath.suffix.lower()
    mime_map = {
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.pdf': 'application/pdf',
    }
    return mime_map.get(ext, 'application/octet-stream')


def upload_file_to_storage(supabase: Client, bucket: str, storage_path: str,
                           local_path: Path, dry_run: bool = False) -> bool:
    """Upload a single file to Supabase Storage."""
    if dry_run:
        return True

    try:
        with open(local_path, 'rb') as f:
            file_data = f.read()

        mime_type = get_mime_type(local_path)

        # Try to upload (will fail if exists, which is fine)
        supabase.storage.from_(bucket).upload(
            storage_path,
            file_data,
            file_options={"content-type": mime_type, "upsert": "true"}
        )
        return True
    except Exception as e:
        if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
            return True  # Already exists is fine
        print(f"      Error uploading {storage_path}: {e}")
        return False


def upload_templates(supabase: Client, dry_run: bool = False) -> int:
    """
    Upload asset templates to Supabase Storage.

    Structure: templates/{asset_key}/{asset_key}.pptx
    Note: intro_outro is uploaded (company branding slides), but not treated as an asset.
    """
    print("\n--- Uploading templates ---")

    # Find templates directory
    templates_dir = None
    for candidate in [TEMPLATES_DIR, RENDER_TEMPLATES_DIR]:
        if candidate.exists():
            templates_dir = candidate
            break

    if not templates_dir:
        print("  No templates directory found")
        return 0

    print(f"  Source: {templates_dir}")

    # Skip special directories (amr = test data)
    # NOTE: intro_outro is uploaded - it contains company-specific branding slides
    skip_dirs = {'amr', '.DS_Store'}

    uploaded = 0
    for asset_dir in sorted(templates_dir.iterdir()):
        if not asset_dir.is_dir():
            continue
        if asset_dir.name in skip_dirs or asset_dir.name.startswith('.'):
            continue

        asset_key = asset_dir.name

        # Upload template files only (.pptx)
        for filepath in asset_dir.iterdir():
            if filepath.name.startswith('.'):
                continue
            if filepath.suffix.lower() not in ('.pptx', '.ppt'):
                continue

            # Storage path: templates/{asset_key}/{filename}
            storage_path = f"{asset_key}/{filepath.name}"

            if dry_run:
                print(f"    [DRY RUN] Would upload: templates/{storage_path}")
                uploaded += 1
            else:
                if upload_file_to_storage(supabase, 'templates', storage_path, filepath):
                    uploaded += 1
                    if uploaded % 10 == 0:
                        print(f"    Progress: {uploaded} files")

    print(f"  Uploaded: {uploaded} template files")
    return uploaded


# =============================================================================
# STEP 1: SEED STANDALONE ASSETS FROM METADATA.TXT FILES
# =============================================================================

def parse_metadata_file(filepath: Path) -> dict[str, Any]:
    """Parse a metadata.txt file into asset data."""
    metadata = {}

    try:
        with open(filepath, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue

                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                value = value.strip()

                # Parse specific fields
                if key == 'sov':
                    value = value.replace('%', '').strip()
                    with contextlib.suppress(ValueError):
                        metadata['sov_percent'] = float(value)
                elif key == 'upload_fee':
                    with contextlib.suppress(ValueError):
                        metadata['upload_fee'] = float(value.replace(',', ''))
                elif key == 'spot_duration':
                    with contextlib.suppress(ValueError):
                        metadata['spot_duration'] = int(value)
                elif key == 'loop_duration':
                    with contextlib.suppress(ValueError):
                        metadata['loop_duration'] = int(value)
                elif key == 'number_of_faces':
                    try:
                        metadata['number_of_faces'] = int(value)
                    except ValueError:
                        metadata['number_of_faces'] = 1
                elif key == 'display_type':
                    metadata['display_type'] = value.lower()
                elif key == 'location_name':
                    metadata['display_name'] = value
                elif key == 'display_name':
                    if 'display_name' not in metadata:
                        metadata['display_name'] = value
                elif key == 'series':
                    metadata['series'] = value
                elif key == 'height':
                    metadata['height'] = value
                elif key == 'width':
                    metadata['width'] = value
                elif key == 'city':
                    metadata['city'] = value
                elif key == 'area':
                    metadata['area'] = value
                elif key == 'address':
                    metadata['address'] = value
    except Exception as e:
        print(f"    Error parsing {filepath}: {e}")

    return metadata


def get_template_path(asset_key: str, templates_dir: Path) -> str | None:
    """Find the template file path for an asset."""
    asset_dir = templates_dir / asset_key
    if not asset_dir.exists():
        return None

    pptx_files = list(asset_dir.glob('*.pptx'))
    if pptx_files:
        # Prefer file matching asset_key
        for pptx in pptx_files:
            if pptx.stem == asset_key:
                return f"{asset_key}/{pptx.name}"
        return f"{asset_key}/{pptx_files[0].name}"
    return None


def seed_standalone_assets(supabase: Client, dry_run: bool = False) -> tuple[int, dict[str, int]]:
    """
    Seed standalone assets from metadata.txt files.

    Returns:
        Tuple of (count inserted, asset_key -> id mapping)
    """
    print("\n" + "=" * 60)
    print("STEP 1: SEED STANDALONE ASSETS")
    print("=" * 60)

    # Find templates directory
    templates_dir = None
    for candidate in [TEMPLATES_DIR, RENDER_TEMPLATES_DIR]:
        if candidate.exists():
            templates_dir = candidate
            break

    if not templates_dir:
        print("  ERROR: No templates directory found")
        print(f"  Checked: {TEMPLATES_DIR}")
        print(f"  Checked: {RENDER_TEMPLATES_DIR}")
        return 0, {}

    print(f"  Templates directory: {templates_dir}")

    # Discover all assets
    assets = []
    metadata_files = list(templates_dir.glob('*/metadata.txt'))

    # Skip special directories (intro_outro = slides, amr = test data)
    skip_dirs = {'intro_outro', 'amr'}

    for metadata_file in sorted(metadata_files):
        asset_key = metadata_file.parent.name

        if asset_key in skip_dirs:
            print(f"    Skipping: {asset_key}")
            continue

        metadata = parse_metadata_file(metadata_file)

        # Determine display type
        display_type = metadata.get('display_type', 'digital')
        if display_type not in ('digital', 'static'):
            display_type = 'digital'

        asset = {
            'asset_key': asset_key,
            'display_name': metadata.get('display_name', asset_key.replace('_', ' ').title()),
            'display_type': display_type,
            'series': metadata.get('series'),
            'height': metadata.get('height'),
            'width': metadata.get('width'),
            'number_of_faces': metadata.get('number_of_faces', 1),
            'spot_duration': metadata.get('spot_duration'),
            'loop_duration': metadata.get('loop_duration'),
            'sov_percent': metadata.get('sov_percent'),
            'upload_fee': metadata.get('upload_fee'),
            'city': metadata.get('city'),
            'area': metadata.get('area'),
            'address': metadata.get('address'),
            'template_path': get_template_path(asset_key, templates_dir),
            'is_active': True,
            'created_by': 'migration_script',
        }

        # Remove None values for cleaner insert
        asset = {k: v for k, v in asset.items() if v is not None}
        assets.append(asset)
        print(f"    Found: {asset_key} ({asset.get('display_name', asset_key)})")

    print(f"\n  Total assets found: {len(assets)}")

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(assets)} assets")
        # Return fake IDs for dry run
        return len(assets), {asset['asset_key']: i+1 for i, asset in enumerate(assets)}

    # Insert assets
    inserted = batch_insert(supabase, 'standalone_assets', assets,
                           batch_size=50, on_conflict='asset_key')
    print(f"  Inserted/Updated: {inserted} assets")

    # Build asset_key -> id mapping
    result = get_schema_table(supabase, 'standalone_assets').select('id, asset_key').execute()
    asset_map = {asset['asset_key']: asset['id'] for asset in (result.data or [])}
    print(f"  Asset map built: {len(asset_map)} entries")

    return inserted, asset_map


# =============================================================================
# MAIN MIGRATION LOGIC
# =============================================================================

def run_migration(args: argparse.Namespace) -> None:
    """Run the full migration."""
    global COMPANY_SCHEMA
    COMPANY_SCHEMA = args.company

    print("\n" + "=" * 60)
    print("ASSET MANAGEMENT - MIGRATION TO SUPABASE")
    print("=" * 60)
    print(f"Company: {COMPANY_SCHEMA}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    supabase = get_supabase()

    # Seed standalone assets from template metadata
    assets_count, asset_map = seed_standalone_assets(supabase, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"  Standalone assets: {assets_count}")
    print("=" * 60)

    if args.dry_run:
        print("\n⚠️  DRY RUN - No changes were made")
    else:
        print("\n✅ Migration complete!")


def main():
    parser = argparse.ArgumentParser(
        description='Seed asset inventory metadata to Asset-Management Supabase (Multi-Schema)'
    )
    parser.add_argument(
        '--company',
        required=True,
        choices=VALID_COMPANIES,
        help='Company schema to migrate (e.g., backlite_dubai)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migration without making changes'
    )

    args = parser.parse_args()

    try:
        run_migration(args)
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
