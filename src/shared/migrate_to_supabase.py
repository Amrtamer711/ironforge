#!/usr/bin/env python3
"""
Consolidated Migration Script: Local Data → Supabase (Multi-Service Architecture).

This script migrates data to the correct Supabase projects:

ASSET-MANAGEMENT SUPABASE (inventory/locations/templates/mockups):
  - {company}.standalone_assets - Location metadata from metadata.txt files
  - {company}.networks - Network groupings (future)
  - {company}.packages - Package bundles (future)
  - {company}.mockup_frames - Mockup frame coordinate data
  - Storage: templates/ - PowerPoint templates per location
  - Storage: mockups/ - Mockup background photos per location

SALES-MODULE SUPABASE (proposals/BOs/analytics):
  - Storage: fonts/, booking_orders/
  - public.proposals_log - Proposal history
  - public.proposal_locations - Links proposals to locations (via location_key)
  - {company}.mockup_usage - Mockup analytics
  - public.booking_orders - Booking order records
  - public.bo_locations - Links BOs to locations (via location_key)
  - public.bo_approval_workflows - BO approval workflows
  - public.ai_costs - AI usage tracking

CROSS-SERVICE LINKING:
  - Sales-Module references Asset-Management via `location_key` (TEXT)
  - No foreign keys between services (separate Supabase projects)

Usage:
    # Full migration (both services)
    python src/shared/migrate_to_supabase.py --company backlite_dubai

    # Dry run (preview)
    python src/shared/migrate_to_supabase.py --company backlite_dubai --dry-run

    # Asset-Management only (locations)
    python src/shared/migrate_to_supabase.py --company backlite_dubai --assets-only

    # Sales-Module only (proposals, mockups, storage)
    python src/shared/migrate_to_supabase.py --company backlite_dubai --sales-only

    # Skip storage uploads
    python src/shared/migrate_to_supabase.py --company backlite_dubai --skip-storage

Prerequisites:
    - Asset-Management schema applied: asset-management/db/migrations/01_schema.sql
    - Asset-Management mockup_frames: asset-management/db/migrations/02_mockup_frames.sql
    - Sales-Module schema applied: sales-module/db/migrations/salesbot/01_schema.sql
    - Storage buckets created in Asset-Management: templates, mockups
    - Storage buckets created in Sales-Module: fonts, booking_orders

Environment Variables:
    ASSETMGMT_DEV_SUPABASE_URL, ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY
    SALESBOT_DEV_SUPABASE_URL, SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY

Valid company codes: backlite_dubai, backlite_uk, backlite_abudhabi, viola
"""

import argparse
import contextlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment
load_dotenv()
REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env.secrets")

from supabase import Client, create_client

# =============================================================================
# CONFIGURATION
# =============================================================================

SALES_MODULE_DIR = REPO_ROOT / "src" / "sales-module"
BACKUP_DIR = SALES_MODULE_DIR / "data_backup_prod" / "data"
SQLITE_DB = BACKUP_DIR / "proposals.db"
TEMPLATES_DIR = BACKUP_DIR / "templates"
MOCKUPS_DIR = BACKUP_DIR / "mockups"
FONTS_DIR = BACKUP_DIR / "Sofia-Pro Font"
BOOKING_ORDERS_DIR = BACKUP_DIR / "booking_orders"

# Fallback locations
RENDER_DATA_DIR = SALES_MODULE_DIR / "render_main_data"
RENDER_TEMPLATES_DIR = RENDER_DATA_DIR / "templates"
RENDER_MOCKUPS_DIR = RENDER_DATA_DIR / "mockups"

VALID_COMPANIES = ['backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola']

# Global state
COMPANY_SCHEMA = 'backlite_dubai'


# =============================================================================
# SUPABASE CLIENTS
# =============================================================================

def get_asset_mgmt_supabase() -> Client:
    """Get Asset-Management Supabase client."""
    url = os.getenv("ASSETMGMT_DEV_SUPABASE_URL") or os.getenv("ASSETMGMT_PROD_SUPABASE_URL")
    key = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError(
            "Missing Asset-Management credentials.\n"
            "Set ASSETMGMT_DEV_SUPABASE_URL and ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY"
        )
    return create_client(url, key)


