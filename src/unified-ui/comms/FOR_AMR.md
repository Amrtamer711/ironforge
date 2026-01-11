# Frontend Requirements for Amr

---

## DEV TO-DO: Unified Asset Management

# - [ ] Make the changes to mockup and proposal generation LLM chats with new location structure.
# - [ ] Lazy Load Chat Messages so that the user is not stuck with loading conversations after login (Clarify if reducing the no of chats loaded will have positive impact).
- [ ] Check the indoor locations - Why images are not loading. Maybe we can solve this by using the venue_type that is being sent from UI, but API is not accepting the venue_type. Details below : #Error01, #Explanation01, #Error02 
- [ ] Chat history of new items not visible. Does this mean anything #Error03
- [ ] Chat history displaying the First 500 messages only, not the latest messages. 
- [ ] Proposal bot calling supbase storage so many times. looks like file links. Is this necessary? That may be blocking the history endpoint response. #Error04



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


#Error03

[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Signed URL generated (length: 546)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Extracted JWT token (length: 364)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] ===== JWT TOKEN ANALYSIS =====
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Full JWT claims: {
[22:57:07] [Sales] INFO:   "url": "uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2026/01/11/a6ed01ea-a5ac-466f-a608-d79205aca4d2_dior_185611126.pdf",
[22:57:07] [Sales] INFO:   "iat": 1768143427,
[22:57:07] [Sales] INFO:   "exp": 1768229827
[22:57:07] [Sales] INFO: }
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Current server time: 1768143427 (2026-01-11T14:57:07+00:00)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Token issued at (iat): 1768143427 (2026-01-11T14:57:07+00:00)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Token expires at (exp): 1768229827 (2026-01-12T14:57:07+00:00)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Time until expiry: 86400s (24.00 hours)
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Time since token issued: 0s
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Expected exp (server_time + 86400): 1768229827
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] Actual exp drift from expected: 0s
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] ✅ Token appears valid and will expire in 24.00 hours
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST END ==========
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] integrations.channels.adapters.web: [WebAdapter] File uploaded to supabase: dior_185611126.pdf -> uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2026/01/11/a6ed01ea-a5ac-466f-a608-d79205aca4d2_dior_185611126.pdf (hash=b9ce794c260609ef...)
[22:57:07] [Sales] DEBUG: 18:57:07 DEBUG    [fe090267] integrations.channels.adapters.web: [WebAdapter] Completed request 4ba9c971... for ee7eabae-3214-4364-8e48-12b8ffc0532a
[22:57:07] [Sales] ERROR: 18:57:07 ERROR    [fe090267] proposal-bot: [CHAT PERSIST] Failed to append messages for ee7eabae-3214-4364-8e48-12b8ffc0532a: '_DatabaseNamespace' object has no attribute 'append_chat_messages'
[22:57:07] [Sales] INFO: 18:57:07 INFO     [fe090267] api.chat: [CHAT] Stream completed for r.shahzad@mmg.global
end #Error03




#Error04


