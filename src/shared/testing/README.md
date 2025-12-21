# MMG Testing Framework

Comprehensive testing setup for RBAC, user context switching, and permission testing.

## Quick Start

### 1. Setup Test Users (One Time)

```bash
# Navigate to testing directory
cd src/shared/testing

# View setup instructions
python cli.py setup

# Or run SQL files manually in Supabase SQL Editor:
# 1. sql/001_seed_profiles.sql
# 2. sql/002_seed_companies_teams.sql
# 3. sql/003_seed_test_users.sql
```

### 2. Use the Dev Panel (Browser)

Open in your browser while running locally:
```
http://localhost:3005/dev-panel.html
```

Features:
- See all test personas
- One-click user switching
- View current RBAC context
- Copy login credentials

### 3. Use the CLI (Terminal)

```bash
# List all personas
python cli.py list

# Get login credentials
python cli.py login rep_dubai_1

# Get JWT token for API testing
python cli.py token hos_backlite

# Get curl headers
python cli.py headers viewer_only
```

## Test Personas

| Persona | Profile | Companies | Use For |
|---------|---------|-----------|---------|
| `test_admin` | system_admin | All | Testing admin features |
| `hos_backlite` | sales_manager | Backlite Dubai/UK/AbuDhabi | BO approvals, team view |
| `hos_viola` | sales_manager | Viola | Separate approval chain |
| `rep_dubai_1` | sales_rep | Backlite Dubai | Standard sales flow |
| `rep_dubai_2` | sales_rep | Backlite Dubai | Sharing tests |
| `rep_uk_1` | sales_rep | Backlite UK | GBP currency |
| `rep_multi_company` | sales_rep | Dubai + Viola | Multi-tenant |
| `coordinator_1` | coordinator | All | BO processing |
| `finance_1` | finance | All | Final approvals |
| `viewer_only` | viewer | Dubai | Read-only testing |
| `no_permissions` | None | Dubai | Auth != Authz |
| `no_company` | sales_rep | None | Empty data |
| `wrong_company` | sales_rep | Viola | Cross-company denial |

**Password for all test users:** `TestUser123!`

## Seeded Test Data

When you run the seed scripts, you get pre-populated business data:

### Proposals

| ID | Owner | Client | Status | Amount |
|----|-------|--------|--------|--------|
| 1 | rep_dubai_1 | Emirates NBD | Draft | 165,000 AED |
| 2 | rep_dubai_1 | Etisalat | Submitted | 312,000 AED |
| 3 | rep_dubai_2 | Majid Al Futtaim | Approved | 88,000 AED |
| 4 | rep_dubai_1 | Noon | Submitted (large) | 520,000 AED |
| 5 | rep_multi_company | Al Futtaim | Draft | 250,000 AED |

### Booking Orders

| BO Ref | Owner | Client | Approval Status |
|--------|-------|--------|-----------------|
| BO-2025-001 | rep_dubai_1 | Emirates NBD | Pending Coordinator |
| BO-2025-002 | rep_dubai_1 | Etisalat | Pending HOS |
| BO-2025-003 | rep_dubai_2 | Majid Al Futtaim | Pending Finance |
| BO-2025-004 | rep_dubai_1 | Unknown | Rejected |

### Locations (backlite_dubai)

| Key | Name | Network | Rate/Week |
|-----|------|---------|-----------|
| SZR-001 | Sheikh Zayed Road - Interchange 1 | Digital | 15,000 AED |
| SZR-002 | Sheikh Zayed Road - Mall of Emirates | Digital | 18,000 AED |
| MARINA-001 | Dubai Marina - JBR Walk | Digital | 12,000 AED |
| DOWNTOWN-001 | Downtown - Burj Khalifa | Static | 22,000 AED |
| DXB-T1-001 | DXB Terminal 1 - Arrivals | Airport | 35,000 AED |
| DXB-T3-001 | DXB Terminal 3 - Concourse A | Airport | 38,000 AED |

