#!/usr/bin/env python3
"""
Migrate existing data to location-centric schema.

This script:
1. Links mockup_frames and mockup_usage to locations table
2. Extracts location data from proposals_log.locations (TEXT) → proposal_locations
3. Extracts location data from booking_orders.locations_json → bo_locations

Usage:
    python db/scripts/migrate_existing_data.py [--dry-run]
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from supabase import create_client, Client


def normalize_location_key(text: str) -> str:
    """Normalize text to a location_key format."""
    # Remove common prefixes
    text = re.sub(r'^(the\s+)', '', text, flags=re.IGNORECASE)

    # Convert to lowercase, replace spaces with underscores
    key = text.lower().strip()
    key = re.sub(r'[^a-z0-9]+', '_', key)
    key = key.strip('_')

    return key


def extract_locations_from_text(locations_text: str) -> List[str]:
    """Extract location keys from a comma-separated text field."""
    if not locations_text:
        return []

    # Split by comma or newline
    parts = re.split(r'[,\n]+', locations_text)

    location_keys = []
    for part in parts:
        part = part.strip()
        if part:
            key = normalize_location_key(part)
            if key:
                location_keys.append(key)

    return location_keys


def extract_locations_from_json(locations_json: Any) -> List[Dict[str, Any]]:
    """Extract location data from a JSON field."""
    if not locations_json:
        return []

    # Parse if string
    if isinstance(locations_json, str):
        try:
            locations_json = json.loads(locations_json)
        except json.JSONDecodeError:
            return []

    if not isinstance(locations_json, list):
        return []

    locations = []
    for item in locations_json:
        if isinstance(item, dict):
            # Extract location info
            location_data = {
                'location_key': None,
                'raw_location_text': None,
                'start_date': None,
                'end_date': None,
                'net_rate': None,
            }

            # Try to find location identifier
            for key in ('location_key', 'location', 'asset', 'name', 'site'):
                if key in item and item[key]:
                    location_data['raw_location_text'] = str(item[key])
                    location_data['location_key'] = normalize_location_key(str(item[key]))
                    break

            # Extract dates
            for key in ('start_date', 'startDate', 'start'):
                if key in item and item[key]:
                    location_data['start_date'] = str(item[key])[:10]  # Just date part
                    break

            for key in ('end_date', 'endDate', 'end'):
                if key in item and item[key]:
                    location_data['end_date'] = str(item[key])[:10]
                    break

            # Extract rate
            for key in ('net_rate', 'netRate', 'rate', 'amount'):
                if key in item and item[key]:
                    try:
                        location_data['net_rate'] = float(str(item[key]).replace(',', ''))
                    except ValueError:
                        pass
                    break

            if location_data['location_key']:
                locations.append(location_data)

        elif isinstance(item, str):
            # Simple string entry
            key = normalize_location_key(item)
            if key:
                locations.append({
                    'location_key': key,
                    'raw_location_text': item,
                })

    return locations


async def migrate_mockups(supabase: Client, location_map: Dict[str, int], dry_run: bool) -> Dict[str, int]:
    """Link mockup tables to locations."""
    stats = {'frames_updated': 0, 'usage_updated': 0, 'frames_errors': 0, 'usage_errors': 0}

    print("\n--- Migrating Mockup Frames ---")

    # Get all mockup_frames without location_id
    result = supabase.table('mockup_frames').select('id, location_key').is_('location_id', 'null').execute()

    for frame in result.data or []:
        location_key = frame.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if dry_run:
                print(f"  [DRY RUN] Would update frame {frame['id']} → location_id {location_id}")
            else:
                try:
                    supabase.table('mockup_frames').update({'location_id': location_id}).eq('id', frame['id']).execute()
                    stats['frames_updated'] += 1
                except Exception as e:
                    print(f"  ✗ Frame {frame['id']}: {e}")
                    stats['frames_errors'] += 1
        else:
            print(f"  ? Frame {frame['id']}: Unknown location_key '{location_key}'")

    print("\n--- Migrating Mockup Usage ---")

    # Get all mockup_usage without location_id
    result = supabase.table('mockup_usage').select('id, location_key').is_('location_id', 'null').execute()

    for usage in result.data or []:
        location_key = usage.get('location_key')
        location_id = location_map.get(location_key)

        if location_id:
            if dry_run:
                print(f"  [DRY RUN] Would update usage {usage['id']} → location_id {location_id}")
            else:
                try:
                    supabase.table('mockup_usage').update({'location_id': location_id}).eq('id', usage['id']).execute()
                    stats['usage_updated'] += 1
                except Exception as e:
                    print(f"  ✗ Usage {usage['id']}: {e}")
                    stats['usage_errors'] += 1

    return stats


async def migrate_proposals(supabase: Client, location_map: Dict[str, int], dry_run: bool) -> Dict[str, int]:
    """Migrate proposals_log.locations to proposal_locations table."""
    stats = {'proposals_processed': 0, 'locations_created': 0, 'errors': 0}

    print("\n--- Migrating Proposals ---")

    # Get all proposals
    result = supabase.table('proposals_log').select('id, locations, proposal_data').execute()

    for proposal in result.data or []:
        proposal_id = proposal['id']
        stats['proposals_processed'] += 1

        # Try to extract locations from proposal_data first (more structured)
        proposal_data = proposal.get('proposal_data')
        locations_text = proposal.get('locations', '')

        location_keys = []

        # Try proposal_data.locations first
        if proposal_data:
            if isinstance(proposal_data, str):
                try:
                    proposal_data = json.loads(proposal_data)
                except:
                    proposal_data = None

            if proposal_data and 'locations' in proposal_data:
                pd_locations = proposal_data['locations']
                if isinstance(pd_locations, list):
                    for loc in pd_locations:
                        if isinstance(loc, dict):
                            for key in ('location_key', 'key', 'name'):
                                if key in loc:
                                    location_keys.append({
                                        'key': normalize_location_key(str(loc[key])),
                                        'display_name': loc.get('display_name') or loc.get('name'),
                                        'start_date': loc.get('start_date'),
                                        'duration_weeks': loc.get('duration_weeks') or loc.get('weeks'),
                                        'net_rate': loc.get('net_rate') or loc.get('rate'),
                                        'upload_fee': loc.get('upload_fee'),
                                    })
                                    break
                        elif isinstance(loc, str):
                            location_keys.append({'key': normalize_location_key(loc)})

        # Fallback to locations text field
        if not location_keys and locations_text:
            for key in extract_locations_from_text(locations_text):
                location_keys.append({'key': key})

        # Insert into proposal_locations
        for loc_data in location_keys:
            location_key = loc_data.get('key')
            if not location_key:
                continue

            location_id = location_map.get(location_key)

            record = {
                'proposal_id': proposal_id,
                'location_key': location_key,
                'location_id': location_id,
                'location_display_name': loc_data.get('display_name'),
                'start_date': loc_data.get('start_date'),
                'duration_weeks': loc_data.get('duration_weeks'),
                'net_rate': loc_data.get('net_rate'),
                'upload_fee': loc_data.get('upload_fee'),
            }

            # Remove None values
            record = {k: v for k, v in record.items() if v is not None}

            if dry_run:
                print(f"  [DRY RUN] Proposal {proposal_id} → {location_key}")
            else:
                try:
                    # Upsert to handle re-runs
                    supabase.table('proposal_locations').upsert(
                        record,
                        on_conflict='proposal_id,location_key'
                    ).execute()
                    stats['locations_created'] += 1
                except Exception as e:
                    print(f"  ✗ Proposal {proposal_id} / {location_key}: {e}")
                    stats['errors'] += 1

    return stats


async def migrate_booking_orders(supabase: Client, location_map: Dict[str, int], dry_run: bool) -> Dict[str, int]:
    """Migrate booking_orders.locations_json to bo_locations table."""
    stats = {'bos_processed': 0, 'locations_created': 0, 'errors': 0}

    print("\n--- Migrating Booking Orders ---")

    # Get all booking orders with locations_json
    result = supabase.table('booking_orders').select('id, locations_json, asset').execute()

    for bo in result.data or []:
        bo_id = bo['id']
        stats['bos_processed'] += 1

        locations_json = bo.get('locations_json')
        locations = extract_locations_from_json(locations_json)

        # If no locations in JSON, try to use asset field
        if not locations and bo.get('asset'):
            key = normalize_location_key(bo['asset'])
            if key:
                locations = [{'location_key': key, 'raw_location_text': bo['asset']}]

        for loc_data in locations:
            location_key = loc_data.get('location_key')
            if not location_key:
                continue

            location_id = location_map.get(location_key)

            record = {
                'bo_id': bo_id,
                'location_key': location_key,
                'location_id': location_id,
                'start_date': loc_data.get('start_date'),
                'end_date': loc_data.get('end_date'),
                'net_rate': loc_data.get('net_rate'),
                'raw_location_text': loc_data.get('raw_location_text'),
            }

            # Remove None values
            record = {k: v for k, v in record.items() if v is not None}

            if dry_run:
                print(f"  [DRY RUN] BO {bo_id} → {location_key}")
            else:
                try:
                    supabase.table('bo_locations').insert(record).execute()
                    stats['locations_created'] += 1
                except Exception as e:
                    # Might be duplicate
                    if 'duplicate' not in str(e).lower():
                        print(f"  ✗ BO {bo_id} / {location_key}: {e}")
                        stats['errors'] += 1

    return stats


async def run_migration(
    supabase_url: str,
    supabase_key: str,
    dry_run: bool = False
) -> None:
    """Run the full migration."""
    print(f"\n{'='*60}")
    print("DATA MIGRATION SCRIPT (V1 → V2)")
    print(f"{'='*60}")
    print(f"Dry run: {dry_run}")
    print()

    # Connect to Supabase
    print("Connecting to Supabase...")
    supabase: Client = create_client(supabase_url, supabase_key)

    # Build location_key → id map
    print("\nBuilding location map...")
    result = supabase.table('locations').select('id, location_key').execute()

    location_map: Dict[str, int] = {}
    for loc in result.data or []:
        location_map[loc['location_key']] = loc['id']

    print(f"  Found {len(location_map)} locations in database")

    if not location_map:
        print("\nERROR: No locations found. Run seed_locations.py first!")
        return

    # Run migrations
    mockup_stats = await migrate_mockups(supabase, location_map, dry_run)
    proposal_stats = await migrate_proposals(supabase, location_map, dry_run)
    bo_stats = await migrate_booking_orders(supabase, location_map, dry_run)

    # Print summary
    print(f"\n{'='*60}")
    print("MIGRATION RESULTS:")
    print(f"{'='*60}")
    print(f"\nMockups:")
    print(f"  Frames updated: {mockup_stats['frames_updated']}")
    print(f"  Usage updated: {mockup_stats['usage_updated']}")
    print(f"  Errors: {mockup_stats['frames_errors'] + mockup_stats['usage_errors']}")
    print(f"\nProposals:")
    print(f"  Proposals processed: {proposal_stats['proposals_processed']}")
    print(f"  Location links created: {proposal_stats['locations_created']}")
    print(f"  Errors: {proposal_stats['errors']}")
    print(f"\nBooking Orders:")
    print(f"  BOs processed: {bo_stats['bos_processed']}")
    print(f"  Location links created: {bo_stats['locations_created']}")
    print(f"  Errors: {bo_stats['errors']}")
    print(f"{'='*60}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Migrate existing data to location-centric schema')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without actually doing it')
    parser.add_argument('--supabase-url', help='Supabase URL (or set SALESBOT_SUPABASE_URL env var)')
    parser.add_argument('--supabase-key', help='Supabase service key (or set SALESBOT_SUPABASE_KEY env var)')
    args = parser.parse_args()

    # Get Supabase credentials
    supabase_url = args.supabase_url or os.environ.get('SALESBOT_SUPABASE_URL')
    supabase_key = args.supabase_key or os.environ.get('SALESBOT_SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        print("ERROR: Supabase credentials required.")
        print("Set SALESBOT_SUPABASE_URL and SALESBOT_SUPABASE_KEY environment variables")
        print("Or pass --supabase-url and --supabase-key arguments")
        sys.exit(1)

    await run_migration(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    asyncio.run(main())
