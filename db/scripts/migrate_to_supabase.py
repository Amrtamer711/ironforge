#!/usr/bin/env python3
"""
Complete Migration Script: SQLite + Files → Supabase (Multi-Schema).

This script performs a full migration to Supabase:
1. Seeds locations from template metadata.txt files → {company}.locations
2. Loads all SQLite table data → {company}.proposals_log, {company}.mockup_frames, etc.
3. Links records to the locations table (location_id foreign keys)
4. Creates proposal_locations and bo_locations junction table entries
5. Uploads files to Supabase Storage with company folder structure

Usage:
    # Full migration (database + storage)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai

    # Database only (no file uploads)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai --skip-storage

    # Storage only (no database)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai --storage-only

    # Dry run (preview)
    python db/scripts/migrate_to_supabase.py --company backlite_dubai --dry-run

Prerequisites:
    - Schema must be applied: salesbot/01_schema.sql (creates company schemas)
    - Storage buckets must exist: templates, mockups, fonts
    - Environment variables: SALESBOT_DEV_SUPABASE_URL, SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY

Valid company codes: backlite_dubai, backlite_uk, backlite_abudhabi, viola
"""

import json
import mimetypes
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

# Load both .env and .env.secrets
load_dotenv()
load_dotenv(Path(__file__).parent.parent.parent / ".env.secrets")

from supabase import Client, create_client

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "data_backup_prod" / "data"
SQLITE_DB = BACKUP_DIR / "proposals.db"
TEMPLATES_DIR = BACKUP_DIR / "templates"
MOCKUPS_DIR = BACKUP_DIR / "mockups"
FONTS_DIR = BACKUP_DIR / "Sofia-Pro Font"
BOOKING_ORDERS_DIR = BACKUP_DIR / "booking_orders"

# Also check render_main_data for files (production location)
RENDER_DATA_DIR = PROJECT_ROOT / "render_main_data"
RENDER_TEMPLATES_DIR = RENDER_DATA_DIR / "templates"
RENDER_MOCKUPS_DIR = RENDER_DATA_DIR / "mockups"
RENDER_FONTS_DIR = RENDER_DATA_DIR / "Sofia-Pro Font"

# Valid company schemas (must match salesbot/01_schema.sql)
VALID_COMPANIES = ['backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola']

# Try DEV vars first, then PROD, then legacy names
SUPABASE_URL = (
    os.getenv("SALESBOT_DEV_SUPABASE_URL") or
    os.getenv("SALESBOT_PROD_SUPABASE_URL") or
    os.getenv("SALESBOT_SUPABASE_URL")
)
SUPABASE_KEY = (
    os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY") or
    os.getenv("SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY") or
    os.getenv("SALESBOT_SUPABASE_SERVICE_KEY")
)

# Global company schema (set by --company argument)
COMPANY_SCHEMA = 'backlite_dubai'


def get_supabase() -> Client:
    """Get Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "Missing environment variables.\n"
            "Set SALESBOT_DEV_SUPABASE_URL and SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY\n"
            "(or SALESBOT_PROD_* for production)"
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_sqlite() -> sqlite3.Connection:
    """Get SQLite connection."""
    if not SQLITE_DB.exists():
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_DB}")
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_location_key(text: str) -> str:
    """Normalize text to a location_key format."""
    if not text:
        return ""
    # Remove common prefixes
    text = re.sub(r'^(the\s+)', '', text, flags=re.IGNORECASE)
    # Convert to lowercase, replace non-alphanumeric with underscores
    key = text.lower().strip()
    key = re.sub(r'[^a-z0-9]+', '_', key)
    key = key.strip('_')
    return key


def parse_json_field(value: Any) -> Any:
    """Parse a JSON field from SQLite (TEXT) to Python object."""
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def get_schema_table(supabase: Client, table: str):
    """Get a table reference with the correct schema."""
    return supabase.schema(COMPANY_SCHEMA).table(table)


def batch_insert(supabase: Client, table: str, records: list[dict],
                 batch_size: int = 50, on_conflict: Optional[str] = None,
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
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.ttf': 'font/ttf',
        '.otf': 'font/otf',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.pdf': 'application/pdf',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
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


def upload_templates(supabase: Client, company: str, dry_run: bool = False) -> int:
    """
    Upload templates to Supabase Storage.

    Structure: templates/{company}/{location_key}/{location_key}.pptx
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
    for location_dir in sorted(templates_dir.iterdir()):
        if not location_dir.is_dir():
            continue
        if location_dir.name in skip_dirs or location_dir.name.startswith('.'):
            continue

        location_key = location_dir.name

        # Upload all files in the location directory
        for filepath in location_dir.iterdir():
            if filepath.name.startswith('.'):
                continue

            # Storage path: templates/{company}/{location_key}/{filename}
            storage_path = f"{company}/{location_key}/{filepath.name}"

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