def get_sales_supabase() -> Client:
    """Get Sales-Module Supabase client."""
    url = os.getenv("SALESBOT_DEV_SUPABASE_URL") or os.getenv("SALESBOT_PROD_SUPABASE_URL")
    key = os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError(
            "Missing Sales-Module credentials.\n"
            "Set SALESBOT_DEV_SUPABASE_URL and SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY"
        )
    return create_client(url, key)


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
    text = re.sub(r'^(the\s+)', '', text, flags=re.IGNORECASE)
    key = text.lower().strip()
    key = re.sub(r'[^a-z0-9]+', '_', key)
    return key.strip('_')


def parse_json_field(value: Any) -> Any:
    """Parse a JSON field from SQLite."""
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


def parse_amount_text(amount_text: str) -> float | None:
    """Parse formatted amount text to numeric value."""
    if not amount_text:
        return None
    amounts = re.findall(r'[\d,]+(?:\.\d+)?', str(amount_text))
    if not amounts:
        return None
    total = sum(float(a.replace(',', '')) for a in amounts if a)
    return total if total > 0 else None


def get_schema_table(supabase: Client, table: str):
    """Get a table reference with the correct schema."""
    return supabase.schema(COMPANY_SCHEMA).table(table)


def batch_insert(supabase: Client, table: str, records: list[dict],
                 batch_size: int = 50, on_conflict: str | None = None,
                 schema: str | None = None, dry_run: bool = False) -> int:
    """Insert records in batches, return count."""
    if not records or dry_run:
        return len(records) if dry_run else 0

    tbl = supabase.schema(schema or COMPANY_SCHEMA).table(table)
    inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            if on_conflict:
                tbl.upsert(batch, on_conflict=on_conflict).execute()
            else:
                tbl.insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"    Error batch {i//batch_size + 1}: {e}")
            for record in batch:
                try:
                    if on_conflict:
                        tbl.upsert(record, on_conflict=on_conflict).execute()
                    else:
                        tbl.insert(record).execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    Failed: {e2}")
    return inserted


# =============================================================================
# STORAGE UPLOAD (Sales-Module)
# =============================================================================

def get_mime_type(filepath: Path) -> str:
    """Get MIME type for a file."""
    mime_type, _ = mimetypes.guess_type(str(filepath))
    if mime_type:
        return mime_type
    ext = filepath.suffix.lower()
    mime_map = {
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.ttf': 'font/ttf', '.otf': 'font/otf', '.pdf': 'application/pdf',
    }
    return mime_map.get(ext, 'application/octet-stream')


def upload_file(supabase: Client, bucket: str, storage_path: str,
                local_path: Path, dry_run: bool = False) -> bool:
    """Upload a single file to Supabase Storage."""
    if dry_run:
        return True
    try:
        with open(local_path, 'rb') as f:
            supabase.storage.from_(bucket).upload(
                storage_path, f.read(),
                file_options={"content-type": get_mime_type(local_path), "upsert": "true"}
            )
        return True
    except Exception as e:
        if 'already exists' not in str(e).lower():
            print(f"      Error: {e}")
        return 'already exists' in str(e).lower()


def upload_templates(supabase: Client, company: str, dry_run: bool = False) -> int:
    """Upload templates to Asset-Management Storage."""
    print("\n--- Uploading templates to Asset-Management ---")
    templates_dir = TEMPLATES_DIR if TEMPLATES_DIR.exists() else RENDER_TEMPLATES_DIR
    if not templates_dir.exists():
        print("  No templates directory found")
        return 0

    print(f"  Source: {templates_dir}")
    skip_dirs = {'amr', '.DS_Store'}
    uploaded = 0

    for loc_dir in sorted(templates_dir.iterdir()):
        if not loc_dir.is_dir() or loc_dir.name in skip_dirs:
            continue
        for f in loc_dir.iterdir():
            if f.name.startswith('.'):
                continue
            # Asset-Management storage structure: {company}/{location_key}/{filename}
            path = f"{company}/{loc_dir.name}/{f.name}"
            if dry_run:
                print(f"    [DRY RUN] templates/{path}")
            if upload_file(supabase, 'templates', path, f, dry_run):
                uploaded += 1

    print(f"  Uploaded: {uploaded} files")
    return uploaded


