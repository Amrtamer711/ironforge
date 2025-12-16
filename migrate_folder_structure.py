#!/usr/bin/env python3
"""
Migration script to reorganize billboard mockup photos from old flat structure to new hierarchical structure.

Old structure:
  location/
    ├── gold/
    ├── silver/
    ├── night/
    └── day/

New structure:
  location/
    ├── all/              # Contains all photos regardless of time/finish
    ├── day/
    │   ├── gold/
    │   └── silver/
    └── night/
        ├── gold/
        └── silver/

Migration logic:
  - gold/ photos → day/gold/ + all/
  - silver/ photos → day/silver/ + all/
  - night/ photos → night/gold/ + all/  (assuming night was gold finish)
  - day/ photos → day/gold/ + all/  (assuming day was gold finish)
"""

import shutil
from pathlib import Path

# Mapping from old subfolder to new (time_of_day, finish)
MIGRATION_MAP = {
    'gold': ('day', 'gold'),
    'silver': ('day', 'silver'),
    'night': ('night', 'gold'),  # Assume night was gold finish
    'day': ('day', 'gold'),      # Assume day was gold finish
}

def migrate_location(location_key: str, mockups_dir: Path, dry_run: bool = True):
    """Migrate a single location's folder structure"""
    location_path = mockups_dir / location_key

    if not location_path.exists():
        print(f"⏭️  Skipping {location_key} - directory doesn't exist")
        return

    print(f"\n{'[DRY RUN] ' if dry_run else ''}📍 Migrating location: {location_key}")

    # Check if already migrated (has day/ or night/ folders)
    if (location_path / 'day').exists() or (location_path / 'night').exists():
        print("  ✅ Already migrated (has day/ or night/ folders)")
        return

    # Create all/ folder for all photos
    all_folder = location_path / 'all'
    if not dry_run:
        all_folder.mkdir(exist_ok=True)

    # Track which photos we've seen
    all_photos_copied = 0

    # Process each old subfolder
    for old_subfolder, (time_of_day, finish) in MIGRATION_MAP.items():
        old_folder = location_path / old_subfolder

        if not old_folder.exists() or not old_folder.is_dir():
            continue

        # List all photos in old folder
        photos = list(old_folder.glob('*.jpg')) + list(old_folder.glob('*.jpeg')) + list(old_folder.glob('*.png'))

        if not photos:
            print(f"  ⏭️  {old_subfolder}/ - empty, skipping")
            continue

        print(f"  📁 {old_subfolder}/ ({len(photos)} photos) → {time_of_day}/{finish}/ + all/")

        # Create new folder structure
        new_folder = location_path / time_of_day / finish
        if not dry_run:
            new_folder.mkdir(parents=True, exist_ok=True)

        # Move photos to new location and copy to all/
        for photo in photos:
            new_photo_path = new_folder / photo.name
            all_photo_path = all_folder / photo.name

            if dry_run:
                print(f"    • {photo.name} → {time_of_day}/{finish}/")
            else:
                # Copy to time_of_day/finish/ folder
                shutil.copy2(photo, new_photo_path)

                # Copy to all/ folder (if not already there)
                if not all_photo_path.exists():
                    shutil.copy2(photo, all_photo_path)
                    all_photos_copied += 1

        # Remove old folder after migration
        if not dry_run:
            shutil.rmtree(old_folder)
            print(f"    ✅ Migrated {len(photos)} photos, removed old {old_subfolder}/ folder")

    if all_photos_copied > 0:
        print(f"  📦 Copied {all_photos_copied} unique photos to all/")


def main():
    """Run migration for all locations"""
    import argparse

    parser = argparse.ArgumentParser(description='Migrate billboard mockup folder structure')
    parser.add_argument('--execute', action='store_true', help='Actually perform migration (default is dry-run)')
    parser.add_argument('--location', type=str, help='Migrate specific location only')
    args = parser.parse_args()

    dry_run = not args.execute

    # Get mockups directory from config
    from mockup_generator import MOCKUPS_DIR

    print("=" * 70)
    print("BILLBOARD MOCKUP FOLDER STRUCTURE MIGRATION")
    print("=" * 70)

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("   Run with --execute to actually perform migration\n")
    else:
        print("\n🚀 EXECUTING MIGRATION - Files will be moved!\n")

    # Get all locations
    if args.location:
        locations = [args.location]
        print(f"Migrating single location: {args.location}")
    else:
        locations = [d.name for d in MOCKUPS_DIR.iterdir() if d.is_dir()]
        print(f"Found {len(locations)} locations to check")

    # Migrate each location
    migrated_count = 0
    skipped_count = 0

    for location_key in sorted(locations):
        try:
            result = migrate_location(location_key, MOCKUPS_DIR, dry_run=dry_run)
            if result is False:
                skipped_count += 1
            else:
                migrated_count += 1
        except Exception as e:
            print(f"\n❌ Error migrating {location_key}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)

    if dry_run:
        print("✅ Dry run completed - no changes made")
        print("   Run with --execute to perform actual migration")
    else:
        print("✅ Migration completed!")
        print(f"   Processed {len(locations)} locations")

    print("\nNext steps:")
    print("1. Verify the new folder structure looks correct")
    print("2. Restart the server to pick up changes")
    print("3. Test mockup generation with different variations")
    print("4. Database migration will happen automatically on next server start")


if __name__ == '__main__':
    main()