## Test Scenarios

### Basic Sales Flow
```
rep_dubai_1 → coordinator_1 → hos_backlite → finance_1
```

### Multi-Company Testing
```
rep_dubai_1 (sees Dubai only)
rep_viola_1 (sees Viola only)
rep_multi_company (sees both, isolated)
```

### Permission Enforcement
```
viewer_only: Can view, cannot create
no_permissions: Blocked everywhere
wrong_company: Cannot access Dubai data
```

## API Endpoints (Dev Panel)

All endpoints are prefixed with `/api/dev/` and only work in development:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dev/status` | GET | Check if dev panel is enabled |
| `/api/dev/personas` | GET | List all test personas |
| `/api/dev/personas/{id}` | GET | Get specific persona |
| `/api/dev/scenarios` | GET | List test scenarios |
| `/api/dev/context` | GET | Current RBAC context |
| `/api/dev/impersonate` | POST | Switch to a persona |
| `/api/dev/stop-impersonation` | POST | Return to real user |
| `/api/dev/permissions` | GET | List all permissions |
| `/api/dev/quick-switch` | GET | Grouped personas for quick access |

## File Structure

```
src/shared/testing/
├── README.md               # This file
├── personas.yaml           # Test persona definitions
├── cli.py                  # CLI testing tool
├── api_test_examples.sh    # curl/httpie examples
└── sql/
    ├── 001_seed_profiles.sql         # Profiles & permissions
    ├── 002_seed_companies_teams.sql  # Companies & teams
    ├── 003_seed_test_users.sql       # Test users
    └── 004_seed_test_data.sql        # Proposals, BOs, workflows

src/shared/local_dev/
├── setup_local_env.py      # Environment setup script
├── sync_from_supabase.py   # Sync from Dev Supabase to local
└── seed_test_data.py       # Seed local SQLite with test data

src/unified-ui/
├── backend/routers/dev_panel.py    # API endpoints
└── public/dev-panel.html           # Browser UI
```

## Testing Workflows

### Testing RBAC Permissions

1. Open Dev Panel: `http://localhost:3005/dev-panel.html`
2. Click "Switch to this user" on a persona
3. Refresh the main app
4. Try accessing different features
5. Verify access is granted/denied correctly

### Testing API Endpoints Directly

There are multiple ways to test APIs:

#### Option 1: Using Local Auth Tokens (Recommended for Local Dev)

```bash
# Set environment for local auth
export ENVIRONMENT=local
export AUTH_PROVIDER=local

# Use persona tokens directly
curl http://localhost:3005/api/sales/proposals \
  -H "Authorization: Bearer local-rep_dubai_1"

# Different personas
curl http://localhost:3005/api/sales/booking-orders?status=pending \
  -H "Authorization: Bearer local-coordinator_1"
```

#### Option 2: Using Dev Panel Impersonation

```bash
# Impersonate a user (sets cookie)
curl -X POST http://localhost:3005/api/dev/impersonate \
  -H "Content-Type: application/json" \
  -d '{"persona_id": "rep_dubai_1"}' \
  -c cookies.txt

# Subsequent requests use the impersonated context
curl http://localhost:3005/api/sales/proposals \
  -b cookies.txt
```

#### Option 3: Direct Trusted Headers (Backend Testing)

```bash
# Bypass gateway, call backend directly
curl -X GET http://localhost:8000/api/v1/proposals \
  -H "X-Trusted-User-Id: test-rep_dubai_1" \
  -H "X-Trusted-User-Email: rep.dubai1@mmg.ae" \
  -H "X-Trusted-User-Profile: sales_rep" \
  -H 'X-Trusted-User-Companies: ["backlite_dubai"]'
```

#### Option 4: Using the Test Examples Script

```bash
# Run pre-built test examples
source src/shared/testing/api_test_examples.sh
```

### Testing Booking Order Flow

