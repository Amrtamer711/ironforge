# Frontend Requirements for Amr

---

## DEV TO-DO: Unified Asset Management

# - [ ] Make the changes to mockup and proposal generation LLM chats with new location structure.

# - [ ] Lazy Load Chat Messages so that the user is not stuck with loading conversations after login (Clarify if reducing the no of chats loaded will have positive impact).

- [ ] Chat history displaying the First 500 messages only, not the latest messages.

- [ ] Issue with the proposal series matching.

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
2. Ensure most functionality and llm functionality are equivalent

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


- Cache Situation - mockup template create/update/delete does not reflect immediately in template list;
Issue: mockup template create/update/delete does not reflect immediately in template list; inconsistent eventual updates.
Repro (create): create indoor template for Galleria Extension Indoor and outdoor/day/gold for Galleria Extension Outdoor; save succeeds but templates API returns empty for those params right after save.
Repro (create): DNA04 outdoor/day/gold not present → create and save → immediate re‑fetch with same params still returns empty; later (after navigating elsewhere) DNA04 template appears, but Galleria templates still missing even after waiting.
Logs: save calls return success; subsequent templates calls return empty array; no errors in logs.
Delete behavior: deletions are delayed/inconsistent; dna02_01.jpg remains after delete; later delete attempt removes dna02_04.jpg instead; still no errors in logs.

Multiple file upload to Mockup generate Generate 