def upload_mockups(supabase: Client, company: str, dry_run: bool = False) -> int:
    """Upload mockups to Asset-Management Storage."""
    print("\n--- Uploading mockups to Asset-Management ---")
    mockups_dir = MOCKUPS_DIR if MOCKUPS_DIR.exists() else RENDER_MOCKUPS_DIR
    if not mockups_dir.exists():
        print("  No mockups directory found")
        return 0

    print(f"  Source: {mockups_dir}")
    uploaded = 0

    for loc_dir in sorted(mockups_dir.iterdir()):
        if not loc_dir.is_dir() or loc_dir.name.startswith('.'):
            continue
        for item in loc_dir.rglob('*'):
            if not item.is_file() or item.name.startswith('.'):
                continue
            rel = item.relative_to(loc_dir)
            path = f"{company}/{loc_dir.name}/{rel}"
            if dry_run:
                print(f"    [DRY RUN] mockups/{path}")
            if upload_file(supabase, 'mockups', path, item, dry_run):
                uploaded += 1

    print(f"  Uploaded: {uploaded} files")
    return uploaded


def upload_fonts(supabase: Client, dry_run: bool = False) -> int:
    """Upload fonts to Sales-Module Storage (shared, not per-company)."""
    print("\n--- Uploading fonts to Sales-Module ---")
    if not FONTS_DIR.exists():
        print("  No fonts directory found")
        return 0

    uploaded = 0
    for f in FONTS_DIR.iterdir():
        if f.suffix.lower() in ('.ttf', '.otf', '.woff', '.woff2'):
            path = f"Sofia-Pro/{f.name}"
            if dry_run:
                print(f"    [DRY RUN] fonts/{path}")
            if upload_file(supabase, 'fonts', path, f, dry_run):
                uploaded += 1

    print(f"  Uploaded: {uploaded} files")
    return uploaded


# =============================================================================
# ASSET-MANAGEMENT: SEED LOCATIONS
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

                if key == 'sov':
                    with contextlib.suppress(ValueError):
                        metadata['sov_percent'] = float(value.replace('%', ''))
                elif key == 'upload_fee':
                    with contextlib.suppress(ValueError):
                        metadata['upload_fee'] = float(value.replace(',', ''))
                elif key in ('spot_duration', 'loop_duration', 'number_of_faces'):
                    with contextlib.suppress(ValueError):
                        metadata[key] = int(value)
                elif key == 'display_type':
                    metadata['display_type'] = value.lower()
                elif key in ('location_name', 'display_name'):
                    metadata['display_name'] = value
                elif key in ('series', 'height', 'width', 'city', 'area', 'address'):
                    metadata[key] = value
    except Exception as e:
        print(f"    Error parsing {filepath}: {e}")
    return metadata


def seed_assets_to_asset_mgmt(supabase: Client, dry_run: bool = False) -> int:
    """Seed standalone_assets to Asset-Management Supabase."""
    print("\n" + "=" * 60)
    print("ASSET-MANAGEMENT: Seed Locations")
    print("=" * 60)

    templates_dir = TEMPLATES_DIR if TEMPLATES_DIR.exists() else RENDER_TEMPLATES_DIR
    if not templates_dir.exists():
        print("  ERROR: No templates directory")
        return 0

    print(f"  Source: {templates_dir}")
    skip_dirs = {'intro_outro', 'amr'}
    assets = []

    for mf in sorted(templates_dir.glob('*/metadata.txt')):
        key = mf.parent.name
        if key in skip_dirs:
            continue

        meta = parse_metadata_file(mf)
        display_type = meta.get('display_type', 'digital')
        if display_type not in ('digital', 'static'):
            display_type = 'digital'

        asset = {
            'asset_key': key,
            'display_name': meta.get('display_name', key.replace('_', ' ').title()),
            'display_type': display_type,
            'series': meta.get('series'),
            'height': meta.get('height'),
            'width': meta.get('width'),
            'number_of_faces': meta.get('number_of_faces', 1),
            'spot_duration': meta.get('spot_duration'),
            'loop_duration': meta.get('loop_duration'),
            'sov_percent': meta.get('sov_percent'),
            'upload_fee': meta.get('upload_fee'),
            'city': meta.get('city'),
            'area': meta.get('area'),
            'is_active': True,
            'created_by': 'migration_script',
        }
        asset = {k: v for k, v in asset.items() if v is not None}
        assets.append(asset)
        print(f"    Found: {key} ({asset.get('display_name')})")

    print(f"\n  Total: {len(assets)} assets")

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(assets)} assets")
        return len(assets)

    inserted = batch_insert(supabase, 'standalone_assets', assets,
                           on_conflict='asset_key', dry_run=dry_run)
    print(f"  Inserted: {inserted}")
    return inserted


