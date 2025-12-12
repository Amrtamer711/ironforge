#!/usr/bin/env python3
"""
Complete SQLite to Supabase Migration Script.

This script performs a full migration from the SQLite backup to Supabase:
1. Seeds locations from template metadata.txt files
2. Loads all SQLite table data (proposals_log, mockup_frames, mockup_usage, etc.)
3. Links records to the locations table (location_id foreign keys)
4. Creates proposal_locations and bo_locations junction table entries

Usage:
    python db/scripts/load_sqlite_backup.py [--dry-run] [--skip-locations] [--tables TABLE1 TABLE2]

Prerequisites:
    - Schema must be applied: salesbot_schema_v2.sql
    - Environment variables: SALESBOT_DEV_SUPABASE_URL, SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY
      (or SALESBOT_PROD_* for production)
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
# Load both .env and .env.secrets
load_dotenv()
load_dotenv(Path(__file__).parent.parent.parent / ".env.secrets")

from supabase import create_client, Client

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "data_backup_prod" / "data"
SQLITE_DB = BACKUP_DIR / "proposals.db"
TEMPLATES_DIR = BACKUP_DIR / "templates"

# Also check render_main_data for templates (production location)
RENDER_TEMPLATES_DIR = PROJECT_ROOT / "render_main_data" / "templates"

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


def batch_insert(supabase: Client, table: str, records: List[Dict],
                 batch_size: int = 50, on_conflict: Optional[str] = None,
                 dry_run: bool = False) -> int:
    """Insert records in batches, return count of inserted records."""
    if not records:
        return 0

    if dry_run:
        return len(records)

    inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            if on_conflict:
                supabase.table(table).upsert(batch, on_conflict=on_conflict).execute()
            else:
                supabase.table(table).insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"    Error inserting batch {i//batch_size + 1}: {e}")
            # Try one by one to identify problematic records
            for record in batch:
                try:
                    if on_conflict:
                        supabase.table(table).upsert(record, on_conflict=on_conflict).execute()
                    else:
                        supabase.table(table).insert(record).execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    Failed record: {e2}")

    return inserted


# =============================================================================
# STEP 1: SEED LOCATIONS FROM METADATA.TXT FILES
# =============================================================================

def parse_metadata_file(filepath: Path) -> Dict[str, Any]:
    """Parse a metadata.txt file into location data."""
    metadata = {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
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


def get_template_path(location_key: str, templates_dir: Path) -> Optional[str]:
    """Find the template file path for a location."""
    location_dir = templates_dir / location_key
    if not location_dir.exists():
        return None

    pptx_files = list(location_dir.glob('*.pptx'))
    if pptx_files:
        # Prefer file matching location_key
        for pptx in pptx_files:
            if pptx.stem == location_key:
                return f"{location_key}/{pptx.name}"
        return f"{location_key}/{pptx_files[0].name}"
    return None


def seed_locations(supabase: Client, dry_run: bool = False) -> Tuple[int, Dict[str, int]]:
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
        print(f"  ERROR: No templates directory found")
        print(f"  Checked: {TEMPLATES_DIR}")
        print(f"  Checked: {RENDER_TEMPLATES_DIR}")
        return 0, {}

    print(f"  Templates directory: {templates_dir}")

    # Discover all locations
    locations = []
    metadata_files = list(templates_dir.glob('*/metadata.txt'))

    # Skip special directories
    skip_dirs = {'intro_outro', 'amr', 't3'}

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
            'template_path': get_template_path(location_key, templates_dir),
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
    result = supabase.table('locations').select('id, location_key').execute()
    location_map = {loc['location_key']: loc['id'] for loc in (result.data or [])}
    print(f"  Location map built: {len(location_map)} entries")

    return inserted, location_map


# =============================================================================
# STEP 2: LOAD SQLITE TABLE DATA
# =============================================================================

def load_proposals_log(supabase: Client, conn: sqlite3.Connection,
                       dry_run: bool = False) -> Tuple[int, List[Dict]]:
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

        record = {
            'user_id': row['submitted_by'],  # Slack ID initially
            'submitted_by': row['submitted_by'],
            'client_name': row['client_name'],
            'date_generated': row['date_generated'],
            'package_type': row['package_type'],
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
            result = supabase.table('proposals_log').insert(record).execute()
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

    records = []
    for row in rows:
        frames_data = parse_json_field(row['frames_data'])
        if frames_data is None:
            frames_data = []

        config_json = parse_json_field(row['config_json'])

        record = {
            'location_key': row['location_key'],
            'time_of_day': row['time_of_day'] or 'day',
            'finish': row['finish'] or 'gold',
            'photo_filename': row['photo_filename'],
            'frames_data': frames_data,
            'created_at': row['created_at'],
            'created_by': row['created_by'],
            'config_json': config_json,
        }
        records.append(record)

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
                        dry_run: bool = False) -> Tuple[int, List[Dict]]:
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
            result = supabase.table('booking_orders').upsert(
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
            supabase.table('ai_costs').insert(batch).execute()
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

def link_mockups_to_locations(supabase: Client, location_map: Dict[str, int],
                              dry_run: bool = False) -> Tuple[int, int]:
    """Link mockup_frames and mockup_usage to locations table."""
    print("\n--- Linking mockups to locations ---")

    frames_updated = 0
    usage_updated = 0

    # Update mockup_frames
    result = supabase.table('mockup_frames').select('id, location_key').is_('location_id', 'null').execute()

    for frame in (result.data or []):
        location_key = frame.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if not dry_run:
                try:
                    supabase.table('mockup_frames').update(
                        {'location_id': location_id}
                    ).eq('id', frame['id']).execute()
                    frames_updated += 1
                except Exception as e:
                    print(f"    Error updating frame {frame['id']}: {e}")
            else:
                frames_updated += 1

    # Update mockup_usage
    result = supabase.table('mockup_usage').select('id, location_key').is_('location_id', 'null').execute()

    for usage in (result.data or []):
        location_key = usage.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if not dry_run:
                try:
                    supabase.table('mockup_usage').update(
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


def create_proposal_locations(supabase: Client, location_map: Dict[str, int],
                             proposal_mapping: List[Dict], dry_run: bool = False) -> int:
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

    inserted = batch_insert(supabase, 'proposal_locations', records,
                           on_conflict='proposal_id,location_key')
    print(f"  Created: {inserted} entries")
    return inserted


def create_bo_locations(supabase: Client, location_map: Dict[str, int],
                        bo_mapping: List[Dict], dry_run: bool = False) -> int:
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
            supabase.table('bo_locations').insert(record).execute()
            inserted += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"    Error: {e}")

    print(f"  Created: {inserted} entries")
    return inserted


# =============================================================================
# MAIN MIGRATION
# =============================================================================

def run_migration(dry_run: bool = False, skip_locations: bool = False,
                  tables: Optional[List[str]] = None):
    """Run the complete migration."""
    print("=" * 70)
    print("COMPLETE SQLITE TO SUPABASE MIGRATION")
    print("=" * 70)
    print(f"SQLite Source: {SQLITE_DB}")
    print(f"Templates: {TEMPLATES_DIR}")
    print(f"Dry Run: {dry_run}")
    print(f"Skip Locations: {skip_locations}")
    if tables:
        print(f"Tables: {', '.join(tables)}")
    print()

    # Initialize clients
    supabase = get_supabase()
    conn = get_sqlite()

    results = {}
    location_map = {}
    proposal_mapping = []
    bo_mapping = []

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
        result = supabase.table('locations').select('id, location_key').execute()
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
        print("\n[DRY RUN] No data was actually inserted.")
        print("Run without --dry-run to perform actual migration.")
    else:
        print("\nMigration complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate SQLite backup to Supabase")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without inserting data")
    parser.add_argument("--skip-locations", action="store_true",
                       help="Skip location seeding (use existing)")
    parser.add_argument("--tables", nargs="+",
                       help="Specific tables to load (default: all)")

    args = parser.parse_args()

    run_migration(
        dry_run=args.dry_run,
        skip_locations=args.skip_locations,
        tables=args.tables
    )
