# Supabase Migration Guide

## Schema Consolidation ✅ COMPLETE

All SQL schema files have been consolidated into a clean structure:

```
db/migrations/
├── ui/
│   ├── 00_reset.sql                 # Drop everything, clean slate
│   └── 01_schema.sql                # Complete UI schema (auth, RBAC, companies, channel identity)
├── salesbot/
│   ├── 00_reset.sql                 # Drop everything, clean slate
│   └── 01_schema.sql                # Multi-schema per-company isolation
└── MIGRATION_GUIDE.md               # This file
```

---

## Architecture Overview

### UI Module (Single Schema)
- User authentication and preferences
- RBAC system (profiles, permissions, teams)
- Companies table with hierarchy
- User-company assignments (many-to-many)
- Channel identity tracking (Slack/Teams)

### Sales Bot (Multi-Schema Per-Company)

```
Sales Bot Database
├── public schema (shared)
│   ├── companies (reference table)
│   ├── get_company_and_children()
│   ├── get_accessible_schemas()
│   └── all_* views (cross-company)
│
├── backlite_dubai schema
│   ├── locations
│   ├── proposals_log
│   ├── booking_orders
│   └── ... (16 tables)
│
├── backlite_uk schema
│   └── ... (same structure)
│
├── backlite_abudhabi schema
│   └── ... (same structure)
│
└── viola schema
    └── ... (same structure)
```

### Storage Structure (Per-Company Folders)

```
Supabase Storage
├── templates/
│   ├── backlite_dubai/
│   │   ├── dubai_gateway/
│   │   │   ├── dubai_gateway.pptx
│   │   │   └── metadata.txt
│   │   └── uae14/
│   │       └── ...
│   ├── backlite_uk/
│   │   └── london_bridge/
│   └── viola/
│       └── ...
│
├── mockups/
│   ├── backlite_dubai/
│   │   └── dubai_gateway/
│   │       ├── day/gold/photo1.jpg
│   │       └── night/gold/photo2.jpg
│   └── ...
│
├── uploads/
│   ├── backlite_dubai/{user_id}/
│   ├── backlite_uk/{user_id}/
│   └── ...
│
├── proposals/
│   ├── backlite_dubai/{user_id}/
│   └── ...
│
└── fonts/
    └── Sofia-Pro/
```

---

## Migration Steps

### Phase 1: Database Setup

#### Step 1.1: UI-Module-Dev Supabase
1. Open Supabase Dashboard → SQL Editor
2. Run `ui/00_reset.sql` (if starting fresh)
3. Run `ui/01_schema.sql`
4. Verify tables created:
   - `users`, `user_preferences`
   - `profiles`, `profile_permissions`
   - `companies`, `user_companies`
   - `channel_identities`, `system_settings`

#### Step 1.2: Sales-Bot-Dev Supabase
1. Open Supabase Dashboard → SQL Editor
2. Run `salesbot/00_reset.sql` (if starting fresh)
3. Run `salesbot/01_schema.sql`
4. Verify schemas created:
   ```sql
   -- Check schemas exist
   SELECT schema_name FROM information_schema.schemata
   WHERE schema_name IN ('backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola');

   -- Check tables in a schema
   SELECT table_name FROM information_schema.tables
   WHERE table_schema = 'backlite_dubai';

   -- Check companies reference
   SELECT * FROM public.companies;
   ```

#### Step 1.3: Repeat for Production
- Run same scripts on UI-Module-Prod
- Run same scripts on Sales-Bot-Prod

---

### Phase 2: Storage Setup

#### Step 2.1: Create Storage Buckets (Sales-Bot-Dev & Prod)

In Supabase Dashboard → Storage → New Bucket:

| Bucket | Public | Description |
|--------|--------|-------------|
| `templates` | No | PPTX templates organized by company |
| `mockups` | No | Background photos organized by company |
| `uploads` | No | User uploads organized by company |
| `proposals` | No | Generated proposals organized by company |
| `fonts` | No | Sofia Pro fonts (shared) |

#### Step 2.2: Upload Files with Company Structure

