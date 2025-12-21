# MMG CRM - Environment Configuration

This document describes the three development/deployment environments and how to configure each.

## Environment Overview

| Environment | Hosting | Database | Auth | Storage | Purpose |
|-------------|---------|----------|------|---------|---------|
| **Production** | Render | Prod Supabase | Supabase JWT | Supabase Storage | Live system |
| **Development** | Render | Dev Supabase | Supabase JWT | Supabase Storage | Playground/staging |
| **Local** | Your machine | SQLite or Dev Supabase | Personas or Dev Supabase | Local filesystem | Offline development |

---

## Production Environment

Production is hosted on Render and uses production Supabase instances.

### Configuration

```bash
ENVIRONMENT=production

# UI Supabase (Auth/RBAC)
UI_PROD_SUPABASE_URL=https://xxx.supabase.co
UI_PROD_SUPABASE_ANON_KEY=xxx
UI_PROD_SUPABASE_SERVICE_KEY=xxx

# Sales Supabase (Business Data)
SALESBOT_PROD_SUPABASE_URL=https://xxx.supabase.co
SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY=xxx
```

### Deployment

All services are deployed via `render.yaml` in their respective directories.

---

## Development Environment

Development is hosted on Render as a playground/staging environment.

### Configuration

```bash
ENVIRONMENT=development

# UI Supabase (Auth/RBAC) - Dev instance
UI_DEV_SUPABASE_URL=https://xxx.supabase.co
UI_DEV_SUPABASE_ANON_KEY=xxx
UI_DEV_SUPABASE_SERVICE_ROLE_KEY=xxx

# Sales Supabase (Business Data) - Dev instance
SALESBOT_DEV_SUPABASE_URL=https://xxx.supabase.co
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=xxx
```

### Use Cases

- Testing new features before production
- QA testing
- Demo environment
- Integration testing

---

## Local Environment

Local development runs entirely on your machine. You can choose between two modes:

### Option A: Connected to Dev Supabase

Use the Dev Supabase database but run services locally.

```bash
ENVIRONMENT=local
AUTH_PROVIDER=supabase        # Use Supabase for auth
DB_BACKEND=supabase           # Use Supabase for data

# Dev Supabase credentials (same as Development)
UI_DEV_SUPABASE_URL=...
UI_DEV_SUPABASE_SERVICE_ROLE_KEY=...
SALESBOT_DEV_SUPABASE_URL=...
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=...
```

### Option B: Fully Offline (Recommended)

No network required. Uses SQLite database and local file storage.

```bash
ENVIRONMENT=local
AUTH_PROVIDER=local           # Use test personas for auth
DB_BACKEND=sqlite             # Use SQLite for data
STORAGE_PROVIDER=local        # Use local filesystem for files
```

---

## Setting Up Local Environment

### Quick Setup (Offline Mode)

```bash
# 1. Run the setup script
python src/shared/local_dev/setup_local_env.py

# 2. Copy the generated .env.local to .env
cp .env.local .env

# 3. Start services
python run_all_services.py
```

### Full Setup (With Dev Supabase Sync)

```bash
# 1. Set Dev Supabase credentials
export UI_DEV_SUPABASE_URL=...
export UI_DEV_SUPABASE_SERVICE_ROLE_KEY=...
export SALESBOT_DEV_SUPABASE_URL=...
export SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=...

# 2. Run setup with sync
python src/shared/local_dev/setup_local_env.py --sync

# 3. Copy the generated .env.local to .env
cp .env.local .env

# 4. Start services
python run_all_services.py
```

---

## Local Authentication

When `AUTH_PROVIDER=local`, use test personas for authentication:

### Token Format

```bash
# Using persona ID
curl -H "Authorization: Bearer local-test_admin" http://localhost:3005/api/...

# Using email directly
curl -H "Authorization: Bearer test.admin@mmg.ae" http://localhost:3005/api/...
```

### Available Test Personas

| Persona ID | Email | Profile | Companies |
|------------|-------|---------|-----------|
| `test_admin` | test.admin@mmg.ae | system_admin | All |
| `hos_backlite` | hos.backlite@mmg.ae | sales_manager | Backlite Dubai/UK/Abu Dhabi |
| `hos_viola` | hos.viola@mmg.ae | sales_manager | Viola |
| `rep_dubai_1` | rep.dubai1@mmg.ae | sales_rep | Backlite Dubai |
| `rep_dubai_2` | rep.dubai2@mmg.ae | sales_rep | Backlite Dubai |
| `rep_uk_1` | rep.uk1@mmg.ae | sales_rep | Backlite UK |
| `rep_abudhabi_1` | rep.abudhabi1@mmg.ae | sales_rep | Backlite Abu Dhabi |
| `rep_viola_1` | rep.viola1@mmg.ae | sales_rep | Viola |
| `coordinator_1` | coordinator1@mmg.ae | coordinator | All |
| `finance_1` | finance1@mmg.ae | finance | All |
| `viewer_only` | viewer@mmg.ae | viewer | All |