def upload_mockups(supabase: Client, company: str, dry_run: bool = False) -> int:
    """
    Upload mockups (background photos) to Supabase Storage.

    Structure: mockups/{company}/{location_key}/{time_of_day}/{finish}/{photo}.jpg
    """
    print("\n--- Uploading mockups ---")

    # Find mockups directory
    mockups_dir = None
    for candidate in [MOCKUPS_DIR, RENDER_MOCKUPS_DIR]:
        if candidate.exists():
            mockups_dir = candidate
            break

    if not mockups_dir:
        print("  No mockups directory found")
        return 0

    print(f"  Source: {mockups_dir}")

    uploaded = 0

    # Walk the mockups directory structure
    for location_dir in sorted(mockups_dir.iterdir()):
        if not location_dir.is_dir():
            continue
        if location_dir.name.startswith('.'):
            continue

        location_key = location_dir.name

        # Walk through time_of_day/finish/photos structure
        for item in location_dir.rglob('*'):
            if not item.is_file():
                continue
            if item.name.startswith('.'):
                continue

            # Get relative path from location directory
            rel_path = item.relative_to(location_dir)

            # Storage path: mockups/{company}/{location_key}/{relative_path}
            storage_path = f"{company}/{location_key}/{rel_path}"

            if dry_run:
                print(f"    [DRY RUN] Would upload: mockups/{storage_path}")
                uploaded += 1
            else:
                if upload_file_to_storage(supabase, 'mockups', storage_path, item):
                    uploaded += 1
                    if uploaded % 20 == 0:
                        print(f"    Progress: {uploaded} files")

    print(f"  Uploaded: {uploaded} mockup files")
    return uploaded


def upload_fonts(supabase: Client, dry_run: bool = False) -> int:
    """
    Upload fonts to Supabase Storage.

    Structure: fonts/Sofia-Pro/{font}.ttf (shared, not per-company)
    """
    print("\n--- Uploading fonts ---")

    # Find fonts directory
    fonts_dir = None
    for candidate in [FONTS_DIR, RENDER_FONTS_DIR]:
        if candidate.exists():
            fonts_dir = candidate
            break

    if not fonts_dir:
        print("  No fonts directory found")
        return 0

    print(f"  Source: {fonts_dir}")

    uploaded = 0

    for filepath in sorted(fonts_dir.iterdir()):
        if filepath.name.startswith('.'):
            continue
        if not filepath.is_file():
            continue

        # Font extensions
        if filepath.suffix.lower() not in ('.ttf', '.otf', '.woff', '.woff2'):
            continue

        # Storage path: fonts/Sofia-Pro/{filename}
        storage_path = f"Sofia-Pro/{filepath.name}"

        if dry_run:
            print(f"    [DRY RUN] Would upload: fonts/{storage_path}")
            uploaded += 1
        else:
            if upload_file_to_storage(supabase, 'fonts', storage_path, filepath):
                uploaded += 1

    print(f"  Uploaded: {uploaded} font files")
    return uploaded


def upload_booking_orders(supabase: Client, company: str, dry_run: bool = False) -> int:
    """
    Upload booking order files to Supabase Storage.

    Structure: booking_orders/{company}/{subfolder}/{filename}
    Subfolders: original_uploads, combined_bos, original_bos, parsed_bos
    """
    print("\n--- Uploading booking orders ---")

    if not BOOKING_ORDERS_DIR.exists():
        print(f"  No booking_orders directory found at {BOOKING_ORDERS_DIR}")
        return 0

    print(f"  Source: {BOOKING_ORDERS_DIR}")

    uploaded = 0

    # Walk all subdirectories
    for subfolder in sorted(BOOKING_ORDERS_DIR.iterdir()):
        if not subfolder.is_dir():
            continue
        if subfolder.name.startswith('.'):
            continue

        subfolder_name = subfolder.name

        # Upload all files in this subfolder
        for filepath in subfolder.iterdir():
            if filepath.name.startswith('.'):
                continue
            if not filepath.is_file():
                continue

            # Storage path: booking_orders/{company}/{subfolder}/{filename}
            storage_path = f"{company}/{subfolder_name}/{filepath.name}"

            if dry_run:
                print(f"    [DRY RUN] Would upload: booking_orders/{storage_path}")
                uploaded += 1
            else:
                if upload_file_to_storage(supabase, 'booking_orders', storage_path, filepath):
                    uploaded += 1
                    if uploaded % 10 == 0:
                        print(f"    Progress: {uploaded} files")

    print(f"  Uploaded: {uploaded} booking order files")
    return uploaded


