# Frontend Requirements for Amr

---

## DEV TO-DO: Unified Asset Management

### Part 1: Unified Architecture ✅ DONE
- [x] Merge `standalone_assets` into `networks` with `standalone` flag
- [x] Add `environment` field to `network_assets` (indoor/outdoor)
- [x] Add `area`, `country` fields to locations
- [x] Create unified `locations` VIEW (no `asset_source`)
- [x] Add `get_mockup_storage_info()` for mockup path resolution
- [x] Internal API endpoint `/api/internal/mockup-storage-info/{network_key}`
- [x] Migration scripts (`03_unify_standalone.sql`, `04_add_country_column.sql`)

### Part 2: Eligibility Service ⏳ PENDING
- [ ] Check if location is **eligible for booking** on given dates
- [ ] Query `asset_occupations` to find date conflicts
- [ ] Return availability status for proposals
- [ ] Endpoint: `GET /api/locations/{location_key}/availability?start_date=X&end_date=Y`
- [ ] Used by Sales-Module when generating proposals

### Database Migration (for existing DB)
```bash
# Run in Supabase SQL Editor:
1. 03_unify_standalone.sql   # Migrates standalone_assets → networks
2. 04_add_country_column.sql # Adds country field
```

---

## Pending

## Authentication
1. Authentication issue where 401 causes logout within a specific time. maybe token expiry?

## General
1. Font issue when the font is not available in the local system.

### Questions / Confirmations
1. **Companies Endpoint** - Confirm if `/dev/companies` path is correct for company details
2. Permissions CRUD not available in the api/rbac/ path. currently using it from api/dev/ path.

### Admin Features
2. **User - multiple Profile sets** - Assign/list multiple profiles per user
3. **User - multiple Permission sets** - Assign multiple permission sets per user
4. **Profile to Permission-Set relation** - Link profiles to permission sets
5. **Hide unused tabs** - Hide teams, sharing rules etc. that are not in use
6. **Add Location UI** - List out the locations for admins

### Mockups
7. **Template thumbnails** - Save `xxxx_n_thumb.png` alongside templates for faster loading. Include in response as `thumbnail` field
8. **Mockup history** - Show history with date + generated image
9. **Mockup frame edit endpoint** - Endpoint to get frame details/config for editing existing templates
   - **Answer**: Yes, use `GET /api/mockup-frames/{company}/{location_key}/frame?time_of_day=day&finish=gold` to get frame data
10. 502 bad gateway while generating the test preview on render deployment. Not in local.
11. company_schema : "unknown" in api/locations endpoint


---

## Completed

### Separate Proposals - Multiple Dates + Payment Terms
**Issue**: Separate proposals were not showing different `start_dates` and `payment_terms` was defaulting to "100% upfront"

**Fix**: Now supports `start_dates` array parallel with `durations` and `net_rates`. Each option gets its own column in the financial slide.

**Example Request**:
```json
{
    "proposals": [{
        "location": "oryx",
        "start_dates": ["01/01/2026", "01/02/2026", "01/03/2026"],
        "durations": ["2 Weeks", "2 Weeks", "3 Weeks"],
        "net_rates": ["AED 12,000", "AED 13,000", "AED 32,000"]
    }],
    "client_name": "Etisalat",
    "proposal_type": "separate",
    "payment_terms": "70% upfront, 30% after"
}
```

**Status**: Fixed in commit `5ed9e78`


##Authentication Issue

2026-01-07 05:48:20,276 - unified-ui - ERROR - [PROXY AUTH] Error: invalid JWT: unable to parse or verify signature, token has invalid claims: token is expired
2026-01-07 05:48:20,277 - unified-ui - INFO - [UI] GET /api/sales/mockup/locations -> 401 (51ms)
INFO:     10.16.95.189:48094 - "GET /api/sales/mockup/locations HTTP/1.1" 401 Unauthorized
[GET]
crm-unified-ui.onrender.com/api/base/auth/me clientIP="94.200.129.142" requestID="9d89dc72-b0d9-4d56" responseTimeMS=547 responseBytes=539 userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
[GET]
crm-unified-ui.onrender.com/api/base/auth/me clientIP="94.200.129.142" requestID="86d712eb-7574-4ae7" responseTimeMS=596 responseBytes=539 userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
2026-01-07 05:48:21,180 - unified-ui - INFO - [RBAC CACHE] Invalidated cache for user acb4874e-d5cc-4cad-acdf-40aa82d09ee5
2026-01-07 05:48:21,222 - unified-ui - INFO - [UI] User profile fetched: a.tamer@mmg.global -> system_admin with 1 permissions
2026-01-07 05:48:21,222 - unified-ui - INFO - [UI] GET /api/base/auth/me -> 200 (593ms)
INFO:     10.16.95.189:48094 - "GET /api/base/auth/me HTTP/1.1" 200 OK
2026-01-07 05:48:21,839 - unified-ui - INFO - [RBAC CACHE] Invalidated cache for user acb4874e-d5cc-4cad-acdf-40aa82d09ee5
2026-01-07 05:48:21,887 - unified-ui - INFO - [UI] User profile fetched: a.tamer@mmg.global -> system_admin with 1 permissions
2026-01-07 05:48:21,887 - unified-ui - INFO - [UI] GET /api/base/auth/me -> 200 (545ms)
INFO:     10.16.28.5:49346 - "GET /api/base/auth/me HTTP/1.1" 200 OK
[GET]
crm-unified-ui.onrender.com/logo.svg clientIP="94.200.129.142" requestID="c4fd97ab-900a-43bb" responseTimeMS=3 responseBytes=858 userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
[GET]
crm-unified-ui.onrender.com/favicon.ico clientIP="94.200.129.142" requestID="c23fe076-477f-4222" responseTimeMS=3 responseBytes=858 userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
[GET]
crm-unified-ui.onrender.com/api/base/auth/me clientIP="94.200.129.142" requestID="e78aa9b4-9f8a-47e1" responseTimeMS=40 responseBytes=459 userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
2026-01-07 05:48:22,128 - unified-ui - ERROR - [UI Auth] Error: Session from session_id claim in JWT does not exist