### Dev Panel UI

Access the browser-based testing UI at:
```
http://localhost:3005/dev-panel.html
```

Features:
- One-click user switching
- View full RBAC context
- Quick persona search
- Copy auth headers for curl

---

## Directory Structure

```
data/
├── local/                    # SQLite databases
│   ├── ui.db                 # Auth/RBAC data
│   └── sales.db              # Business data
└── storage/                  # Local file storage
    ├── proposals/
    ├── mockups/
    ├── uploads/
    ├── templates/
    └── documents/
```

---

## Syncing Data

To sync the latest data from Dev Supabase to local SQLite:

```bash
# Sync all database tables
python src/shared/local_dev/sync_from_supabase.py

# Preview without changes
python src/shared/local_dev/sync_from_supabase.py --dry-run

# Clear and re-sync
python src/shared/local_dev/sync_from_supabase.py --clear

# Sync specific tables
python src/shared/local_dev/sync_from_supabase.py --tables users,profiles

# Sync specific company schema
python src/shared/local_dev/sync_from_supabase.py --schema backlite_dubai
```

---

## Syncing File Storage

To sync files from Supabase Storage buckets to local filesystem:

```bash
# Sync databases AND file storage
python src/shared/local_dev/sync_from_supabase.py --storage

# Sync ONLY file storage (skip databases)
python src/shared/local_dev/sync_from_supabase.py --storage-only

# Sync specific buckets only
python src/shared/local_dev/sync_from_supabase.py --storage --buckets proposals,mockups

# Sync from specific projects (sales, assets, ui, security)
python src/shared/local_dev/sync_from_supabase.py --storage --projects sales,assets

# Preview storage sync (dry run)
python src/shared/local_dev/sync_from_supabase.py --storage-only --dry-run

# Clear and re-sync storage
python src/shared/local_dev/sync_from_supabase.py --storage-only --clear
```

### Storage Buckets by Project

| Project | Buckets | Local Folder |
|---------|---------|--------------|
| **Sales** | proposals, mockups, documents, templates, uploads | data/storage/{bucket}/ |
| **Assets** | location-images, network-assets | data/storage/{bucket}/ |
| **UI** | avatars | data/storage/avatars/ |
| **Security** | audit-exports | data/storage/audit-exports/ |

### Using Setup Script

```bash
# Setup with database sync only
python src/shared/local_dev/setup_local_env.py --sync

# Setup with database AND storage sync
python src/shared/local_dev/setup_local_env.py --sync-all

# Setup with storage sync only
python src/shared/local_dev/setup_local_env.py --sync-storage
```

---

## Environment Variables Reference

### Core Settings

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `ENVIRONMENT` | `local`, `development`, `production` | `local` | Deployment environment |
| `AUTH_PROVIDER` | `supabase`, `local` | `supabase` | Authentication provider |
| `DB_BACKEND` | `supabase`, `sqlite` | `supabase` | Database backend |
| `STORAGE_PROVIDER` | `supabase`, `local` | `supabase` | File storage provider |

### Local Mode Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_DB_PATH` | `data/local/ui.db` | SQLite database path |
| `LOCAL_STORAGE_PATH` | `data/storage/` | Local file storage path |

### Service Ports

| Variable | Default | Description |
|----------|---------|-------------|
| `UI_PORT` | `3005` | Unified UI gateway port |
| `SALES_MODULE_PORT` | `8000` | Sales module port |
| `ASSET_MGMT_PORT` | `8001` | Asset management port |

---

## Troubleshooting

### "Supabase not configured"

**In local mode**: Set `AUTH_PROVIDER=local` to use test personas instead of Supabase.

**In dev mode**: Ensure Dev Supabase credentials are set in environment.

### "Database not found"

Run the sync script to create local databases:
```bash
python src/shared/local_dev/sync_from_supabase.py
```

Or run setup with `--sync` flag:
```bash
python src/shared/local_dev/setup_local_env.py --sync
```

### "personas.yaml not found"

The personas file should be at `src/shared/testing/personas.yaml`. Run setup:
```bash
python src/shared/local_dev/setup_local_env.py
```

### Checking Setup Status

```bash
python src/shared/local_dev/setup_local_env.py --check
```

---

## Quick Reference Card

```bash
# OFFLINE DEVELOPMENT
export ENVIRONMENT=local
export AUTH_PROVIDER=local
export DB_BACKEND=sqlite
export STORAGE_PROVIDER=local

# Test as admin
curl -H "Authorization: Bearer local-test_admin" http://localhost:3005/api/sales/...

# Test as sales rep
curl -H "Authorization: Bearer local-rep_dubai_1" http://localhost:3005/api/sales/...

# Sync latest data
python src/shared/local_dev/sync_from_supabase.py

# Open dev panel
open http://localhost:3005/dev-panel.html
```
