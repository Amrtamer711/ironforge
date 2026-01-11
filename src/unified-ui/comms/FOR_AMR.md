# Frontend Requirements for Amr

---

## DEV TO-DO: Unified Asset Management

# - [ ] Make the changes to mockup and proposal generation LLM chats with new location structure.
# - [ ] Lazy Load Chat Messages so that the user is not stuck with loading conversations after login (Clarify if reducing the no of chats loaded will have positive impact).
- [ ] Check the indoor locations - Why images are not loading. Maybe we can solve this by using the venue_type that is being sent from UI, but API is not accepting the venue_type. Details below : #Error01, #Explanation01, #Error02 


### Part 1: Unified Architecture ✅ DONE

- [X] Merge `standalone_assets` into `networks` with `standalone` flag
- [X] Add `environment` field to `network_assets` (indoor/outdoor)
- [X] Add `area`, `country` fields to locations
- [X] Create unified `locations` VIEW (no `asset_source`)
- [X] Add `get_mockup_storage_info()` for mockup path resolution
- [X] Internal API endpoint `/api/internal/mockup-storage-info/{network_key}`
- [X] Migration scripts (`03_unify_standalone.sql`, `04_add_country_column.sql`)

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
# 2. Change the Auth redirect to new mmg-nova.com in supabase


## Profiles 

Sales Executive - Account director
	associated with one company. only view their own mockups and proposals
Head of Sales
	associated with one company. They can view proposals and mockups of all users under that company.
Chief Revenue Officer
	across all companies. everything must be visible for all users.


## General

1. Font issue when the font is not available in the local system.
2. Examine the document cached log(could be the reason why the chat history loading is taking too long)
3. Inefficient search for mockup photo in mockup generate ( we already know the configuration we need to look for but we are still looking in all companies)
4. Ensure most functionality and llm functionality are equivalent

### Questions / Confirmations

1. **Companies Endpoint** - Confirm if `/dev/companies` path is correct for company details
2. Permissions CRUD not available in the api/rbac/ path. currently using it from api/dev/ path.

### Admin Features

2. **User - multiple Profile sets** - Assign/list multiple profiles per user
3. **User - multiple Permission sets** - Assign multiple permission sets per user
4. **Profile to Permission-Set relation** - Link profiles to permission sets
# 5. **Hide unused tabs** - Hide teams, sharing rules etc. that are not in use
# 6. **Add Location UI** - List out the locations for admins

### Mockups

1. **Template thumbnails** - Save `xxxx_n_thumb.png` alongside templates for faster loading. Include in response as `thumbnail` field
2. **Mockup history** - Show history with date + generated image
3. **Mockup frame edit endpoint** - Endpoint to get frame details/config for editing existing templates
   - **Answer**: Yes, use `GET /api/mockup-frames/{company}/{location_key}/frame?time_of_day=day&finish=gold` to get frame data
# 4. 502 bad gateway while generating the test preview on render deployment. Not in local.
# 5. company_schema : "unknown" in api/locations endpoint
6. Save the mockups generated with details in the Generate Page and to be available as links in a history endpoint just like proposal history.
7. Generate and Setup shows different list of Locations.


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

-------------------------------


#Error01