**Reorganize existing data:**
```
data_backup_prod/data/templates/dubai_gateway/
→ templates/backlite_dubai/dubai_gateway/

data_backup_prod/data/mockups/dubai_gateway/
→ mockups/backlite_dubai/dubai_gateway/
```

**Option A: Manual Upload**
1. Create company folders in each bucket
2. Upload location folders into the appropriate company folder

**Option B: Script Upload (TODO: update script)**
```bash
python db/scripts/upload_storage.py \
  --bucket templates \
  --company backlite_dubai \
  --source data_backup_prod/data/templates
```

---

### Phase 3: Data Migration

#### Step 3.1: Set Environment Variables
```bash
export SALESBOT_DEV_SUPABASE_URL="https://xxx.supabase.co"
export SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY="eyJ..."
```

#### Step 3.2: Update Migration Script

The migration script needs to be updated to use schemas:

```python
# Old: Insert into public.locations
supabase.table('locations').insert(data).execute()

# New: Insert into company schema
supabase.schema('backlite_dubai').table('locations').insert(data).execute()
```

#### Step 3.3: Run Migration
```bash
# Preview
python db/scripts/load_sqlite_backup.py --dry-run --company backlite_dubai

# Execute
python db/scripts/load_sqlite_backup.py --company backlite_dubai
```

This will:
- Insert locations into `backlite_dubai.locations`
- Insert proposals into `backlite_dubai.proposals_log`
- Insert mockup_frames into `backlite_dubai.mockup_frames`
- Insert ai_costs into `backlite_dubai.ai_costs`

---

### Phase 4: Application Updates

#### Step 4.1: Environment Variables (.env)
```env
ENVIRONMENT=development
SALESBOT_DEV_SUPABASE_URL=https://xxx.supabase.co
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
DB_BACKEND=supabase
STORAGE_PROVIDER=supabase
```

#### Step 4.2: API Changes - Schema Selection

All queries must specify the company schema:

```python
# Get user's accessible schemas from UI Supabase
schemas = ui_supabase.rpc('get_accessible_schemas', {'p_company_ids': user_company_ids}).execute()

# Query specific company
locations = salesbot_supabase.schema('backlite_dubai').table('locations').select('*').execute()

# Or use the active company from request header
company_code = request.headers.get('X-Company-Code', 'backlite_dubai')
locations = salesbot_supabase.schema(company_code).table('locations').select('*').execute()
```

#### Step 4.3: API Changes - Cross-Company Queries (MMG users)

```python
# For MMG users who need to see all companies
if user_has_mmg_access:
    # Use cross-schema views
    all_locations = salesbot_supabase.table('all_locations').select('*').execute()
else:
    # Use specific schema
    locations = salesbot_supabase.schema(company_code).table('locations').select('*').execute()
```

#### Step 4.4: Storage Path Updates

```python
# Old
storage_path = f"templates/{location_key}/{location_key}.pptx"

# New
storage_path = f"templates/{company_code}/{location_key}/{location_key}.pptx"
```

#### Step 4.5: Frontend Changes

- Add `X-Company-Code` header to API requests
- Add company switcher UI for multi-company users
- Store active company in localStorage
- Update file upload paths to include company

---

## Company Hierarchy Reference

```
MMG (id=1, is_group=true)
├── Backlite (id=2, is_group=true)
│   ├── Backlite Dubai (id=3, schema=backlite_dubai)
│   ├── Backlite UK (id=4, schema=backlite_uk)
│   └── Backlite Abu Dhabi (id=5, schema=backlite_abudhabi)
└── Viola (id=6, schema=viola)
```

**Access Rules:**
| User Assignment | Accessible Schemas |
|-----------------|-------------------|
| `mmg` | all schemas (via `public.all_*` views) |
| `backlite` | backlite_dubai, backlite_uk, backlite_abudhabi |
| `backlite_dubai` | backlite_dubai only |
| `viola` | viola only |
| `backlite_dubai + viola` | backlite_dubai, viola |

**Get accessible schemas:**
```sql
-- User assigned to backlite group (id=2)
SELECT * FROM public.get_accessible_schemas(ARRAY[2]);
-- Returns: backlite_dubai, backlite_uk, backlite_abudhabi

-- User assigned to MMG (id=1)
SELECT * FROM public.get_accessible_schemas(ARRAY[1]);
-- Returns: backlite_dubai, backlite_uk, backlite_abudhabi, viola
```