# =============================================================================
# STEP 1: SEED LOCATIONS FROM METADATA.TXT FILES
# =============================================================================

def parse_metadata_file(filepath: Path) -> dict[str, Any]:
    """Parse a metadata.txt file into location data."""
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
                    try:
                        metadata['sov_percent'] = float(value)
                    except ValueError:
                        pass
                elif key == 'upload_fee':
                    try:
                        metadata['upload_fee'] = float(value.replace(',', ''))
                    except ValueError:
                        pass
                elif key == 'spot_duration':
                    try:
                        metadata['spot_duration'] = int(value)
                    except ValueError:
                        pass
                elif key == 'loop_duration':
                    try:
                        metadata['loop_duration'] = int(value)
                    except ValueError:
                        pass
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
    except Exception as e:
        print(f"    Error parsing {filepath}: {e}")

    return metadata


def get_template_path(location_key: str, templates_dir: Path, company: str) -> Optional[str]:
    """Find the template file path for a location (with company prefix)."""
    location_dir = templates_dir / location_key
    if not location_dir.exists():
        return None

    pptx_files = list(location_dir.glob('*.pptx'))
    if pptx_files:
        # Prefer file matching location_key
        for pptx in pptx_files:
            if pptx.stem == location_key:
                return f"{company}/{location_key}/{pptx.name}"
        return f"{company}/{location_key}/{pptx_files[0].name}"
    return None


def seed_locations(supabase: Client, dry_run: bool = False) -> tuple[int, dict[str, int]]:
    """
    Seed locations from metadata.txt files.

    Returns:
        Tuple of (count inserted, location_key -> id mapping)
    """
    print("\n" + "=" * 60)
    print("STEP 1: SEED LOCATIONS")
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

    # Discover all locations
    locations = []
    metadata_files = list(templates_dir.glob('*/metadata.txt'))

    # Skip special directories (intro_outro = slides, amr = test data)
    skip_dirs = {'intro_outro', 'amr'}

    for metadata_file in sorted(metadata_files):
        location_key = metadata_file.parent.name

        if location_key in skip_dirs:
            print(f"    Skipping: {location_key}")
            continue

        metadata = parse_metadata_file(metadata_file)

        # Determine display type
        display_type = metadata.get('display_type', 'digital')
        if display_type not in ('digital', 'static'):
            display_type = 'digital'

        location = {
            'location_key': location_key,
            'display_name': metadata.get('display_name', location_key.replace('_', ' ').title()),
            'display_type': display_type,
            'series': metadata.get('series'),
            'height': metadata.get('height'),
            'width': metadata.get('width'),
            'number_of_faces': metadata.get('number_of_faces', 1),
            'spot_duration': metadata.get('spot_duration'),
            'loop_duration': metadata.get('loop_duration'),
            'sov_percent': metadata.get('sov_percent'),
            'upload_fee': metadata.get('upload_fee'),
            'template_path': get_template_path(location_key, templates_dir, COMPANY_SCHEMA),
            'is_active': True,
            'created_by': 'migration_script',
        }

        # Remove None values for cleaner insert
        location = {k: v for k, v in location.items() if v is not None}
        locations.append(location)
        print(f"    Found: {location_key} ({location.get('display_name', location_key)})")

    print(f"\n  Total locations found: {len(locations)}")

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(locations)} locations")
        # Return fake IDs for dry run
        return len(locations), {loc['location_key']: i+1 for i, loc in enumerate(locations)}

    # Insert locations
    inserted = batch_insert(supabase, 'locations', locations,
                           batch_size=50, on_conflict='location_key')
    print(f"  Inserted/Updated: {inserted} locations")

    # Build location_key -> id mapping
    result = get_schema_table(supabase, 'locations').select('id, location_key').execute()
    location_map = {loc['location_key']: loc['id'] for loc in (result.data or [])}
    print(f"  Location map built: {len(location_map)} entries")

    return inserted, location_map


# =============================================================================
# STEP 2: LOAD SQLITE TABLE DATA
# =============================================================================

