#!/usr/bin/env python3
"""
One-time migration script to move existing mockup photos into 'all' subfolder structure.

This script:
1. Finds all photos in /data/mockups/{location}/ (old structure)
2. Moves them to /data/mockups/{location}/all/ (new structure)
3. Updates file paths while preserving database entries
"""

import os
from pathlib import Path
import shutil

# Determine mockups directory
if os.path.exists("/data/"):
    MOCKUPS_DIR = Path("/data/mockups")
else:
    MOCKUPS_DIR = Path(__file__).parent / "data" / "mockups"

print(f"[MIGRATION] Using mockups directory: {MOCKUPS_DIR}")

if not MOCKUPS_DIR.exists():
    print("[MIGRATION] No mockups directory found, nothing to migrate")
    exit(0)

# Track statistics
total_moved = 0
total_skipped = 0
total_errors = 0

# Iterate through location directories
for location_dir in MOCKUPS_DIR.iterdir():
    if not location_dir.is_dir():
        continue

    location_key = location_dir.name
    print(f"\n[MIGRATION] Processing location: {location_key}")

    # Create 'all' subfolder if it doesn't exist
    all_subfolder = location_dir / "all"
    all_subfolder.mkdir(exist_ok=True)

    # Find all image files directly in location directory (old structure)
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    moved_count = 0

    for file_path in location_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            # This is an old-structure photo, move it to 'all' subfolder
            dest_path = all_subfolder / file_path.name

            if dest_path.exists():
                print(f"  [SKIP] {file_path.name} already exists in 'all' subfolder")
                total_skipped += 1
            else:
                try:
                    shutil.move(str(file_path), str(dest_path))
                    print(f"  [MOVED] {file_path.name} -> all/{file_path.name}")
                    moved_count += 1
                    total_moved += 1
                except Exception as e:
                    print(f"  [ERROR] Failed to move {file_path.name}: {e}")
                    total_errors += 1

    if moved_count == 0:
        print(f"  No photos to migrate for {location_key}")

print(f"\n[MIGRATION COMPLETE]")
print(f"  Total moved: {total_moved}")
print(f"  Total skipped: {total_skipped}")
print(f"  Total errors: {total_errors}")