[21:19:05] [Assets] ERROR: 2026-01-10 17:19:05,596 - asset-management - DEBUG - [STORAGE] Mockup photo not found: viola/dna01/outdoor/day/gold/Dna01_3.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[21:19:05] [Assets] INFO: 2026-01-10 17:19:05,596 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/viola/dna01/outdoor/day/gold/Dna01_3.jpg -> 404 (701ms) user=- request_id=107fb233-25f2-4f64-a6cf-9ba4120fed74
[21:19:05] [Assets] INFO: INFO:     127.0.0.1:62946 - "GET /api/storage/mockups/viola/dna01/outdoor/day/gold/Dna01_3.jpg HTTP/1.1" 404 Not Found
[21:19:05] [Sales] WARN: 17:19:05 WARNING  [4b45fadd] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Photo not found in any company
[21:19:05] [Sales] ERROR: 17:19:05 ERROR    [4b45fadd] proposal-bot: [PHOTO GET] ✗ Photo not found: dna01/Dna01_3.jpg
[21:19:05] [Sales] INFO: 17:19:05 INFO     [4b45fadd] api.request: GET /api/mockup/photo/dna01 -> 404 (3891ms)
[21:19:05] [UI] INFO: 2026-01-10 17:19:05,598 - unified-ui - INFO - [PROXY] Response: 404
[21:19:05] [UI] INFO: 2026-01-10 17:19:05,598 - unified-ui - INFO - [UI] GET /api/sales/mockup/photo/dna01 -> 404 (4348ms)
[21:19:05] [UI] INFO: INFO:     127.0.0.1:63103 - "GET /api/sales/mockup/photo/dna01?photo_filename=Dna01_3.jpg&time_of_day=day&side=gold&company=backlite_dubai HTTP/1.1" 404 Not Found
[21:19:06] [Assets] ERROR: 2026-01-10 17:19:06,320 - asset-management - DEBUG - [STORAGE] Mockup photo not found: viola/dna01/outdoor/day/gold/Dna01_4.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[21:19:06] [Assets] INFO: 2026-01-10 17:19:06,321 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/viola/dna01/outdoor/day/gold/Dna01_4.jpg -> 404 (798ms) user=- request_id=6732d396-0ef3-439c-984a-fbcf1a4819a5
[21:19:06] [Assets] INFO: INFO:     127.0.0.1:62952 - "GET /api/storage/mockups/viola/dna01/outdoor/day/gold/Dna01_4.jpg HTTP/1.1" 404 Not Found
[21:19:06] [Sales] WARN: 17:19:06 WARNING  [af931afc] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Photo not found in any company
[21:19:06] [Sales] ERROR: 17:19:06 ERROR    [af931afc] proposal-bot: [PHOTO GET] ✗ Photo not found: dna01/Dna01_4.jpg

end Error01

#Explanation01

Observed behavior

After saving mockup frames for multiple selected locations with venue_type=indoor, template images do not load for indoor templates.
Immediately after save, templates are inconsistent across locations: some return templates, others don’t. Sometimes templates appear only after refresh/logout/reselect.
Frontend flow (MockupPage.jsx / mockup.js)

Save: POST /api/sales/mockup/save-frame (multipart) with:
location_keys (JSON array), venue_type, optional asset_type_key, time_of_day, side, frames_data, photo
Refresh: invalidates and refetches templates for each selected location:
GET /api/sales/mockup/templates/{locationKey}?time_of_day=...&side=...&venue_type=...
Image load: GET /api/sales/mockup/photo/{locationKey}?photo_filename=...&time_of_day=...&side=...&venue_type=...
Questions for backend

Is template creation asynchronous or delayed after save-frame?
Is there any caching (API, CDN, DB, or service-layer) that could return stale template lists or photos right after save?


end Explanation01