---

## Verification Checklist

### After UI Schema
- [ ] `SELECT * FROM companies;` returns 6 companies
- [ ] `SELECT * FROM profiles;` returns default profiles
- [ ] Users table has `primary_company_id` column

### After Sales Bot Schema
- [ ] 4 company schemas exist (backlite_dubai, backlite_uk, backlite_abudhabi, viola)
- [ ] Each schema has 16 tables
- [ ] `public.companies` has 6 records
- [ ] Cross-schema views work: `SELECT * FROM public.all_locations;`

### After Data Migration
- [ ] `SELECT COUNT(*) FROM backlite_dubai.locations;` matches template count
- [ ] `SELECT COUNT(*) FROM backlite_dubai.proposals_log;` = 227
- [ ] `SELECT COUNT(*) FROM backlite_dubai.mockup_frames;` = 69
- [ ] `SELECT COUNT(*) FROM backlite_dubai.ai_costs;` = 915

### After Storage Upload
- [ ] `templates/backlite_dubai/` has location folders
- [ ] `mockups/backlite_dubai/` has background photos
- [ ] `fonts/` has Sofia Pro fonts

---

## Adding a New Company

To add a new company (e.g., "Purple Printing"):

1. **Add to UI Supabase:**
```sql
INSERT INTO companies (code, name, parent_id, country, currency, is_group)
VALUES ('purple_printing', 'Purple Printing', 1, 'UAE', 'AED', false);
```

2. **Create schema in Sales Bot:**
```sql
SELECT public.create_company_schema('purple_printing');
```

3. **Update cross-schema views:**
```sql
-- Add to all_locations view
CREATE OR REPLACE VIEW public.all_locations AS
SELECT 'backlite_dubai' as company_code, l.* FROM backlite_dubai.locations l
UNION ALL
SELECT 'backlite_uk' as company_code, l.* FROM backlite_uk.locations l
UNION ALL
SELECT 'backlite_abudhabi' as company_code, l.* FROM backlite_abudhabi.locations l
UNION ALL
SELECT 'viola' as company_code, l.* FROM viola.locations l
UNION ALL
SELECT 'purple_printing' as company_code, l.* FROM purple_printing.locations l;
-- Repeat for other all_* views
```

4. **Create storage folders:**
   - `templates/purple_printing/`
   - `mockups/purple_printing/`
   - `uploads/purple_printing/`
   - `proposals/purple_printing/`

---

## Rollback

### UI Database
```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
-- Then re-run ui/01_schema.sql
```

### Sales Bot Database
```sql
-- Use the reset script which handles multi-schema
-- Or manually:
DROP SCHEMA IF EXISTS backlite_dubai CASCADE;
DROP SCHEMA IF EXISTS backlite_uk CASCADE;
DROP SCHEMA IF EXISTS backlite_abudhabi CASCADE;
DROP SCHEMA IF EXISTS viola CASCADE;
-- Drop public objects
DROP VIEW IF EXISTS public.all_locations CASCADE;
DROP TABLE IF EXISTS public.companies CASCADE;
-- Then re-run salesbot/01_schema.sql
```

---

## Query Examples

### Single Company Query
```sql
-- Get all digital locations for Backlite Dubai
SELECT * FROM backlite_dubai.locations
WHERE display_type = 'digital' AND is_active = true;

-- Get proposals for a user
SELECT * FROM backlite_dubai.proposals_log
WHERE user_id = 'user-uuid'
ORDER BY date_generated DESC;
```

### Cross-Company Query (MMG Access)
```sql
-- All locations across all companies
SELECT * FROM public.all_locations;

-- All proposals across all companies
SELECT * FROM public.all_proposals
ORDER BY date_generated DESC;

-- AI costs summary by company
SELECT company_code, SUM(total_cost) as total
FROM public.all_ai_costs
GROUP BY company_code;
```

### Check User Access
```sql
-- Get schemas a user can access
SELECT * FROM public.get_accessible_schemas(
  (SELECT ARRAY_AGG(company_id) FROM ui_supabase.user_companies WHERE user_id = 'user-uuid')
);
```