def load_proposals_log(supabase: Client, conn: sqlite3.Connection,
                       dry_run: bool = False) -> tuple[int, list[dict]]:
    """
    Load proposals_log from SQLite.

    Returns:
        Tuple of (count inserted, list of {sqlite_id, supabase_id, locations_text})
    """
    print("\n--- proposals_log ---")

    cursor = conn.execute("SELECT * FROM proposals_log ORDER BY id")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0, []

    records = []
    proposal_mapping = []  # Track SQLite ID -> locations text for later

    for row in rows:
        # Store locations text for later extraction
        locations_text = row['locations'] or ''

        # Map package_type: 'single' -> 'separate' (schema only allows 'separate' or 'combined')
        package_type = row['package_type']
        if package_type not in ('separate', 'combined'):
            package_type = 'separate'  # Default 'single' and others to 'separate'

        record = {
            'user_id': row['submitted_by'],  # Slack ID initially
            'submitted_by': row['submitted_by'],
            'client_name': row['client_name'],
            'date_generated': row['date_generated'],
            'package_type': package_type,
            'total_amount': row['total_amount'],
            'currency': 'AED',
            # Store in proposal_data for reference
            'proposal_data': {
                'locations_text': locations_text,
                'migrated_from_sqlite_id': row['id'],
            },
        }
        records.append(record)
        proposal_mapping.append({
            'sqlite_id': row['id'],
            'locations_text': locations_text,
            'total_amount': row['total_amount'],
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        # Fake IDs for dry run
        for i, pm in enumerate(proposal_mapping):
            pm['supabase_id'] = i + 1
        return len(records), proposal_mapping

    # Insert and capture IDs
    inserted = 0
    for i, record in enumerate(records):
        try:
            result = get_schema_table(supabase, 'proposals_log').insert(record).execute()
            if result.data:
                proposal_mapping[i]['supabase_id'] = result.data[0]['id']
                inserted += 1
        except Exception as e:
            print(f"    Error inserting proposal {i}: {e}")
            proposal_mapping[i]['supabase_id'] = None

    print(f"  Inserted: {inserted} records")
    return inserted, proposal_mapping


def load_mockup_frames(supabase: Client, conn: sqlite3.Connection,
                       dry_run: bool = False) -> int:
    """Load mockup_frames from SQLite."""
    print("\n--- mockup_frames ---")

    cursor = conn.execute("SELECT * FROM mockup_frames ORDER BY id")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0

    # Skip test data locations
    skip_locations = {'amr'}

    # Valid enum values per schema constraints
    valid_time_of_day = {'day', 'night'}
    valid_finish = {'gold', 'silver', 'black'}

    records = []
    skipped = 0
    for row in rows:
        location_key = row['location_key']

        # Skip test data
        if location_key in skip_locations:
            skipped += 1
            continue

        time_of_day = row['time_of_day'] or 'day'
        finish = row['finish'] or 'gold'

        # Validate enum values - skip invalid records
        if time_of_day not in valid_time_of_day:
            print(f"    Skipping {location_key}: invalid time_of_day='{time_of_day}'")
            skipped += 1
            continue
        if finish not in valid_finish:
            print(f"    Skipping {location_key}: invalid finish='{finish}'")
            skipped += 1
            continue

        frames_data = parse_json_field(row['frames_data'])
        if frames_data is None:
            frames_data = []

        config_json = parse_json_field(row['config_json'])

        record = {
            'location_key': location_key,
            'time_of_day': time_of_day,
            'finish': finish,
            'photo_filename': row['photo_filename'],
            'frames_data': frames_data,
            'created_at': row['created_at'],
            'created_by': row['created_by'],
            'config_json': config_json,
        }
        records.append(record)

    if skipped > 0:
        print(f"  Skipped: {skipped} invalid/test records")

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'mockup_frames', records,
                           on_conflict='location_key,time_of_day,finish,photo_filename')
    print(f"  Inserted: {inserted} records")
    return inserted


def load_mockup_usage(supabase: Client, conn: sqlite3.Connection,
                      dry_run: bool = False) -> int:
    """Load mockup_usage from SQLite."""
    print("\n--- mockup_usage ---")

    cursor = conn.execute("SELECT * FROM mockup_usage ORDER BY id")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0

    records = []
    for row in rows:
        record = {
            'location_key': row['location_key'],
            'generated_at': row['generated_at'],
            'time_of_day': row['time_of_day'],
            'finish': row['finish'],
            'photo_used': row['photo_used'],
            'creative_type': row['creative_type'],
            'ai_prompt': row['ai_prompt'],
            'template_selected': bool(row['template_selected']),
            'success': bool(row['success']),
            'user_ip': row['user_ip'],
        }
        records.append(record)

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'mockup_usage', records, batch_size=100)
    print(f"  Inserted: {inserted} records")
    return inserted