#Error02
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,770 - unified-ui - INFO - [AUTH] Expanded companies: ['backlite_abudhabi', 'backlite_uk', 'viola', 'backlite_dubai'] -> ['backlite_abudhabi', 'backlite_dubai', 'backlite_uk', 'viola']
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,772 - unified-ui - INFO - [PROXY] GET /api/sales/mockup/photo/dna04 -> http://localhost:8000/api/mockup/photo/dna04?photo_filename=Dna04_3.jpg&time_of_day=day&side=gold&company=backlite_dubai&venue_type=indoor
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,772 - unified-ui - INFO - [PROXY] User: r.shahzad@mmg.global | Profile: system_admin
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,773 - unified-ui - INFO - [AUTH] Expanded companies: ['backlite_abudhabi', 'backlite_uk', 'viola', 'backlite_dubai'] -> ['backlite_abudhabi', 'backlite_dubai', 'backlite_uk', 'viola']
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,773 - unified-ui - INFO - [AUTH] Expanded companies: ['backlite_abudhabi', 'backlite_uk', 'viola', 'backlite_dubai'] -> ['backlite_abudhabi', 'backlite_dubai', 'backlite_uk', 'viola']
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,774 - unified-ui - INFO - [PROXY] GET /api/sales/mockup/photo/dna04 -> http://localhost:8000/api/mockup/photo/dna04?photo_filename=Dna04_2.jpg&time_of_day=day&side=gold&company=backlite_dubai&venue_type=indoor
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,774 - unified-ui - INFO - [PROXY] User: r.shahzad@mmg.global | Profile: system_admin
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,775 - unified-ui - INFO - [PROXY] GET /api/sales/mockup/photo/dna04 -> http://localhost:8000/api/mockup/photo/dna04?photo_filename=Dna04_4.jpg&time_of_day=day&side=gold&company=backlite_dubai&venue_type=indoor
[22:31:43] [UI] INFO: 2026-01-11 18:31:43,775 - unified-ui - INFO - [PROXY] User: r.shahzad@mmg.global | Profile: system_admin
[22:31:43] [Sales] INFO: 18:31:43 INFO     [3357699a] api.request: GET /api/mockup/photo/dna04
[22:31:43] [Sales] INFO: 18:31:43 INFO     [909b4ab0] api.request: GET /api/mockup/photo/dna04
[22:31:43] [Sales] INFO: 18:31:43 INFO     [3357699a] proposal-bot: [PHOTO GET] Request for photo: dna04/Dna04_3.jpg (time_of_day=day, side=gold, company=backlite_dubai)
[22:31:43] [Sales] INFO: 18:31:43 INFO     [3357699a] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Downloading photo: dna04/outdoor/day/gold/Dna04_3.jpg
[22:31:43] [Sales] INFO: 18:31:43 INFO     [ca11492e] api.request: GET /api/mockup/photo/dna04
[22:31:43] [Sales] INFO: 18:31:43 INFO     [909b4ab0] proposal-bot: [PHOTO GET] Request for photo: dna04/Dna04_2.jpg (time_of_day=day, side=gold, company=backlite_dubai)
[22:31:43] [Sales] INFO: 18:31:43 INFO     [909b4ab0] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Downloading photo: dna04/outdoor/day/gold/Dna04_2.jpg
[22:31:43] [Sales] INFO: 18:31:43 INFO     [ca11492e] proposal-bot: [PHOTO GET] Request for photo: dna04/Dna04_4.jpg (time_of_day=day, side=gold, company=backlite_dubai)
[22:31:43] [Sales] INFO: 18:31:43 INFO     [ca11492e] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Downloading photo: dna04/outdoor/day/gold/Dna04_4.jpg
[22:31:43] [Assets] INFO: 2026-01-11 18:31:43,821 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_dubai/dna04/outdoor/day/gold/Dna04_2.jpg
[22:31:43] [Assets] INFO: 2026-01-11 18:31:43,831 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_dubai/dna04/outdoor/day/gold/Dna04_4.jpg
[22:31:44] [Assets] ERROR: 2026-01-11 18:31:44,594 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_dubai/dna04/outdoor/day/gold/Dna04_2.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,594 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_2.jpg -> 404 (774ms) user=- request_id=b76e6db7-1f98-4c47-aa97-ff6594151c4a
[22:31:44] [Assets] INFO: INFO:     127.0.0.1:53588 - "GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_2.jpg HTTP/1.1" 404 Not Found
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,600 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_2.jpg
[22:31:44] [Assets] ERROR: 2026-01-11 18:31:44,656 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_dubai/dna04/outdoor/day/gold/Dna04_4.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,656 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_4.jpg -> 404 (835ms) user=- request_id=4199f903-dc97-4e06-b032-048ec000700a
[22:31:44] [Assets] INFO: INFO:     127.0.0.1:53590 - "GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_4.jpg HTTP/1.1" 404 Not Found
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,658 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_4.jpg
[22:31:44] [Assets] ERROR: 2026-01-11 18:31:44,669 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_dubai/dna04/outdoor/day/gold/Dna04_3.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,673 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_3.jpg -> 404 (865ms) user=- request_id=3c381273-da81-4128-aad0-7eb8bfccfe11
[22:31:44] [Assets] INFO: INFO:     127.0.0.1:53474 - "GET /api/storage/mockups/backlite_dubai/dna04/outdoor/day/gold/Dna04_3.jpg HTTP/1.1" 404 Not Found
[22:31:44] [Assets] INFO: 2026-01-11 18:31:44,674 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_3.jpg
[22:31:45] [Assets] ERROR: 2026-01-11 18:31:45,415 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_3.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,416 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_3.jpg -> 404 (741ms) user=- request_id=2d7589ee-6ad5-4c46-aa3d-e655364bde8e
[22:31:45] [Assets] INFO: INFO:     127.0.0.1:53474 - "GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_3.jpg HTTP/1.1" 404 Not Found
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,419 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_uk/dna04/outdoor/day/gold/Dna04_3.jpg
[22:31:45] [Assets] ERROR: 2026-01-11 18:31:45,532 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_4.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,532 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_4.jpg -> 404 (874ms) user=- request_id=f800367e-bb18-4898-b9b8-d8f8d9c741c4
[22:31:45] [Assets] INFO: INFO:     127.0.0.1:53590 - "GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_4.jpg HTTP/1.1" 404 Not Found
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,535 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_uk/dna04/outdoor/day/gold/Dna04_4.jpg
[22:31:45] [Assets] ERROR: 2026-01-11 18:31:45,549 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_abudhabi/dna04/outdoor/day/gold/Dna04_2.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,549 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_2.jpg -> 404 (949ms) user=- request_id=32339d8f-430e-4cfc-bf1c-66fc47f3bfe2
[22:31:45] [Assets] INFO: INFO:     127.0.0.1:53588 - "GET /api/storage/mockups/backlite_abudhabi/dna04/outdoor/day/gold/Dna04_2.jpg HTTP/1.1" 404 Not Found
[22:31:45] [Assets] INFO: 2026-01-11 18:31:45,551 - asset-management - INFO - [STORAGE] Getting mockup photo: backlite_uk/dna04/outdoor/day/gold/Dna04_2.jpg
[22:31:46] [Assets] ERROR: 2026-01-11 18:31:46,335 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_uk/dna04/outdoor/day/gold/Dna04_4.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:46] [Assets] ERROR: 2026-01-11 18:31:46,335 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_uk/dna04/outdoor/day/gold/Dna04_2.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:46] [Assets] ERROR: 2026-01-11 18:31:46,335 - asset-management - DEBUG - [STORAGE] Mockup photo not found: backlite_uk/dna04/outdoor/day/gold/Dna04_3.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,335 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_4.jpg -> 404 (801ms) user=- request_id=49a2ed02-5b82-4c80-a3ef-91b022b22348
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,335 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_2.jpg -> 404 (785ms) user=- request_id=18fb599f-01db-4a71-bb48-1406b8b6819c
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,335 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_3.jpg -> 404 (917ms) user=- request_id=5d151e12-7202-45d7-a543-a00affdca5c4
[22:31:46] [Assets] INFO: INFO:     127.0.0.1:53590 - "GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_4.jpg HTTP/1.1" 404 Not Found
[22:31:46] [Assets] INFO: INFO:     127.0.0.1:53588 - "GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_2.jpg HTTP/1.1" 404 Not Found
[22:31:46] [Assets] INFO: INFO:     127.0.0.1:53474 - "GET /api/storage/mockups/backlite_uk/dna04/outdoor/day/gold/Dna04_3.jpg HTTP/1.1" 404 Not Found
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,339 - asset-management - INFO - [STORAGE] Getting mockup photo: viola/dna04/outdoor/day/gold/Dna04_4.jpg
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,356 - asset-management - INFO - [STORAGE] Getting mockup photo: viola/dna04/outdoor/day/gold/Dna04_2.jpg
[22:31:46] [Assets] INFO: 2026-01-11 18:31:46,368 - asset-management - INFO - [STORAGE] Getting mockup photo: viola/dna04/outdoor/day/gold/Dna04_3.jpg
[22:31:47] [Assets] ERROR: 2026-01-11 18:31:47,052 - asset-management - DEBUG - [STORAGE] Mockup photo not found: viola/dna04/outdoor/day/gold/Dna04_4.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:47] [Assets] INFO: 2026-01-11 18:31:47,052 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_4.jpg -> 404 (713ms) user=- request_id=d5862e55-a29c-48e1-bb60-89a156981f97
[22:31:47] [Assets] INFO: INFO:     127.0.0.1:53590 - "GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_4.jpg HTTP/1.1" 404 Not Found
[22:31:47] [Sales] WARN: 18:31:47 WARNING  [ca11492e] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Photo not found in any company
[22:31:47] [Sales] ERROR: 18:31:47 ERROR    [ca11492e] proposal-bot: [PHOTO GET] ✗ Photo not found: dna04/Dna04_4.jpg
[22:31:47] [Sales] INFO: 18:31:47 INFO     [ca11492e] api.request: GET /api/mockup/photo/dna04 -> 404 (3249ms)
[22:31:47] [UI] INFO: 2026-01-11 18:31:47,056 - unified-ui - INFO - [PROXY] Response: 404
[22:31:47] [UI] INFO: 2026-01-11 18:31:47,058 - unified-ui - INFO - [UI] GET /api/sales/mockup/photo/dna04 -> 404 (4188ms)
[22:31:47] [UI] INFO: INFO:     127.0.0.1:53666 - "GET /api/sales/mockup/photo/dna04?photo_filename=Dna04_4.jpg&time_of_day=day&side=gold&company=backlite_dubai&venue_type=indoor HTTP/1.1" 404 Not Found
[22:31:47] [Assets] ERROR: 2026-01-11 18:31:47,085 - asset-management - DEBUG - [STORAGE] Mockup photo not found: viola/dna04/outdoor/day/gold/Dna04_3.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:47] [Assets] ERROR: 2026-01-11 18:31:47,085 - asset-management - DEBUG - [STORAGE] Mockup photo not found: viola/dna04/outdoor/day/gold/Dna04_2.jpg - {'statusCode': 404, 'error': not_found, 'message': Object not found}
[22:31:47] [Assets] INFO: 2026-01-11 18:31:47,085 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_3.jpg -> 404 (746ms) user=- request_id=80b8792f-b549-4f65-bdd2-07582967ea25
[22:31:47] [Assets] INFO: 2026-01-11 18:31:47,085 - crm_security.middleware - INFO - [HTTP] GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_2.jpg -> 404 (746ms) user=- request_id=16e62a53-fa8b-411a-aaa1-1710bd8508dd
[22:31:47] [Assets] INFO: INFO:     127.0.0.1:53474 - "GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_3.jpg HTTP/1.1" 404 Not Found
[22:31:47] [Assets] INFO: INFO:     127.0.0.1:53588 - "GET /api/storage/mockups/viola/dna04/outdoor/day/gold/Dna04_2.jpg HTTP/1.1" 404 Not Found
[22:31:47] [Sales] WARN: 18:31:47 WARNING  [3357699a] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Photo not found in any company
[22:31:47] [Sales] ERROR: 18:31:47 ERROR    [3357699a] proposal-bot: [PHOTO GET] ✗ Photo not found: dna04/Dna04_3.jpg
[22:31:47] [Sales] WARN: 18:31:47 WARNING  [909b4ab0] core.services.mockup_frame_service: [MOCKUP_FRAME_SERVICE] Photo not found in any company
[22:31:47] [Sales] ERROR: 18:31:47 ERROR    [909b4ab0] proposal-bot: [PHOTO GET] ✗ Photo not found: dna04/Dna04_2.jpg
[22:31:47] [Sales] INFO: 18:31:47 INFO     [3357699a] api.request: GET /api/mockup/photo/dna04 -> 404 (3283ms)
[22:31:47] [Sales] INFO: 18:31:47 INFO     [909b4ab0] api.request: GET /api/mockup/photo/dna04 -> 404 (3282ms)

End Error02