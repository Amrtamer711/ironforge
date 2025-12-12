#!/usr/bin/env python3
"""
Seed locations from metadata.txt files into the database.

This script reads all metadata.txt files from render_main_data/templates/
and inserts them into the locations table.

Usage:
    python db/scripts/seed_locations.py [--dry-run]
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from supabase import create_client, Client


def parse_metadata_file(filepath: Path) -> Dict[str, Any]:
    """Parse a metadata.txt file into a dictionary."""
    metadata = {}

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
                # Remove % and convert to decimal
                value = value.replace('%', '').strip()
                try:
                    metadata['sov_percent'] = float(value)
                except ValueError:
                    metadata['sov_percent'] = None
            elif key == 'upload_fee':
                try:
                    metadata['upload_fee'] = float(value.replace(',', ''))
                except ValueError:
                    metadata['upload_fee'] = None
            elif key == 'spot_duration':
                try:
                    metadata['spot_duration'] = int(value)
                except ValueError:
                    metadata['spot_duration'] = None
            elif key == 'loop_duration':
                try:
                    metadata['loop_duration'] = int(value)
                except ValueError:
                    metadata['loop_duration'] = None
            elif key == 'number_of_faces':
                try:
                    metadata['number_of_faces'] = int(value)
                except ValueError:
                    metadata['number_of_faces'] = 1
            elif key == 'display_type':
                # Normalize to lowercase
                metadata['display_type'] = value.lower()
            elif key == 'location_name':
                metadata['display_name'] = value
            elif key == 'display_name':
                # Use display_name if location_name not set
                if 'display_name' not in metadata:
                    metadata['display_name'] = value
            elif key == 'series':
                metadata['series'] = value
            elif key == 'height':
                metadata['height'] = value
            elif key == 'width':
                metadata['width'] = value

    return metadata


def get_location_key_from_path(filepath: Path) -> str:
    """Extract location_key from the directory name."""
    return filepath.parent.name


def get_template_path(location_key: str, templates_dir: Path) -> Optional[str]:
    """Find the template file for a location."""
    location_dir = templates_dir / location_key

    # Look for .pptx files
    pptx_files = list(location_dir.glob('*.pptx'))
    if pptx_files:
        # Prefer file matching location_key
        for pptx in pptx_files:
            if pptx.stem == location_key:
                return f"{location_key}/{pptx.name}"
        # Otherwise use first one
        return f"{location_key}/{pptx_files[0].name}"

    return None


def discover_all_locations(templates_dir: Path) -> List[Dict[str, Any]]:
    """Discover all locations from metadata.txt files."""
    locations = []

    metadata_files = list(templates_dir.glob('*/metadata.txt'))

    for metadata_file in sorted(metadata_files):
        location_key = get_location_key_from_path(metadata_file)

        # Skip special directories
        if location_key in ('intro_outro', 'amr', 't3'):
            print(f"  Skipping special directory: {location_key}")
            continue

        metadata = parse_metadata_file(metadata_file)

        # Determine display type (default to digital)
        display_type = metadata.get('display_type', 'digital')
        if display_type not in ('digital', 'static'):
            display_type = 'digital'

        # Build location record
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
            'created_by': 'seed_script',
        }

        locations.append(location)
        print(f"  Found: {location_key} ({location['display_name']})")

    return locations


async def seed_locations(
    supabase_url: str,
    supabase_key: str,
    templates_dir: Path,
    dry_run: bool = False
) -> None:
    """Seed locations into the database."""
    print(f"\n{'='*60}")
    print("LOCATION SEEDING SCRIPT")
    print(f"{'='*60}")
    print(f"Templates directory: {templates_dir}")
    print(f"Dry run: {dry_run}")
    print()

    # Discover locations
    print("Discovering locations...")
    locations = discover_all_locations(templates_dir)
    print(f"\nFound {len(locations)} locations")

    if dry_run:
        print("\n[DRY RUN] Would insert the following locations:")
        for loc in locations:
            print(f"  - {loc['location_key']}: {loc['display_name']} ({loc['display_type']})")
        return

    # Connect to Supabase
    print("\nConnecting to Supabase...")
    supabase: Client = create_client(supabase_url, supabase_key)

    # Insert locations (upsert to handle re-runs)
    print("\nInserting locations...")
    inserted = 0
    updated = 0
    errors = 0

    for location in locations:
        try:
            # Try to upsert (insert or update on conflict)
            result = supabase.table('locations').upsert(
                location,
                on_conflict='location_key'
            ).execute()

            if result.data:
                inserted += 1
                print(f"  ✓ {location['location_key']}")
            else:
                errors += 1
                print(f"  ✗ {location['location_key']}: No data returned")

        except Exception as e:
            errors += 1
            print(f"  ✗ {location['location_key']}: {str(e)}")

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Inserted/Updated: {inserted}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Seed locations from metadata.txt files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be inserted without actually inserting')
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

    # Find templates directory
    project_root = Path(__file__).parent.parent.parent
    templates_dir = project_root / 'render_main_data' / 'templates'

    if not templates_dir.exists():
        print(f"ERROR: Templates directory not found: {templates_dir}")
        sys.exit(1)

    await seed_locations(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        templates_dir=templates_dir,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    asyncio.run(main())