[01:11:04] [Assets] INFO: 2026-01-11 21:11:04,491 - asset-management - INFO - [SUPABASE] Expanded ['backlite_abudhabi', 'backlite_uk', 'viola', 'backlite_dubai'] -> ['backlite_abudhabi', 'backlite_dubai', 'backlite_uk', 'viola']
[01:11:04] [Assets] INFO: 2026-01-11 21:11:04,492 - crm_security.middleware - INFO - [HTTP] POST /api/companies/expand -> 200 (233ms) user=- request_id=0e0b2dfc-5de3-43af-baee-20025524c02c
[01:11:04] [Assets] INFO: INFO:     127.0.0.1:50668 - "POST /api/companies/expand?company_codes=backlite_abudhabi&company_codes=backlite_uk&company_codes=viola&company_codes=backlite_dubai HTTP/1.1" 200 OK
[01:11:04] [UI] INFO: 2026-01-11 21:11:04,494 - unified-ui - INFO - [AUTH] Expanded companies: ['backlite_abudhabi', 'backlite_uk', 'viola', 'backlite_dubai'] -> ['backlite_abudhabi', 'backlite_dubai', 'backlite_uk', 'viola']
[01:11:04] [UI] INFO: 2026-01-11 21:11:04,494 - unified-ui - INFO - [PROXY] GET /api/sales/chat/history -> http://localhost:8000/api/chat/history?limit=500
[01:11:04] [UI] INFO: 2026-01-11 21:11:04,494 - unified-ui - INFO - [PROXY] User: r.shahzad@mmg.global | Profile: system_admin
[01:11:04] [Sales] INFO: 21:11:04 INFO     [8e5d3420] api.request: GET /api/chat/history
[01:11:04] [Sales] DEBUG: 21:11:04 DEBUG    [8e5d3420] proposal-bot: [CACHE] Chat session cache hit: ee7eabae-3214-4364-8e48-12b8ffc0532a
[01:11:08] [Sales] DEBUG: 21:11:08 DEBUG    [8e5d3420] proposal-bot: [CACHE] Documents batch: all 73 from cache
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST START ==========
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] System time BEFORE call: 1768151468.742707 (2026-01-11T17:11:08.742707+00:00)
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Bucket: uploads, Key: ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/846fb1cc-9c8b-445b-8ff3-78810ffc802a_MMG Back.png
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Requested expires_in: 86400s (24.0 hours)
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Supabase URL: https://hqhwddnaynbimltpqlli.supabase.co
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Service key prefix: sb_secret_eL3x1ZJz2c...
[01:11:08] [Sales] INFO: 21:11:08 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Calling Supabase create_signed_url API...
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] System time AFTER call: 1768151469.318826 (2026-01-11T17:11:09.318826+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] API call took: 0.576s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Raw response: {'signedURL': 'https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/846fb1cc-9c8b-445b-8ff3-78810ffc802a_MMG%20Back.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL2VlN2VhYmFlLTMyMTQtNDM2NC04ZTQ4LTEyYjhmZmMwNTMyYS8yMDI1LzEyLzIzLzg0NmZiMWNjLTljOGItNDQ1Yi04ZmYzLTc4ODEwZmZjODAyYV9NTUcgQmFjay5wbmciLCJpYXQiOjE3NjgxNTE0NjksImV4cCI6MTc2ODIzNzg2OX0.O6niwMa54rVi751_xfwcZzmO13O3Jf4WkcnDX56VJCc', 'signedUrl': 'https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/846fb1cc-9c8b-445b-8ff3-78810ffc802a_MMG%20Back.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL2VlN2VhYmFlLTMyMTQtNDM2NC04ZTQ4LTEyYjhmZmMwNTMyYS8yMDI1LzEyLzIzLzg0NmZiMWNjLTljOGItNDQ1Yi04ZmYzLTc4ODEwZmZjODAyYV9NTUcgQmFjay5wbmciLCJpYXQiOjE3NjgxNTE0NjksImV4cCI6MTc2ODIzNzg2OX0.O6niwMa54rVi751_xfwcZzmO13O3Jf4WkcnDX56VJCc'}
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Signed URL generated (length: 534)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Extracted JWT token (length: 356)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ===== JWT TOKEN ANALYSIS =====
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Full JWT claims: {
[01:11:09] [Sales] INFO:   "url": "uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/846fb1cc-9c8b-445b-8ff3-78810ffc802a_MMG Back.png",
[01:11:09] [Sales] INFO:   "iat": 1768151469,
[01:11:09] [Sales] INFO:   "exp": 1768237869
[01:11:09] [Sales] INFO: }
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Current server time: 1768151469 (2026-01-11T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Token issued at (iat): 1768151469 (2026-01-11T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Token expires at (exp): 1768237869 (2026-01-12T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Time until expiry: 86400s (24.00 hours)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Time since token issued: 0s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Expected exp (server_time + 86400): 1768237868
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Actual exp drift from expected: 1s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ✅ Token appears valid and will expire in 24.00 hours
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST END ==========
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST START ==========
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] System time BEFORE call: 1768151469.31917 (2026-01-11T17:11:09.319170+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Bucket: uploads, Key: ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/7a15605c-1f0f-42ec-a70a-528e1202240e_MMG Back.png
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Requested expires_in: 86400s (24.0 hours)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Supabase URL: https://hqhwddnaynbimltpqlli.supabase.co
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Service key prefix: sb_secret_eL3x1ZJz2c...
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Calling Supabase create_signed_url API...
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] System time AFTER call: 1768151469.5422878 (2026-01-11T17:11:09.542288+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] API call took: 0.223s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Raw response: {'signedURL': 'https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/7a15605c-1f0f-42ec-a70a-528e1202240e_MMG%20Back.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL2VlN2VhYmFlLTMyMTQtNDM2NC04ZTQ4LTEyYjhmZmMwNTMyYS8yMDI1LzEyLzIzLzdhMTU2MDVjLTFmMGYtNDJlYy1hNzBhLTUyOGUxMjAyMjQwZV9NTUcgQmFjay5wbmciLCJpYXQiOjE3NjgxNTE0NjksImV4cCI6MTc2ODIzNzg2OX0.RmcJgZM22PIeehBESlatiJv5vfDHBEaaiPz3kHsL78Q', 'signedUrl': 'https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/7a15605c-1f0f-42ec-a70a-528e1202240e_MMG%20Back.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL2VlN2VhYmFlLTMyMTQtNDM2NC04ZTQ4LTEyYjhmZmMwNTMyYS8yMDI1LzEyLzIzLzdhMTU2MDVjLTFmMGYtNDJlYy1hNzBhLTUyOGUxMjAyMjQwZV9NTUcgQmFjay5wbmciLCJpYXQiOjE3NjgxNTE0NjksImV4cCI6MTc2ODIzNzg2OX0.RmcJgZM22PIeehBESlatiJv5vfDHBEaaiPz3kHsL78Q'}
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Signed URL generated (length: 534)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Extracted JWT token (length: 356)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ===== JWT TOKEN ANALYSIS =====
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Full JWT claims: {
[01:11:09] [Sales] INFO:   "url": "uploads/ee7eabae-3214-4364-8e48-12b8ffc0532a/2025/12/23/7a15605c-1f0f-42ec-a70a-528e1202240e_MMG Back.png",
[01:11:09] [Sales] INFO:   "iat": 1768151469,
[01:11:09] [Sales] INFO:   "exp": 1768237869
[01:11:09] [Sales] INFO: }
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Current server time: 1768151469 (2026-01-11T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Token issued at (iat): 1768151469 (2026-01-11T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Token expires at (exp): 1768237869 (2026-01-12T17:11:09+00:00)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Time until expiry: 86400s (24.00 hours)
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Time since token issued: 0s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Expected exp (server_time + 86400): 1768237869
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] Actual exp drift from expected: 0s
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ✅ Token appears valid and will expire in 24.00 hours
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST END ==========
[01:11:09] [Sales] INFO: 21:11:09 INFO     [8e5d3420] proposal-bot: [STORAGE:SUPABASE] ========== SIGNED URL REQUEST START ==========

end #Error04