def load_booking_orders(supabase: Client, conn: sqlite3.Connection,
                        dry_run: bool = False) -> tuple[int, list[dict]]:
    """
    Load booking_orders from SQLite.

    Returns:
        Tuple of (count inserted, list of {sqlite_id, supabase_id, locations_json, asset})
    """
    print("\n--- booking_orders ---")

    cursor = conn.execute("SELECT * FROM booking_orders ORDER BY id")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0, []

    records = []
    bo_mapping = []

    for row in rows:
        locations_json = parse_json_field(row['locations_json'])
        warnings_json = parse_json_field(row['warnings_json'])
        missing_fields_json = parse_json_field(row['missing_fields_json'])

        record = {
            'bo_ref': row['bo_ref'],
            'company': row['company'],
            'original_file_path': row['original_file_path'],
            'original_file_type': row['original_file_type'],
            'original_file_size': row['original_file_size'],
            'original_filename': row['original_filename'],
            'parsed_excel_path': row['parsed_excel_path'],
            'bo_number': row['bo_number'],
            'bo_date': row['bo_date'],
            'client': row['client'],
            'agency': row['agency'],
            'brand_campaign': row['brand_campaign'],
            'category': row['category'],
            'asset': row['asset'],
            'net_pre_vat': row['net_pre_vat'],
            'vat_value': row['vat_value'],
            'gross_amount': row['gross_amount'],
            'sla_pct': row['sla_pct'],
            'payment_terms': row['payment_terms'],
            'sales_person': row['sales_person'],
            'commission_pct': row['commission_pct'],
            'notes': row['notes'],
            'locations_json': locations_json,
            'extraction_method': row['extraction_method'],
            'extraction_confidence': row['extraction_confidence'],
            'warnings_json': warnings_json,
            'missing_fields_json': missing_fields_json,
            'vat_calc': row['vat_calc'],
            'gross_calc': row['gross_calc'],
            'sla_deduction': row['sla_deduction'],
            'net_excl_sla_calc': row['net_excl_sla_calc'],
            'parsed_at': row['parsed_at'],
            'parsed_by': row['parsed_by'],
            'source_classification': row['source_classification'],
            'classification_confidence': row['classification_confidence'],
            'needs_review': bool(row['needs_review']),
            'search_text': row['search_text'],
        }
        records.append(record)
        bo_mapping.append({
            'sqlite_id': row['id'],
            'bo_ref': row['bo_ref'],
            'locations_json': locations_json,
            'asset': row['asset'],
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        for i, bm in enumerate(bo_mapping):
            bm['supabase_id'] = i + 1
        return len(records), bo_mapping

    # Insert and capture IDs
    inserted = 0
    for i, record in enumerate(records):
        try:
            result = get_schema_table(supabase, 'booking_orders').upsert(
                record, on_conflict='bo_ref'
            ).execute()
            if result.data:
                bo_mapping[i]['supabase_id'] = result.data[0]['id']
                inserted += 1
        except Exception as e:
            print(f"    Error inserting BO {record['bo_ref']}: {e}")
            bo_mapping[i]['supabase_id'] = None

    print(f"  Inserted: {inserted} records")
    return inserted, bo_mapping


def load_bo_workflows(supabase: Client, conn: sqlite3.Connection,
                      dry_run: bool = False) -> int:
    """Load bo_approval_workflows from SQLite."""
    print("\n--- bo_approval_workflows ---")

    cursor = conn.execute("SELECT * FROM bo_approval_workflows ORDER BY created_at")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0

    records = []
    for row in rows:
        workflow_data = parse_json_field(row['workflow_data'])
        if workflow_data is None:
            workflow_data = {}

        # Map status to V2 enum
        status = workflow_data.get('status', 'pending')
        stage = workflow_data.get('stage', 'coordinator')

        if status == 'approved':
            status = 'hos_approved' if stage == 'hos' else 'coordinator_approved'
        elif status == 'rejected':
            status = 'hos_rejected' if stage == 'hos' else 'coordinator_rejected'
        elif status not in ('pending', 'cancelled', 'completed',
                           'coordinator_approved', 'coordinator_rejected',
                           'hos_approved', 'hos_rejected'):
            status = 'pending'

        record = {
            'workflow_id': row['workflow_id'],
            'workflow_data': workflow_data,
            'status': status,
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }
        records.append(record)

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'bo_approval_workflows', records,
                           on_conflict='workflow_id')
    print(f"  Inserted: {inserted} records")
    return inserted


def load_ai_costs(supabase: Client, conn: sqlite3.Connection,
                  dry_run: bool = False) -> int:
    """Load ai_costs from SQLite."""
    print("\n--- ai_costs ---")

    cursor = conn.execute("SELECT * FROM ai_costs ORDER BY id")
    rows = cursor.fetchall()

    if not rows:
        print("  No data")
        return 0

    # Valid enum values for V2 schema
    valid_call_types = {
        'classification', 'parsing', 'coordinator_thread', 'main_llm',
        'mockup_analysis', 'image_generation', 'bo_edit', 'other'
    }
    valid_workflows = {
        'mockup_upload', 'mockup_ai', 'bo_parsing', 'bo_editing',
        'bo_revision', 'proposal_generation', 'general_chat',
        'location_management', None
    }

    records = []
    for row in rows:
        metadata_json = parse_json_field(row['metadata_json'])

        call_type = row['call_type']
        if call_type not in valid_call_types:
            call_type = 'other'

        workflow = row['workflow']
        if workflow not in valid_workflows:
            workflow = None

        record = {
            'timestamp': row['timestamp'],
            'call_type': call_type,
            'workflow': workflow,
            'model': row['model'],
            'user_id': row['user_id'],
            'context': row['context'],
            'input_tokens': row['input_tokens'],
            'cached_input_tokens': row['cached_input_tokens'] or 0,
            'output_tokens': row['output_tokens'],
            'reasoning_tokens': row['reasoning_tokens'] or 0,
            'total_tokens': row['total_tokens'],
            'input_cost': row['input_cost'],
            'output_cost': row['output_cost'],
            'reasoning_cost': row['reasoning_cost'] or 0,
            'total_cost': row['total_cost'],
            'metadata_json': metadata_json,
        }
        records.append(record)

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    # Insert in larger batches since there's no conflict key
    inserted = 0
    batch_size = 100
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            get_schema_table(supabase, 'ai_costs').insert(batch).execute()
            inserted += len(batch)
            if inserted % 500 == 0:
                print(f"    Progress: {inserted}/{len(records)}")
        except Exception as e:
            print(f"    Error at batch {i//batch_size}: {e}")

    print(f"  Inserted: {inserted} records")
    return inserted


# =============================================================================
# STEP 3: LINK RECORDS TO LOCATIONS
# =============================================================================

def link_mockups_to_locations(supabase: Client, location_map: dict[str, int],
                              dry_run: bool = False) -> tuple[int, int]:
    """Link mockup_frames and mockup_usage to locations table."""
    print("\n--- Linking mockups to locations ---")

    frames_updated = 0
    usage_updated = 0

    # Update mockup_frames
    result = get_schema_table(supabase, 'mockup_frames').select('id, location_key').is_('location_id', 'null').execute()

    for frame in (result.data or []):
        location_key = frame.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if not dry_run:
                try:
                    get_schema_table(supabase, 'mockup_frames').update(
                        {'location_id': location_id}
                    ).eq('id', frame['id']).execute()
                    frames_updated += 1
                except Exception as e:
                    print(f"    Error updating frame {frame['id']}: {e}")
            else:
                frames_updated += 1

    # Update mockup_usage
    result = get_schema_table(supabase, 'mockup_usage').select('id, location_key').is_('location_id', 'null').execute()

    for usage in (result.data or []):
        location_key = usage.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if not dry_run:
                try:
                    get_schema_table(supabase, 'mockup_usage').update(
                        {'location_id': location_id}
                    ).eq('id', usage['id']).execute()
                    usage_updated += 1
                except Exception as e:
                    print(f"    Error updating usage {usage['id']}: {e}")
            else:
                usage_updated += 1

    print(f"  Frames linked: {frames_updated}")
    print(f"  Usage linked: {usage_updated}")
    return frames_updated, usage_updated


def create_proposal_locations(supabase: Client, location_map: dict[str, int],
                             proposal_mapping: list[dict], dry_run: bool = False) -> int:
    """Create proposal_locations entries from proposals_log locations text."""
    print("\n--- Creating proposal_locations ---")

    records = []

    for pm in proposal_mapping:
        supabase_id = pm.get('supabase_id')
        if not supabase_id:
            continue

        locations_text = pm.get('locations_text', '')
        total_amount = pm.get('total_amount', '')

        # Parse locations: "Uae31, Uae23, Uae14"
        location_keys = [normalize_location_key(l.strip())
                        for l in locations_text.split(',') if l.strip()]

        # Parse amounts: "AED 446,796, AED 446,796, AED 446,796"
        amounts = re.findall(r'AED\s*([\d,]+)', total_amount)
        amounts = [float(a.replace(',', '')) for a in amounts]

        for i, loc_key in enumerate(location_keys):
            if not loc_key:
                continue

            location_id = location_map.get(loc_key)
            net_rate = amounts[i] if i < len(amounts) else None

            record = {
                'proposal_id': supabase_id,
                'location_key': loc_key,
                'location_id': location_id,
                'location_display_name': loc_key.upper().replace('_', ' '),
                'net_rate': net_rate,
            }
            records.append(record)

    if dry_run:
        print(f"  [DRY RUN] Would create {len(records)} entries")
        return len(records)

    # No on_conflict - allow duplicate locations per proposal (different options/finishes)
    inserted = batch_insert(supabase, 'proposal_locations', records)
    print(f"  Created: {inserted} entries")
    return inserted


def create_bo_locations(supabase: Client, location_map: dict[str, int],
                        bo_mapping: list[dict], dry_run: bool = False) -> int:
    """Create bo_locations entries from booking_orders locations_json."""
    print("\n--- Creating bo_locations ---")

    records = []

    for bm in bo_mapping:
        supabase_id = bm.get('supabase_id')
        if not supabase_id:
            continue

        locations_json = bm.get('locations_json')
        asset = bm.get('asset')

        locations_data = []

        # Extract from locations_json if available
        if isinstance(locations_json, list):
            for item in locations_json:
                if isinstance(item, dict):
                    loc_data = {'raw_location_text': None, 'location_key': None}

                    # Try to find location identifier
                    for key in ('location_key', 'location', 'asset', 'name', 'site'):
                        if key in item and item[key]:
                            loc_data['raw_location_text'] = str(item[key])
                            loc_data['location_key'] = normalize_location_key(str(item[key]))
                            break

                    # Extract dates
                    for key in ('start_date', 'startDate', 'start'):
                        if key in item and item[key]:
                            loc_data['start_date'] = str(item[key])[:10]
                            break

                    for key in ('end_date', 'endDate', 'end'):
                        if key in item and item[key]:
                            loc_data['end_date'] = str(item[key])[:10]
                            break

                    # Extract rate
                    for key in ('net_rate', 'netRate', 'rate', 'amount'):
                        if key in item and item[key]:
                            try:
                                loc_data['net_rate'] = float(str(item[key]).replace(',', ''))
                            except ValueError:
                                pass
                            break

                    if loc_data['location_key']:
                        locations_data.append(loc_data)

                elif isinstance(item, str):
                    key = normalize_location_key(item)
                    if key:
                        locations_data.append({
                            'location_key': key,
                            'raw_location_text': item,
                        })

        # Fallback to asset field
        if not locations_data and asset:
            key = normalize_location_key(asset)
            if key:
                locations_data.append({
                    'location_key': key,
                    'raw_location_text': asset,
                })

        # Create records
        for loc_data in locations_data:
            loc_key = loc_data.get('location_key')
            if not loc_key:
                continue

            location_id = location_map.get(loc_key)

            record = {
                'bo_id': supabase_id,
                'location_key': loc_key,
                'location_id': location_id,
                'raw_location_text': loc_data.get('raw_location_text'),
                'start_date': loc_data.get('start_date'),
                'end_date': loc_data.get('end_date'),
                'net_rate': loc_data.get('net_rate'),
            }
            # Remove None values
            record = {k: v for k, v in record.items() if v is not None}
            records.append(record)

    if dry_run:
        print(f"  [DRY RUN] Would create {len(records)} entries")
        return len(records)

    # Insert one by one to handle potential duplicates
    inserted = 0
    for record in records:
        try:
            get_schema_table(supabase, 'bo_locations').insert(record).execute()
            inserted += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"    Error: {e}")

    print(f"  Created: {inserted} entries")
    return inserted