1. Switch to `rep_dubai_1`
2. Create a proposal
3. Submit as booking order
4. Switch to `coordinator_1`
5. Review and approve
6. Switch to `hos_backlite`
7. Approve
8. Switch to `finance_1`
9. Confirm

### Testing Data Isolation

1. Switch to `rep_dubai_1`
2. Create a proposal
3. Switch to `rep_viola_1`
4. Verify Dubai proposal is NOT visible
5. Switch to `rep_multi_company`
6. Verify can see own data from both companies, isolated

## Extending the Framework

### Adding New Personas

Edit `personas.yaml`:

```yaml
personas:
  - id: my_new_user
    email: newuser@mmg.ae
    name: New Test User
    description: Description of this user's purpose
    profile: sales_rep  # Must exist in profiles section
    companies: [backlite_dubai]
    teams:
      - team_id: 1
        role: member
    use_for:
      - Testing specific feature X
```

Then run the seed scripts again.

### Adding New Profiles

Edit `sql/001_seed_profiles.sql`:

```sql
INSERT INTO profiles (name, display_name, description, is_system) VALUES
    ('my_profile', 'My Profile', 'Description', true);

INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm
FROM profiles p, unnest(ARRAY['module:resource:action']) AS perm
WHERE p.name = 'my_profile';
```

## Local Development (Offline Mode)

For fully offline development without Supabase, use local auth mode:

### Quick Setup (Recommended)

```bash
# 1. Seed local databases with test data (no network required)
python src/shared/local_dev/seed_test_data.py

# 2. Set environment variables
export ENVIRONMENT=local
export AUTH_PROVIDER=local
export DB_BACKEND=sqlite
export STORAGE_PROVIDER=local

# 3. Start services
python run_all_services.py
```

### Alternative: Sync from Dev Supabase

```bash
# If you have Dev Supabase access, sync real data:
export UI_DEV_SUPABASE_URL=...
export UI_DEV_SUPABASE_SERVICE_ROLE_KEY=...
export SALESBOT_DEV_SUPABASE_URL=...
export SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=...

python src/shared/local_dev/sync_from_supabase.py
```

### Full Setup Script

```bash
# Run the comprehensive setup script
python src/shared/local_dev/setup_local_env.py

# This creates:
# - data/local/ui.db       (users, profiles, RBAC)
# - data/local/sales.db    (proposals, BOs)
# - data/storage/          (local file storage)
# - .env.local             (environment template)
```

### Using Test Personas (Local Auth)

When `AUTH_PROVIDER=local`, authenticate using persona tokens:

```bash
# Using persona ID
curl -H "Authorization: Bearer local-test_admin" http://localhost:3005/api/...

# Using persona ID (short form)
curl -H "Authorization: Bearer local-rep_dubai_1" http://localhost:3005/api/...

# Using email directly
curl -H "Authorization: Bearer test.admin@mmg.ae" http://localhost:3005/api/...
```

### How It Works

1. Local auth reads personas from `personas.yaml`
2. Each persona has predefined profile, permissions, companies, teams
3. Full RBAC context is loaded from the persona definition
4. No network/Supabase required

### Storage Cleanup

To manage local data storage:

```bash
# Check storage usage
python src/shared/local_dev/setup_local_env.py --usage

# Clean databases only (keep .env.local)
python src/shared/local_dev/setup_local_env.py --clean

# Clean everything (asks for confirmation)
python src/shared/local_dev/setup_local_env.py --clean-all
```

See `src/shared/local_dev/ENVIRONMENTS.md` for full documentation.

---

## Permission Toggle (Dev Mode)

Toggle individual permissions on/off without changing personas:

### Toggle Single Permission
```bash
# Add a permission
curl -X POST http://localhost:3005/api/dev/permissions/toggle \
  -H "Content-Type: application/json" \
  -d '{"permission": "sales:proposals:delete", "enabled": true}'

# Remove a permission
curl -X POST http://localhost:3005/api/dev/permissions/toggle \
  -H "Content-Type: application/json" \
  -d '{"permission": "sales:proposals:create", "enabled": false}'
```

