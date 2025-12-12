# SalesBot Database Migrations

## Schema Overview

The SalesBot database uses a **location-centric design** where the `locations` table is the foundation that all other entities link to.

### Schema Files

| File | Purpose |
|------|---------|
| `salesbot_schema.sql` | Original V1 schema (deprecated) |
| `salesbot_schema_v2.sql` | **Current** location-centric schema |
| `v1_to_v2_migration.sql` | Migration script from V1 to V2 |
| `ui_schema.sql` | UI Supabase schema (auth/RBAC) |

## V2 Schema Architecture

```
locations (The Foundation)
├── mockup_frames → location_id FK
├── mockup_usage → location_id FK
├── proposal_locations (junction) → proposal_id + location_id
├── bo_locations (junction) → bo_id + location_id
├── location_occupations (inventory) → location_id
├── rate_cards (pricing) → location_id
└── location_photos → location_id

File Storage Tables:
├── documents (BO uploads, general files)
├── mockup_files (generated mockups)
└── proposal_files (generated PPTX files)
```

## Migration Guide

### Prerequisites

1. Access to Supabase project
2. Environment variables set:
   - `SALESBOT_SUPABASE_URL`
   - `SALESBOT_SUPABASE_KEY` (service role key)

### Migration Steps

#### Step 1: Backup (Recommended)

```bash
# Export current data from Supabase
# Use Supabase Dashboard > Database > Backups
```

#### Step 2: Run Migration SQL

The migration is **ADDITIVE ONLY** - it does NOT delete any data:
- All existing tables are preserved
- New columns are added with `IF NOT EXISTS`
- New tables are created with `IF NOT EXISTS`
- No `DROP TABLE` or `DELETE` statements

```sql
-- Run in Supabase SQL Editor
-- Copy contents of v1_to_v2_migration.sql
```

#### Step 3: Seed Locations

Populate the `locations` table from metadata.txt files:

```bash
cd /path/to/project

# Dry run first (shows what would be inserted)
python db/scripts/seed_locations.py --dry-run

# Actually seed the data
python db/scripts/seed_locations.py
```

#### Step 4: Migrate Existing Data

Link existing proposals and booking orders to the new junction tables:

```bash
# Dry run first
python db/scripts/migrate_existing_data.py --dry-run

# Actually migrate
python db/scripts/migrate_existing_data.py
```

### What Gets Migrated

| Source | Target | Action |
|--------|--------|--------|
| `metadata.txt` files | `locations` | Seeded from templates directory |
| `mockup_frames.location_key` | `mockup_frames.location_id` | FK added |
| `mockup_usage.location_key` | `mockup_usage.location_id` | FK added |
| `proposals_log.locations` (TEXT) | `proposal_locations` | Junction table populated |
| `booking_orders.locations_json` | `bo_locations` | Junction table populated |

### New Tables Created

1. **`locations`** - Central location inventory
2. **`proposal_locations`** - Many-to-many proposal↔location
3. **`bo_locations`** - Many-to-many BO↔location
4. **`location_occupations`** - Inventory/availability tracking
5. **`rate_cards`** - Location pricing by period
6. **`documents`** - File registry for BO uploads
7. **`mockup_files`** - Generated mockup images
8. **`proposal_files`** - Generated PPTX files
9. **`location_photos`** - Background photos for mockups

### New Views Created

- `digital_locations` - Active digital locations
- `static_locations` - Active static locations
- `digital_locations_with_rates` - Locations + current rate card
- `static_locations_with_rates` - Static locations + current rate card
- `location_availability` - What's booked and when
- `proposals_summary` - Proposals with location details
- `booking_orders_summary` - BOs with location details

## File Storage Architecture

Files are stored separately from the database:

| File Type | Storage Location | Database Table |
|-----------|------------------|----------------|
| BO Documents | `/data/storage/uploads/` or Supabase Storage | `documents` |
| Mockup Images | `/data/mockups/` | `mockup_files` |
| Proposal PPTX | `/data/storage/proposals/` or Supabase Storage | `proposal_files` |
| Location Photos | `/data/mockups/{location}/` | `location_photos` |

Storage provider is configurable via `STORAGE_PROVIDER` env var:
- `local` - Local filesystem (development)
- `supabase` - Supabase Storage (production)
- `s3` - AWS S3 (optional)

## Rollback

Since the migration is additive-only, rollback is simple:
1. New tables can be dropped if needed (no data loss)
2. New columns can be dropped (original columns preserved)
3. Original `locations` TEXT field in `proposals_log` is preserved

```sql
-- To rollback (if needed):
-- DROP TABLE IF EXISTS location_photos;
-- DROP TABLE IF EXISTS proposal_files;
-- DROP TABLE IF EXISTS mockup_files;
-- DROP TABLE IF EXISTS documents;
-- DROP TABLE IF EXISTS rate_cards;
-- DROP TABLE IF EXISTS location_occupations;
-- DROP TABLE IF EXISTS bo_locations;
-- DROP TABLE IF EXISTS proposal_locations;
-- DROP TABLE IF EXISTS locations;
```

## Troubleshooting

### "btree_gist extension not found"

The `location_occupations` table uses a GIST exclusion constraint to prevent double bookings. If you get an error:

```sql
-- Enable the extension first
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

### "Permission denied"

Ensure you're using the service role key, not the anon key.

### "location_key not found"

Some location keys in existing data may not match the metadata.txt files. The migration scripts handle this gracefully by:
- Setting `location_id` to NULL if not found
- Preserving the original `location_key` for historical records

## Support

For issues, check the project's main README or open an issue in the repository.