# =============================================================================
# SALES-MODULE: LOAD SQLITE DATA
# =============================================================================

def load_proposals_log(supabase: Client, conn: sqlite3.Connection,
                       dry_run: bool = False) -> tuple[int, list[dict]]:
    """Load proposals_log to Sales-Module (public schema)."""
    print("\n--- proposals_log ---")
    cursor = conn.execute("SELECT * FROM proposals_log ORDER BY id")
    rows = cursor.fetchall()
    if not rows:
        return 0, []

    records = []
    mapping = []

    for row in rows:
        pkg_type = row['package_type']
        if pkg_type not in ('separate', 'combined'):
            pkg_type = 'separate'

        record = {
            'user_id': row['submitted_by'],
            'submitted_by': row['submitted_by'],
            'client_name': row['client_name'],
            'date_generated': row['date_generated'],
            'package_type': pkg_type,
            'total_amount': row['total_amount'] or '',
            'total_amount_value': parse_amount_text(row['total_amount']),
            'currency': 'AED',
            'proposal_data': {
                'locations_text': row['locations'] or '',
                'migrated_from_sqlite_id': row['id'],
            },
        }
        records.append(record)
        mapping.append({
            'sqlite_id': row['id'],
            'locations_text': row['locations'] or '',
            'total_amount': row['total_amount'],
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        for i, m in enumerate(mapping):
            m['supabase_id'] = i + 1
        return len(records), mapping

    # Insert to public schema
    tbl = supabase.table('proposals_log')
    inserted = 0
    for i, rec in enumerate(records):
        try:
            result = tbl.insert(rec).execute()
            if result.data:
                mapping[i]['supabase_id'] = result.data[0]['id']
                inserted += 1
        except Exception as e:
            print(f"    Error: {e}")
            mapping[i]['supabase_id'] = None

    print(f"  Inserted: {inserted}")
    return inserted, mapping


def load_mockup_frames(supabase: Client, conn: sqlite3.Connection,
                       dry_run: bool = False) -> int:
    """Load mockup_frames to Asset-Management (company schema)."""
    print("\n--- mockup_frames (to Asset-Management) ---")
    cursor = conn.execute("SELECT * FROM mockup_frames ORDER BY id")
    rows = cursor.fetchall()
    if not rows:
        return 0

    valid_tod = {'day', 'night'}
    valid_finish = {'gold', 'silver', 'black'}
    records = []

    for row in rows:
        if row['location_key'] == 'amr':
            continue
        tod = row['time_of_day'] or 'day'
        finish = row['finish'] or 'gold'
        if tod not in valid_tod or finish not in valid_finish:
            continue

        records.append({
            'location_key': row['location_key'],
            'time_of_day': tod,
            'finish': finish,
            'photo_filename': row['photo_filename'],
            'frames_data': parse_json_field(row['frames_data']) or [],
            'created_at': row['created_at'],
            'created_by': row['created_by'],
            'config': parse_json_field(row['config_json']),
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'mockup_frames', records,
                           on_conflict='location_key,time_of_day,finish,photo_filename')
    print(f"  Inserted: {inserted}")
    return inserted


def load_mockup_usage(supabase: Client, conn: sqlite3.Connection,
                      dry_run: bool = False) -> int:
    """Load mockup_usage to Sales-Module (company schema)."""
    print("\n--- mockup_usage ---")
    cursor = conn.execute("SELECT * FROM mockup_usage ORDER BY id")
    rows = cursor.fetchall()
    if not rows:
        return 0

    records = [{
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
    } for row in rows]

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'mockup_usage', records, batch_size=100)
    print(f"  Inserted: {inserted}")
    return inserted


def load_bo_workflows(supabase: Client, conn: sqlite3.Connection,
                      dry_run: bool = False) -> int:
    """Load bo_approval_workflows to Sales-Module (public schema)."""
    print("\n--- bo_approval_workflows ---")
    cursor = conn.execute("SELECT * FROM bo_approval_workflows ORDER BY created_at")
    rows = cursor.fetchall()
    if not rows:
        return 0

    records = []
    for row in rows:
        wf_data = parse_json_field(row['workflow_data']) or {}
        status = wf_data.get('status', 'pending')
        stage = wf_data.get('stage', 'coordinator')

        if status == 'approved':
            status = 'hos_approved' if stage == 'hos' else 'coordinator_approved'
        elif status == 'rejected':
            status = 'hos_rejected' if stage == 'hos' else 'coordinator_rejected'
        elif status not in ('pending', 'cancelled', 'completed',
                           'coordinator_approved', 'coordinator_rejected',
                           'hos_approved', 'hos_rejected'):
            status = 'pending'

        records.append({
            'workflow_id': row['workflow_id'],
            'workflow_data': wf_data,
            'status': status,
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    inserted = batch_insert(supabase, 'bo_approval_workflows', records,
                           on_conflict='workflow_id', schema='public')
    print(f"  Inserted: {inserted}")
    return inserted


def load_ai_costs(supabase: Client, conn: sqlite3.Connection,
                  dry_run: bool = False) -> int:
    """Load ai_costs to Sales-Module (public schema)."""
    print("\n--- ai_costs ---")
    cursor = conn.execute("SELECT * FROM ai_costs ORDER BY id")
    rows = cursor.fetchall()
    if not rows:
        return 0

    valid_types = {'classification', 'parsing', 'coordinator_thread', 'main_llm',
                   'mockup_analysis', 'image_generation', 'bo_edit', 'other'}

    records = []
    for row in rows:
        call_type = row['call_type'] if row['call_type'] in valid_types else 'other'
        records.append({
            'timestamp': row['timestamp'],
            'call_type': call_type,
            'workflow': row['workflow'],
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
            'metadata_json': parse_json_field(row['metadata_json']),
        })

    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} records")
        return len(records)

    # Insert to public schema
    tbl = supabase.table('ai_costs')
    inserted = 0
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        try:
            tbl.insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"    Error: {e}")

    print(f"  Inserted: {inserted}")
    return inserted


def create_proposal_locations(supabase: Client, mapping: list[dict],
                              dry_run: bool = False) -> int:
    """Create proposal_locations entries (public schema, uses location_key)."""
    print("\n--- proposal_locations ---")
    records = []

    for pm in mapping:
        if not pm.get('supabase_id'):
            continue

        locs = [normalize_location_key(l.strip())
                for l in pm.get('locations_text', '').split(',') if l.strip()]
        amounts = re.findall(r'AED\s*([\d,]+)', pm.get('total_amount', ''))
        amounts = [float(a.replace(',', '')) for a in amounts]

        for i, key in enumerate(locs):
            if not key:
                continue
            records.append({
                'proposal_id': pm['supabase_id'],
                'location_key': key,
                'location_company': COMPANY_SCHEMA,
                'location_display_name': key.upper().replace('_', ' '),
                'net_rate': amounts[i] if i < len(amounts) else None,
            })

    if dry_run:
        print(f"  [DRY RUN] Would create {len(records)} entries")
        return len(records)

    tbl = supabase.table('proposal_locations')
    inserted = 0
    for rec in records:
        try:
            tbl.insert(rec).execute()
            inserted += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"    Error: {e}")

    print(f"  Created: {inserted}")
    return inserted


# =============================================================================
# MAIN MIGRATION
# =============================================================================

def run_migration(args: argparse.Namespace):
    """Run the consolidated migration."""
    global COMPANY_SCHEMA
    COMPANY_SCHEMA = args.company

    print("=" * 70)
    print("CONSOLIDATED MIGRATION TO SUPABASE")
    print("=" * 70)
    print(f"Company: {COMPANY_SCHEMA}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Assets Only: {args.assets_only}")
    print(f"Sales Only: {args.sales_only}")
    print(f"Skip Storage: {args.skip_storage}")
    print("=" * 70)

    results = {}
    asset_sb = None
    sales_sb = None

    # =========================================================================
    # ASSET-MANAGEMENT: Locations, Templates, Mockups, Mockup Frames
    # =========================================================================
    if not args.sales_only:
        print("\n" + "=" * 70)
        print("ASSET-MANAGEMENT SUPABASE")
        print("=" * 70)
        try:
            asset_sb = get_asset_mgmt_supabase()

            # Seed locations
            results['assets'] = seed_assets_to_asset_mgmt(asset_sb, args.dry_run)

            # Storage uploads (templates and mockups go to Asset-Management)
            if not args.skip_storage:
                results['templates'] = upload_templates(asset_sb, args.company, args.dry_run)
                results['mockups'] = upload_mockups(asset_sb, args.company, args.dry_run)

            # Mockup frames (from SQLite to Asset-Management)
            print("\n" + "=" * 60)
            print("ASSET-MANAGEMENT: Load Mockup Frames from SQLite")
            print("=" * 60)
            try:
                conn = get_sqlite()
                results['mockup_frames'] = load_mockup_frames(asset_sb, conn, args.dry_run)
                conn.close()
            except FileNotFoundError as e:
                print(f"  SKIPPED: {e}")
                results['mockup_frames'] = 0

        except ValueError as e:
            print(f"  SKIPPED: {e}")
            results['assets'] = 0

    # =========================================================================
    # SALES-MODULE: Proposals, Fonts, Usage Analytics, BOs
    # =========================================================================
    if not args.assets_only:
        print("\n" + "=" * 70)
        print("SALES-MODULE SUPABASE")
        print("=" * 70)
        try:
            sales_sb = get_sales_supabase()

            # Fonts storage (shared, goes to Sales-Module)
            if not args.skip_storage:
                results['fonts'] = upload_fonts(sales_sb, args.dry_run)

            # Database migration
            print("\n" + "=" * 60)
            print("SALES-MODULE: Load SQLite Data")
            print("=" * 60)

            try:
                conn = get_sqlite()
                count, proposal_map = load_proposals_log(sales_sb, conn, args.dry_run)
                results['proposals_log'] = count

                results['mockup_usage'] = load_mockup_usage(sales_sb, conn, args.dry_run)
                results['bo_workflows'] = load_bo_workflows(sales_sb, conn, args.dry_run)
                results['ai_costs'] = load_ai_costs(sales_sb, conn, args.dry_run)
                conn.close()

                # Create proposal_locations
                if proposal_map:
                    results['proposal_locations'] = create_proposal_locations(
                        sales_sb, proposal_map, args.dry_run
                    )
            except FileNotFoundError as e:
                print(f"  SKIPPED: {e}")

        except ValueError as e:
            print(f"  SKIPPED: {e}")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    for key, value in results.items():
        print(f"  {key}: {value}")

    if args.dry_run:
        print("\n[DRY RUN] No data was actually inserted/uploaded.")
    else:
        print("\nMigration complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Consolidated migration to Asset-Management + Sales-Module Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--company", required=True, choices=VALID_COMPANIES,
                       help="Target company schema")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without making changes")
    parser.add_argument("--assets-only", action="store_true",
                       help="Only migrate to Asset-Management (locations)")
    parser.add_argument("--sales-only", action="store_true",
                       help="Only migrate to Sales-Module (proposals, mockups, storage)")
    parser.add_argument("--skip-storage", action="store_true",
                       help="Skip storage uploads")

    args = parser.parse_args()

    if args.assets_only and args.sales_only:
        print("ERROR: Cannot use both --assets-only and --sales-only")
        sys.exit(1)

    try:
        run_migration(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