### Add/Remove Multiple
```bash
# Add multiple permissions
curl -X POST http://localhost:3005/api/dev/permissions/add \
  -H "Content-Type: application/json" \
  -d '{"permissions": ["assets:locations:create", "assets:networks:create"]}'

# Remove multiple permissions
curl -X POST http://localhost:3005/api/dev/permissions/remove \
  -H "Content-Type: application/json" \
  -d '{"permissions": ["sales:proposals:create", "sales:proposals:update"]}'
```

### Set Exact Permissions
```bash
# Replace all permissions with an exact list
curl -X POST http://localhost:3005/api/dev/permissions/set-exact \
  -H "Content-Type: application/json" \
  -d '["sales:proposals:read", "sales:booking_orders:read"]'
```

### Check/Reset Overrides
```bash
# See current overrides
curl http://localhost:3005/api/dev/permissions/overrides

# Reset to profile defaults
curl -X POST http://localhost:3005/api/dev/permissions/reset
```

---

## Pytest Fixtures

Comprehensive fixtures for automated testing:

```python
# In your test file
import pytest

def test_rep_can_create_proposal(auth_headers_rep_dubai_1, test_client):
    response = test_client.post(
        "/api/sales/proposals",
        headers=auth_headers_rep_dubai_1,
        json={"client_name": "Test"}
    )
    assert response.status_code == 201

def test_viewer_cannot_create(auth_headers_viewer_only, test_client):
    response = test_client.post(
        "/api/sales/proposals",
        headers=auth_headers_viewer_only,
        json={"client_name": "Test"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMISSION_DENIED"

def test_workflow(scenario_basic_sales_flow, test_client):
    rep, coordinator, hos, finance = scenario_basic_sales_flow
    # ... test complete workflow with each persona
```

### Available Fixtures

| Fixture | Description |
|---------|-------------|
| `persona_test_admin` | System admin PersonaContext |
| `persona_rep_dubai_1` | Dubai sales rep PersonaContext |
| `auth_headers_rep_dubai_1` | Trusted headers dict for rep |
| `get_persona("id")` | Factory to get any persona |
| `get_auth_headers("id")` | Factory to get any headers |
| `scenario_basic_sales_flow` | List of personas for workflow |
| `assert_has_permission("id", "perm")` | Assert permission exists |
| `mock_user_context("id")` | Get dict for unit tests |

See `src/shared/testing/example_tests.py` for more examples.

---

## Postman Collection

Import the collection for quick API testing:

1. Import `src/shared/testing/postman/mmg_api_collection.json`
2. Import `src/shared/testing/postman/mmg_environments.json`
3. Select "MMG Environments" environment
4. Change `persona` variable to switch users

Features:
- Pre-request scripts auto-inject auth headers
- RBAC tests verify 403 responses include detailed errors
- Workflow scenarios chain requests with persona switching

See `src/shared/testing/postman/README.md` for full documentation.

---

## Troubleshooting

### "Dev panel not enabled"
- Ensure `ENVIRONMENT` is set to `local`, `development`, or `test`
- Check that unified-ui is running

### "Persona not found"
- Run `python cli.py list` to see available personas
- Ensure you've run the SQL seed scripts

### "User not in Supabase Auth"
- Test users need to be created in Supabase Auth first
- Use the Supabase dashboard to create users with emails from `personas.yaml`
- Or use the CLI setup command
- **Or use local auth mode:** Set `AUTH_PROVIDER=local` to bypass Supabase

### Impersonation not working
- Check browser cookies are enabled
- Try clearing cookies and refreshing
- Verify the `/api/dev/impersonate` endpoint returns success

### Local auth "Invalid token"
- Ensure `AUTH_PROVIDER=local` is set
- Check persona ID exists in `personas.yaml`
- Token format: `local-{persona_id}` or just email