# =============================================================================
# MAIN MIGRATION
# =============================================================================

def run_migration(company: str, dry_run: bool = False, skip_locations: bool = False,
                  skip_storage: bool = False, storage_only: bool = False,
                  tables: Optional[list[str]] = None):
    """Run the complete migration to a company schema."""
    global COMPANY_SCHEMA
    COMPANY_SCHEMA = company

    print("=" * 70)
    print("COMPLETE MIGRATION TO SUPABASE (Multi-Schema)")
    print("=" * 70)
    print(f"Target Company: {COMPANY_SCHEMA}")
    print(f"SQLite Source: {SQLITE_DB}")
    print(f"Templates: {TEMPLATES_DIR}")
    print(f"Dry Run: {dry_run}")
    print(f"Skip Locations: {skip_locations}")
    print(f"Skip Storage: {skip_storage}")
    print(f"Storage Only: {storage_only}")
    if tables:
        print(f"Tables: {', '.join(tables)}")
    print()

    # Initialize clients
    supabase = get_supabase()

    results = {}
    location_map = {}
    proposal_mapping = []
    bo_mapping = []

    # =========================================================================
    # STORAGE UPLOAD (if not skipped)
    # =========================================================================
    if not skip_storage:
        print("\n" + "=" * 60)
        print("STORAGE UPLOAD")
        print("=" * 60)

        results['templates_uploaded'] = upload_templates(supabase, company, dry_run)
        results['mockups_uploaded'] = upload_mockups(supabase, company, dry_run)
        results['fonts_uploaded'] = upload_fonts(supabase, dry_run)
        results['booking_orders_uploaded'] = upload_booking_orders(supabase, company, dry_run)

    # If storage-only mode, stop here
    if storage_only:
        print("\n" + "=" * 70)
        print("STORAGE UPLOAD SUMMARY")
        print("=" * 70)
        for key, value in results.items():
            print(f"  {key}: {value}")
        return

    # =========================================================================
    # DATABASE MIGRATION
    # =========================================================================

    # Need SQLite for database migration
    conn = get_sqlite()

    # All tables to load
    all_tables = ['proposals_log', 'mockup_frames', 'mockup_usage',
                  'booking_orders', 'bo_approval_workflows', 'ai_costs']

    if tables:
        tables_to_load = [t for t in all_tables if t in tables]
    else:
        tables_to_load = all_tables

    # Step 1: Seed locations
    if not skip_locations:
        loc_count, location_map = seed_locations(supabase, dry_run)
        results['locations'] = loc_count
    else:
        print("\n[Skipping location seeding]")
        # Build location map from existing data
        result = get_schema_table(supabase, 'locations').select('id, location_key').execute()
        location_map = {loc['location_key']: loc['id'] for loc in (result.data or [])}
        print(f"  Loaded existing location map: {len(location_map)} entries")

    # Step 2: Load SQLite data
    print("\n" + "=" * 60)
    print("STEP 2: LOAD SQLITE DATA")
    print("=" * 60)

    if 'proposals_log' in tables_to_load:
        count, proposal_mapping = load_proposals_log(supabase, conn, dry_run)
        results['proposals_log'] = count

    if 'mockup_frames' in tables_to_load:
        results['mockup_frames'] = load_mockup_frames(supabase, conn, dry_run)

    if 'mockup_usage' in tables_to_load:
        results['mockup_usage'] = load_mockup_usage(supabase, conn, dry_run)

    if 'booking_orders' in tables_to_load:
        count, bo_mapping = load_booking_orders(supabase, conn, dry_run)
        results['booking_orders'] = count

    if 'bo_approval_workflows' in tables_to_load:
        results['bo_approval_workflows'] = load_bo_workflows(supabase, conn, dry_run)

    if 'ai_costs' in tables_to_load:
        results['ai_costs'] = load_ai_costs(supabase, conn, dry_run)

    conn.close()

    # Step 3: Link to locations
    print("\n" + "=" * 60)
    print("STEP 3: LINK TO LOCATIONS")
    print("=" * 60)

    if location_map:
        frames, usage = link_mockups_to_locations(supabase, location_map, dry_run)
        results['mockup_frames_linked'] = frames
        results['mockup_usage_linked'] = usage

        if proposal_mapping:
            results['proposal_locations'] = create_proposal_locations(
                supabase, location_map, proposal_mapping, dry_run
            )

        if bo_mapping:
            results['bo_locations'] = create_bo_locations(
                supabase, location_map, bo_mapping, dry_run
            )
    else:
        print("  Skipping (no location map)")

    # Summary
    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    for key, value in results.items():
        print(f"  {key}: {value}")

    if dry_run:
        print("\n[DRY RUN] No data was actually inserted/uploaded.")
        print("Run without --dry-run to perform actual migration.")
    else:
        print("\nMigration complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate SQLite + files to Supabase company schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full migration (database + storage)
  python db/scripts/migrate_to_supabase.py --company backlite_dubai

  # Database only
  python db/scripts/migrate_to_supabase.py --company backlite_dubai --skip-storage

  # Storage only
  python db/scripts/migrate_to_supabase.py --company backlite_dubai --storage-only

  # Dry run
  python db/scripts/migrate_to_supabase.py --company backlite_dubai --dry-run
        """
    )
    parser.add_argument("--company", required=True, choices=VALID_COMPANIES,
                       help=f"Target company schema: {', '.join(VALID_COMPANIES)}")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without inserting data")
    parser.add_argument("--skip-locations", action="store_true",
                       help="Skip location seeding (use existing)")
    parser.add_argument("--skip-storage", action="store_true",
                       help="Skip file uploads to storage")
    parser.add_argument("--storage-only", action="store_true",
                       help="Only upload files to storage (skip database)")
    parser.add_argument("--tables", nargs="+",
                       help="Specific tables to load (default: all)")

    args = parser.parse_args()

    run_migration(
        company=args.company,
        dry_run=args.dry_run,
        skip_locations=args.skip_locations,
        skip_storage=args.skip_storage,
        storage_only=args.storage_only,
        tables=args.tables
    )
