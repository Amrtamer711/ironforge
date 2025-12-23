# CRM Architecture Audit

**Date:** 2025-12-22
**Purpose:** Complete audit of Sales-Module and Asset-Management architecture before cleanup/refactoring

---

## Executive Summary

This audit documents the current state of the CRM's microservices architecture, focusing on the Sales-Module and Asset-Management services. The goal is to identify fragmentation, integration gaps, and inconsistencies before implementing a systematic cleanup.

**Key Findings:**
1. ✅ Multi-tenant architecture successfully implemented in both services
2. ⚠️ Sales-Module still queries **local DB for locations** instead of Asset-Management API
3. ⚠️ Mockup and proposal code is **fragmented** across multiple files
4. ⚠️ **Inconsistent access control patterns** (proposals use user_id, mockups use user.companies)
5. ⚠️ Eligibility checking system exists but **not actively used** in workflows
6. ✅ Asset-Management API is complete and ready for integration
7. ⚠️ No unified workflow orchestration between AI chat and form-based interfaces

---

## 1. Module Resource Ownership

### 1.1 Asset-Management Service (Port 8001)

**Purpose:** Centralized asset inventory and availability management

**What it stores:**

| Entity | Schema Location | Description |
|--------|----------------|-------------|
| **Networks** | `{company}.networks` | Sellable groupings of assets (e.g., "Abu Dhabi Highways") |
| **Asset Types** | `{company}.asset_types` | Categories within networks (NOT sellable) |
| **Locations** | `{company}.locations` (combines network_assets + standalone_assets) | Individual sellable assets (billboards, screens) |
| **Packages** | `{company}.packages`, `{company}.package_items` | Company-specific bundles of networks/assets |
| **Asset Photos** | `{company}.asset_photos` | Real billboard photos (table defined, endpoints NOT implemented) |
| **Asset Occupations** | `{company}.asset_occupations` | Booking/availability tracking (table defined, endpoints NOT implemented) |
| **Companies** | `public.companies` | Company hierarchy (MMG → Backlite → subsidiaries) |

**Schemas:**
- `backlite_dubai`
- `backlite_uk`
- `backlite_abudhabi`
- `viola`
- `public` (cross-company data)

**What it does NOT store:**
- ❌ Mockup frames (stays in Sales-Module)
- ❌ Rate cards (stays in Sales-Module)
- ❌ Proposals (stays in Sales-Module)
- ❌ Booking orders (stays in Sales-Module)
- ❌ Chat sessions (stays in Sales-Module)

---

### 1.2 Sales-Module Service (Port 8000)

**Purpose:** Sales workflows (proposals, mockups, bookings, AI chat)

**What it stores:**

| Entity | Schema Location | Description |
|--------|----------------|-------------|
| **Proposals** | `public.proposals_log` | Generated proposals with financial calculations |
| **Proposal Locations** | `public.proposal_locations` | Junction table to locations |
| **Booking Orders** | `public.booking_orders` | Parsed booking orders |
| **Mockup Files** | `public.mockup_files` | Generated mockup images |
| **Chat Sessions** | `public.chat_sessions`, `public.chat_messages` | AI chat history |
| **Mockup Frames** | `{company}.mockup_frames` | Billboard photo + frame coordinates for warping |
| **Mockup Usage** | `{company}.mockup_usage` | Mockup generation audit trail |
| **Location Photos** | `{company}.location_photos` | Real billboard photos (for mockup warping) |
| **Rate Cards** | `{company}.rate_cards` | Pricing data for proposals |
| **Locations (DUPLICATE)** | `{company}.locations` | ⚠️ **Duplicate of Asset-Management locations** |

**Schemas:**
- Same as Asset-Management: `backlite_dubai`, `backlite_uk`, `backlite_abudhabi`, `viola`
- `public` (cross-company data)

**⚠️ PROBLEM: Location data duplication**
- Sales-Module has local copies of `{company}.locations` tables
- Asset-Management has authoritative `{company}.locations` tables
- **No synchronization mechanism** - data can diverge
- Sales-Module should query Asset-Management API, not local DB

---

## 2. Current Integration Status

### 2.1 Asset-Management Client (Ready but Not Active)

**File:** [src/sales-module/clients/asset_management.py](../src/sales-module/clients/asset_management.py)

**Available Methods:**
```python
asset_mgmt_client = AssetManagementClient()

# Location queries
locations = asset_mgmt_client.get_locations(companies=["backlite_dubai"], network_id=123)
location = asset_mgmt_client.get_location(company="backlite_dubai", location_id=456)
location = asset_mgmt_client.get_location_by_key(location_key="sheikh_zayed_rd_01", companies=user.companies)

# Eligibility checks
is_eligible = asset_mgmt_client.check_location_eligibility(company="backlite_dubai", location_id=456, service="mockup_generator")
eligible_locations = asset_mgmt_client.get_eligible_locations(service="proposal_generator", companies=user.companies)

# Package expansion
locations = asset_mgmt_client.expand_to_locations([
    {"type": "network", "id": 1, "company": "backlite_dubai"},
    {"type": "asset", "id": 42, "company": "viola"}
])
```

**Authentication:** JWT-based service-to-service auth via `ServiceAuthClient`

**Status:** ✅ Fully implemented, ⚠️ NOT actively used in mockup/proposal workflows

---

### 2.2 Where Sales-Module SHOULD Use Asset-Management API (But Doesn't)

| File | Line | Current Behavior | Should Be |
|------|------|------------------|-----------|
| [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) | 63 | `db.get_locations_for_companies(user.companies)` | `asset_mgmt_client.get_locations(companies=user.companies)` |
| [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) | 145 | `db.get_location_by_key(location_key, user.companies)` | `asset_mgmt_client.get_location_by_key(location_key, companies=user.companies)` |
| [api/routers/proposals.py](../src/sales-module/api/routers/proposals.py) | N/A | No location queries (relies on proposal_locations junction) | Should use asset_mgmt_client for location details |
| [db/backends/supabase.py](../src/sales-module/db/backends/supabase.py) | 1911-1931 | `get_locations_for_companies()` - queries local DB | Should be deprecated in favor of API client |

**⚠️ CRITICAL FINDING:** Sales-Module never calls Asset-Management API for location data in production workflows

---

### 2.3 Cross-Service Data Validation (Partially Implemented)

Asset-Management checks Sales-Module schemas for eligibility:

**File:** [src/asset-management/services/eligibility.py](../src/asset-management/services/eligibility.py)

```python
# Check if location has rate card (for proposal eligibility)
def _has_rate_card(location_id: int, company: str) -> bool:
    try:
        result = db.client.schema(company).table("rate_cards").select("id").eq("location_id", location_id).execute()
        return len(result.data) > 0
    except Exception:
        return True  # ⚠️ Default to True if table doesn't exist

# Check if location has mockup frame (for mockup eligibility)
def _has_mockup_frame(location_id: int, company: str) -> bool:
    try:
        result = db.client.schema(company).table("mockup_frames").select("id").eq("location_id", location_id).execute()
        return len(result.data) > 0
    except Exception:
        return True  # ⚠️ Default to True if table doesn't exist
```

**Status:**
- ✅ Cross-schema queries implemented
- ⚠️ Graceful degradation (returns True if tables missing)
- ⚠️ No real-time synchronization
- ⚠️ Eligibility API exists but not used by Sales-Module workflows

---

## 3. Code Fragmentation Analysis

### 3.1 Mockup Generation Code

**Problem:** Mockup functionality split across 6+ files with overlapping responsibilities

| File | Purpose | Lines | Responsibility Overlap |
|------|---------|-------|----------------------|
| [generators/mockup.py](../src/sales-module/generators/mockup.py) | Core warping engine | 420 | ✅ Clean (single responsibility) |
| [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) | Form-based UI endpoints | 627 | ⚠️ Contains business logic (frame validation, preview generation) |
| [routers/mockup_handler.py](../src/sales-module/routers/mockup_handler.py) | AI chat workflow orchestration | 350 | ⚠️ Duplicates mockup generation logic |
| [core/tools.py](../src/sales-module/core/tools.py) | LLM tool definitions | 15 (tool def) | ⚠️ Thin wrapper, actual logic in mockup_handler |
| [generators/effects/compositor.py](../src/sales-module/generators/effects/compositor.py) | Perspective warping | 200 | ✅ Clean (single responsibility) |
| [generators/effects/edge.py](../src/sales-module/generators/effects/edge.py) | Edge blending | 150 | ✅ Clean (single responsibility) |

**Identified Issues:**
1. **Dual workflow implementations:**
   - Form-based: [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) → `generators/mockup.py`
   - AI chat: [routers/mockup_handler.py](../src/sales-module/routers/mockup_handler.py) → `generators/mockup.py`
   - 🔴 **Business logic duplicated** (eligibility, file handling, storage)

2. **Business logic in API layer:**
   - [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) contains frame validation, preview generation
   - Should be extracted to service layer

3. **No unified orchestration:**
   - Each workflow (form, AI chat) has its own orchestration code
   - No shared `MockupService` class

**Recommendation:** Consolidate into modular structure:
```
services/
  mockup_service.py      # Unified business logic
generators/
  mockup.py              # Core warping (keep as-is)
  effects/               # Effects modules (keep as-is)
api/routers/
  mockups.py             # Thin API layer (calls mockup_service)
routers/
  mockup_handler.py      # Thin AI chat handler (calls mockup_service)
```

---

### 3.2 Proposal Generation Code

**Problem:** Proposal functionality split across 4+ files with duplicated financial logic

| File | Purpose | Lines | Responsibility Overlap |
|------|---------|-------|----------------------|
| [core/proposals.py](../src/sales-module/core/proposals.py) | Core proposal generation | 450 | ⚠️ Contains API logic (file serving, DB saves) |
| [api/routers/proposals.py](../src/sales-module/api/routers/proposals.py) | CRUD endpoints | 200 | ✅ Clean (list/get/delete only) |
| [core/tools.py](../src/sales-module/core/tools.py) | LLM tool definitions | 100 (2 tools) | ⚠️ Contains business logic (parameter parsing, validation) |
| [generators/pdf.py](../src/sales-module/generators/pdf.py) | PDF operations | 150 | ✅ Clean (single responsibility) |
| [generators/pptx.py](../src/sales-module/generators/pptx.py) | PPTX financial slide generation | 200 | ✅ Clean (single responsibility) |

**Identified Issues:**
1. **Business logic in LLM tools:**
   - [core/tools.py](../src/sales-module/core/tools.py) contains parameter validation, currency conversion
   - Should be delegated to service layer

2. **No separation of concerns:**
   - [core/proposals.py](../src/sales-module/core/proposals.py) handles:
     - Financial calculations
     - Template rendering
     - File I/O
     - Database operations
     - Supabase storage
   - 🔴 **Should be split into multiple classes**

3. **Dual workflow implementations:**
   - AI chat: [core/tools.py](../src/sales-module/core/tools.py) → [core/proposals.py](../src/sales-module/core/proposals.py)
   - Direct API: Frontend → [api/routers/proposals.py](../src/sales-module/api/routers/proposals.py) (list/get only, no create)
   - 🔴 **No unified creation endpoint** (only AI chat can create proposals)

**Recommendation:** Consolidate into modular structure:
```
services/
  proposal_service.py         # Unified business logic
  financial_calculator.py     # Financial calculations
  template_renderer.py        # PPTX/PDF rendering
generators/
  pdf.py                      # PDF operations (keep as-is)
  pptx.py                     # PPTX operations (keep as-is)
api/routers/
  proposals.py                # CRUD endpoints (add POST)
core/
  tools.py                    # Thin wrappers (delegate to service)
```

---

### 3.3 AI Chat Integration

**Problem:** Tool definitions contain business logic instead of being thin wrappers

**File:** [core/tools.py](../src/sales-module/core/tools.py)

**Current Structure:**
```python
def get_base_tools():
    return [
        {
            "name": "get_separate_proposals",
            "description": "...",  # 47 lines of business logic
            "input_schema": {...},
        },
        {
            "name": "get_combined_proposal",
            "description": "...",  # 43 lines of business logic
            "input_schema": {...},
        },
        {
            "name": "generate_mockup",
            "description": "...",  # 12 lines of orchestration
            "input_schema": {...},
        },
        # ... 3 more tools
    ]
```

**Issues:**
1. Tool definitions ≠ tool implementations (confusing)
2. [core/llm.py](../src/sales-module/core/llm.py) `main_llm_loop()` manually routes tool calls:
   ```python
   if tool_name == "generate_mockup":
       from routers.mockup_handler import handle_mockup_generation
       await handle_mockup_generation(...)
   elif tool_name == "get_separate_proposals":
       from core.proposals import process_proposals
       result = await process_proposals(...)
   ```
3. No abstraction - adding new tool requires modifying `main_llm_loop()`

**Recommendation:**
- Create `ToolRegistry` pattern
- Move tool implementations to service classes
- Use dependency injection for tool handlers

---

## 4. Access Control Analysis

### 4.1 Multi-Tenant Filtering Patterns

**Pattern 1: Company-based filtering (Mockups, Locations)**

✅ **Implemented in:**
- [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) - All endpoints check `user.companies`
- [db/backends/supabase.py](../src/sales-module/db/backends/supabase.py) - `_query_schemas()` filters by accessible schemas
- Asset-Management - All endpoints filter by `user.companies`

**How it works:**
```python
@router.get("/api/mockup/locations")
async def get_mockup_locations(user: AuthUser = Depends(require_permission("sales:mockups:read"))):
    # Line 56-60: Check user has any company access
    if not user.has_company_access:
        raise HTTPException(status_code=403, detail="No company access")

    # Line 63: Query only accessible company schemas
    db_locations = db.get_locations_for_companies(user.companies)
    return {"locations": sorted(locations, key=lambda x: x["name"])}
```

**Company hierarchy support:**
- Database functions: `get_company_and_children()`, `get_accessible_schemas()`
- NOT actively used in Sales-Module (queries leaf companies only)
- ⚠️ **Users assigned to "Backlite" group should see Dubai + UK + Abu Dhabi locations**

---

**Pattern 2: User-based filtering (Proposals)**

✅ **Implemented in:**
- [api/routers/proposals.py](../src/sales-module/api/routers/proposals.py)

**How it works:**
```python
@router.get("/api/proposals")
async def list_proposals(user: AuthUser = Depends(require_permission("sales:proposals:read"))):
    # Get accessible user IDs based on hierarchy
    if has_permission(user.permissions, "sales:proposals:manage"):
        accessible_users = ["*"]  # Admin sees all
    else:
        accessible_users = get_accessible_user_ids(user.id, user.permissions)

    proposals = db.get_proposals(user_ids=accessible_users)
    return {"proposals": proposals}
```

**⚠️ INCONSISTENCY:**
- Proposals use `user_id` filtering (owner + subordinates)
- Mockups use `user.companies` filtering
- **No company-based access control for proposals** - user can see proposals for locations they don't have access to

---

### 4.2 Access Control Gaps

| Entity | Current Filtering | Missing |
|--------|------------------|---------|
| **Locations** | ✅ `user.companies` | ⚠️ No hierarchy expansion (groups → leaf companies) |
| **Mockups** | ✅ `user.companies` | ⚠️ No hierarchy expansion |
| **Proposals** | ✅ `user_id` + team hierarchy | 🔴 **No company filtering** |
| **Booking Orders** | ✅ `user_id` + team hierarchy | 🔴 **No company filtering** |
| **Chat Sessions** | ✅ `user_id` | 🔴 **No company filtering** |
| **Networks** | ✅ `user.companies` (Asset-Management) | ✅ Fully implemented |
| **Packages** | ✅ `user.companies` (Asset-Management) | ✅ Fully implemented |

**Critical Gap:**
Proposals/BOs created for Location A (backlite_dubai) are visible to users without backlite_dubai access if they belong to the same team.

**Recommended Fix:**
Add company-based filtering to proposals:
```python
proposals = db.get_proposals(
    user_ids=accessible_users,
    companies=user.companies  # Add this
)
```

---

### 4.3 Eligibility Checking (Not Actively Used)

**Available but unused:**
- Asset-Management: `/api/eligibility/check/{company}/{location_id}`
- Asset-Management: `/api/eligibility/eligible-locations?service=mockup_generator`
- Sales-Module client: `asset_mgmt_client.check_location_eligibility()`

**Where it SHOULD be used:**

| Workflow | Current Behavior | Should Be |
|----------|------------------|-----------|
| **Mockup Form** | Shows all locations from `user.companies` | Pre-filter to only show locations with `template_path` + `mockup_frame` |
| **Mockup AI Chat** | No eligibility check before generation | Post-check: "Sorry, Sheikh Zayed Rd 01 doesn't have a mockup frame configured yet" |
| **Proposal Form** | Shows all locations from `user.companies` | Pre-filter to only show locations with active rate card |
| **Proposal AI Chat** | No eligibility check before generation | Post-check: "Sorry, this location doesn't have pricing configured" |

**Recommended Pattern:**
- **Forms (Pre-filter):** Only show eligible locations in dropdowns
  ```python
  eligible = asset_mgmt_client.get_eligible_locations(service="mockup_generator", companies=user.companies)
  ```

- **AI Chat (Post-check):** Check eligibility after user asks, provide helpful error
  ```python
  check = asset_mgmt_client.check_location_eligibility(company, location_id, service="mockup_generator")
  if not check["eligible"]:
      return f"Sorry, this location is missing: {', '.join(check['missing_fields'])}"
  ```

---

## 5. Workflow Pattern Analysis

### 5.1 Form-based Workflows

**Mockup Setup:**
- **Endpoint:** `GET /mockup` - Serves HTML admin interface
- **Flow:**
  1. Select location from dropdown (filtered by `user.companies`)
  2. Upload billboard photo
  3. Interactively draw frame corners
  4. Configure effects (edge blur, brightness)
  5. Test preview in real-time (`POST /api/mockup/test-preview`)
  6. Save frame configuration (`POST /api/mockup/save-frame`)

**Mockup Generation:**
- **Endpoint:** `POST /api/mockup/generate`
- **Flow:**
  1. Select location (filtered by `user.companies`)
  2. Upload creative OR use AI generation
  3. Generate mockup
  4. Return Supabase storage URL

**Proposal Viewing:**
- **Endpoint:** `GET /api/proposals`
- **Flow:**
  1. List proposals (filtered by `user_id` + team)
  2. Download PPTX/PDF from Supabase storage

**⚠️ No form-based proposal CREATION** (only via AI chat)

---

### 5.2 AI Chat Workflows

**Central Orchestrator:** [core/llm.py](../src/sales-module/core/llm.py) `main_llm_loop()`

**Channel-Agnostic Design:**
- WebAdapter (web UI chat)
- SlackAdapter (Slack bot)
- Unified processing via adapters

**Tool Execution Flow:**
```
User message
  ↓
Chat API (web) or Slack API
  ↓
main_llm_loop(companies=user.companies)
  ↓
Claude decides tool to use
  ↓
Tool router (if/elif chain)
  ↓
Tool handler (mockup_handler.py, proposals.py, etc.)
  ↓
Generator (mockup.py, pptx.py, pdf.py)
  ↓
Return result to LLM
  ↓
LLM generates response
  ↓
Stream to user (SSE)
```

**Available Tools:**
1. `generate_mockup` - Upload, AI generation, or follow-up (reuse creative)
2. `get_separate_proposals` - Multiple locations, multiple duration/rate options each
3. `get_combined_proposal` - Package deal with single net rate
4. `parse_booking_order` - Extract structured data from BO email/PDF
5. `list_locations` - Explicitly list available locations

**Streaming Support:**
- Server-Sent Events (SSE) for real-time responses
- Progress updates during long-running operations (mockup generation)
- File URLs streamed as they're generated

---

### 5.3 Workflow Inconsistencies

| Feature | Form-based | AI Chat | Issue |
|---------|-----------|---------|-------|
| **Mockup Creation** | ✅ POST /api/mockup/generate | ✅ generate_mockup tool | ✅ Both implemented |
| **Proposal Creation** | ❌ No endpoint | ✅ get_separate_proposals, get_combined_proposal tools | 🔴 **Only AI chat can create proposals** |
| **Eligibility Checking** | ❌ Shows all locations | ❌ No eligibility check | 🔴 **Neither workflow checks eligibility** |
| **Company Filtering** | ✅ Pre-filtered by user.companies | ✅ Passed to main_llm_loop | ✅ Consistent |
| **Location Source** | 🔴 Local DB | 🔴 Local DB | 🔴 **Both should use Asset-Management API** |

**Recommendation:**
1. Add `POST /api/proposals/generate` endpoint for form-based proposal creation
2. Implement eligibility pre-filtering for form dropdowns
3. Implement eligibility post-checking in AI chat
4. Migrate both workflows to use Asset-Management API

---

## 6. Database Architecture

### 6.1 Multi-Schema Design

**Shared Pattern (Sales-Module + Asset-Management):**
```
public/
  companies          # Company hierarchy (MMG → Backlite → backlite_dubai, etc.)
  proposals_log      # Cross-company proposals
  booking_orders     # Cross-company BOs
  chat_sessions      # Cross-company chat history

backlite_dubai/
  locations          # Dubai assets
  mockup_frames      # Dubai mockup configs
  rate_cards         # Dubai pricing

backlite_uk/
  locations          # UK assets
  mockup_frames      # UK mockup configs
  rate_cards         # UK pricing

backlite_abudhabi/
  locations          # Abu Dhabi assets
  mockup_frames      # Abu Dhabi mockup configs
  rate_cards         # Abu Dhabi pricing

viola/
  locations          # Viola assets
  mockup_frames      # Viola mockup configs
  rate_cards         # Viola pricing
```

**Access Control Functions:**
```sql
-- Recursive company tree
get_company_and_children(company_id) → [company_ids]

-- Expand groups to schemas
get_accessible_schemas(company_ids[]) → [schema_names]

-- Per-company schema creation
create_company_asset_schema(company_code)
```

**⚠️ PROBLEM: Data Duplication**
Both services have identical `{company}.locations` tables with no synchronization.

---

### 6.2 Cross-Service Data Dependencies

**Asset-Management queries Sales-Module schemas:**
```python
# Check if location has rate card (proposal eligibility)
supabase.schema("backlite_dubai").table("rate_cards").select("id").eq("location_id", location_id)

# Check if location has mockup frame (mockup eligibility)
supabase.schema("backlite_dubai").table("mockup_frames").select("id").eq("location_id", location_id)
```

**Issues:**
1. ⚠️ Tight coupling between services at DB level
2. ⚠️ No API boundaries for cross-service data access
3. ⚠️ Graceful degradation hides missing data (returns True if table doesn't exist)

**Recommendation:**
- Sales-Module should expose `/api/internal/location-eligibility` endpoint
- Asset-Management should call API instead of querying DB directly
- Use service-to-service JWT auth

---

## 7. Security Architecture

### 7.1 Two-Layer Authentication

**Layer 1: User-Facing Requests (Unified-UI → Backend)**

**Middleware:** `TrustedUserMiddleware` (crm_security SDK)

**Headers:**
```
X-Proxy-Secret: {PROXY_SECRET}           # Service authentication
X-User-Id: user123                        # User identity
X-User-Email: john@example.com
X-User-Name: John Doe
X-User-Profile: sales_rep
X-User-Permissions: ["sales:mockups:read", "sales:proposals:read", ...]
X-User-Permission-Sets: ["sales_rep"]
X-User-Teams: ["dubai_sales"]
X-User-Companies: ["backlite_dubai", "viola"]  # Multi-tenant access
```

**Validation:**
1. Check `X-Proxy-Secret` matches `PROXY_SECRET` env var
2. If trusted headers present without valid secret → 403 Forbidden
3. Extract user context into `request.state.trusted_user`
4. Available to endpoints via `Depends(require_permission(...))`

---

**Layer 2: Service-to-Service Requests**

**Authentication:** JWT tokens via `ServiceAuthClient` (crm_security SDK)

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
X-Service-Name: sales-module
```

**JWT Payload:**
```json
{
  "service": "sales-module",
  "type": "service",
  "iat": 1703260800,
  "exp": 1703261100  // 5 minute expiry
}
```

**Validation:**
1. Verify JWT signature using `INTER_SERVICE_SECRET`
2. Check `type == "service"`
3. Check expiry
4. Return service name to endpoint

---

### 7.2 Authorization (RBAC)

**Permission Format:** `{resource}:{entity}:{action}`

**Examples:**
- `sales:mockups:read` - View mockup setup interface
- `sales:mockups:create` - Generate mockups
- `sales:proposals:read` - View proposals
- `sales:proposals:manage` - Admin access (see all users' proposals)
- `assets:networks:read` - View networks
- `assets:locations:create` - Add new locations

**Permission Checking:**
```python
@router.get("/api/mockup/locations")
async def get_locations(user: AuthUser = Depends(require_permission("sales:mockups:read"))):
    # user.permissions = ["sales:mockups:read", "sales:mockups:create", ...]
    # user.companies = ["backlite_dubai", "viola"]
    ...
```

**Combined Authorization:**
1. Check permission (RBAC)
2. Check company access (multi-tenant RLS)

**Example:**
```python
# User has permission sales:mockups:read
# User has companies ["backlite_dubai"]
# Tries to access viola location
→ 403 Forbidden (no company access)
```

---

## 8. Deployment Architecture

### 8.1 Service Topology

```
┌─────────────────────────────────────────────┐
│          Unified-UI (Port 3000)             │
│  - API Gateway                               │
│  - Proxy Router                              │
│  - User Authentication (Supabase Auth)       │
│  - Trusted Headers Injection                 │
└─────────────────────────────────────────────┘
                    │
          ┌─────────┴─────────┐
          │                   │
          ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│  Sales-Module    │  │ Asset-Management │
│  (Port 8000)     │  │  (Port 8001)     │
│  - Proposals     │  │  - Networks      │
│  - Mockups       │  │  - Locations     │
│  - BOs           │  │  - Packages      │
│  - AI Chat       │  │  - Eligibility   │
│  - Rate Cards    │  │                  │
│  - Mockup Frames │  │                  │
└──────────────────┘  └──────────────────┘
          │                   │
          │    ⚠️ SHOULD      │
          │    INTEGRATE      │
          │    (currently     │
          │     doesn't)      │
          │                   │
          └─────────┬─────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         Security-Service (Port 8003)        │
│  - Audit Logging                             │
│  - Permission Management (future)            │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         Supabase (PostgreSQL + Auth)        │
│  - Sales-Module DB (multi-schema)            │
│  - Asset-Management DB (multi-schema)        │
│  - Security-Service DB                       │
│  - File Storage (mockups, proposals)         │
└─────────────────────────────────────────────┘
```

---

### 8.2 Environment Configuration

**Sales-Module:**
- `DATABASE_URL` - Supabase connection string
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` - Supabase SDK
- `PROXY_SECRET` - Trusted header validation
- `INTER_SERVICE_SECRET` - Service-to-service JWT
- `SERVICE_NAME=sales-module`
- `COMPANY_SCHEMAS=backlite_dubai,backlite_uk,backlite_abudhabi,viola`
- `OPENAI_API_KEY` - AI creative generation
- `ANTHROPIC_API_KEY` - Claude LLM

**Asset-Management:**
- `DATABASE_URL` - Supabase connection string (separate DB)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- `PROXY_SECRET` - Trusted header validation
- `INTER_SERVICE_SECRET` - Service-to-service JWT
- `SERVICE_NAME=asset-management`
- `COMPANY_SCHEMAS=backlite_dubai,backlite_uk,backlite_abudhabi,viola`

**Security-Service:**
- `DATABASE_URL` - Supabase connection string (separate DB)
- `PROXY_SECRET` - Trusted header validation
- `SERVICE_NAME=security-service`

---

## 9. Key Problems Identified

### 9.1 Critical Issues (Must Fix)

1. **🔴 Location Data Duplication**
   - Sales-Module queries local `{company}.locations` tables
   - Asset-Management has authoritative location data
   - No synchronization mechanism
   - **Impact:** Data can diverge, Asset-Management updates not reflected in Sales-Module
   - **Files affected:**
     - [src/sales-module/api/routers/mockups.py](../src/sales-module/api/routers/mockups.py):63, 145
     - [src/sales-module/db/backends/supabase.py](../src/sales-module/db/backends/supabase.py):1911-1931
   - **Fix:** Replace all `db.get_locations_*()` calls with `asset_mgmt_client.get_locations()`

2. **🔴 Fragmented Mockup Code**
   - Business logic duplicated across form and AI chat workflows
   - No unified `MockupService` class
   - API layer contains business logic
   - **Impact:** Hard to maintain, inconsistent behavior
   - **Files affected:**
     - [src/sales-module/api/routers/mockups.py](../src/sales-module/api/routers/mockups.py)
     - [src/sales-module/routers/mockup_handler.py](../src/sales-module/routers/mockup_handler.py)
     - [src/sales-module/core/tools.py](../src/sales-module/core/tools.py)
   - **Fix:** Extract to `services/mockup_service.py`

3. **🔴 Fragmented Proposal Code**
   - Financial calculations, template rendering, file I/O, DB operations all in one file
   - Tool definitions contain business logic
   - No form-based proposal creation endpoint
   - **Impact:** Hard to test, hard to extend
   - **Files affected:**
     - [src/sales-module/core/proposals.py](../src/sales-module/core/proposals.py)
     - [src/sales-module/core/tools.py](../src/sales-module/core/tools.py)
   - **Fix:** Split into `services/proposal_service.py`, `services/financial_calculator.py`, `services/template_renderer.py`

4. **🔴 No Eligibility Checking in Workflows**
   - Asset-Management eligibility API exists but unused
   - Users can request mockups for locations without frames
   - Users can request proposals for locations without rate cards
   - **Impact:** Confusing error messages, wasted computation
   - **Fix:**
     - Forms: Pre-filter with `asset_mgmt_client.get_eligible_locations()`
     - AI Chat: Post-check with `asset_mgmt_client.check_location_eligibility()`

---

### 9.2 Moderate Issues (Should Fix)

5. **⚠️ Inconsistent Access Control**
   - Proposals use `user_id` + team filtering
   - Mockups use `user.companies` filtering
   - No company-based access control for proposals
   - **Impact:** Users can see proposals for locations they don't have access to
   - **Fix:** Add `companies` filtering to proposal queries

6. **⚠️ No Company Hierarchy Expansion**
   - Users assigned to "Backlite" group should see Dubai + UK + Abu Dhabi
   - Currently queries leaf companies only
   - Database functions exist (`get_accessible_schemas()`) but not used
   - **Impact:** Managers must be assigned to each subsidiary individually
   - **Fix:** Call `get_accessible_schemas()` before querying

7. **⚠️ Tool Registry Pattern Missing**
   - `main_llm_loop()` uses if/elif chain for tool routing
   - Adding new tool requires modifying core LLM code
   - **Impact:** Hard to extend, hard to test
   - **Fix:** Create `ToolRegistry` with dependency injection

8. **⚠️ Cross-Service DB Queries**
   - Asset-Management queries Sales-Module schemas directly
   - Violates service boundaries
   - **Impact:** Tight coupling, hard to scale independently
   - **Fix:** Sales-Module exposes `/api/internal/location-eligibility` endpoint

---

### 9.3 Minor Issues (Nice to Have)

9. **⚡ No Form-based Proposal Creation**
   - Only AI chat can create proposals
   - No `POST /api/proposals/generate` endpoint
   - **Impact:** Users must use AI chat for proposals
   - **Fix:** Add form-based endpoint

10. **⚡ Asset Photos/Occupations Not Implemented**
    - `asset_photos` and `asset_occupations` tables defined but no endpoints
    - **Impact:** Availability calendar can't be built
    - **Fix:** Implement CRUD endpoints in Asset-Management

---

## 10. Recommendations

### 10.1 Immediate Actions (Week 1)

1. **Migrate Location Queries to Asset-Management API**
   - Replace all `db.get_locations_*()` with `asset_mgmt_client.get_locations()`
   - Test thoroughly (mockup form, proposal generation, AI chat)
   - Remove local `{company}.locations` tables from Sales-Module schema

2. **Implement Eligibility Checking**
   - Forms: Pre-filter location dropdowns
   - AI Chat: Post-check with helpful error messages
   - Use `asset_mgmt_client.get_eligible_locations()` and `asset_mgmt_client.check_location_eligibility()`

3. **Add Company Filtering to Proposals**
   - Update `db.get_proposals()` to accept `companies` parameter
   - Filter proposal_locations by accessible companies
   - Ensure users can't see proposals for unauthorized companies

---

### 10.2 Short-term Refactoring (Week 2-3)

4. **Consolidate Mockup Code**
   - Create `services/mockup_service.py` with unified business logic
   - Thin wrappers in `api/routers/mockups.py` and `routers/mockup_handler.py`
   - Extract eligibility, file handling, storage to service layer

5. **Consolidate Proposal Code**
   - Split `core/proposals.py` into:
     - `services/proposal_service.py` - Orchestration
     - `services/financial_calculator.py` - Financial calculations
     - `services/template_renderer.py` - PPTX/PDF generation
   - Add `POST /api/proposals/generate` endpoint for forms

6. **Implement Company Hierarchy Expansion**
   - Call `get_accessible_schemas()` before location queries
   - Support group assignments (MMG, Backlite)
   - Update `user.companies` to include expanded schemas

---

### 10.3 Long-term Architecture (Month 2+)

7. **Decouple Cross-Service DB Access**
   - Sales-Module exposes `/api/internal/location-eligibility`
   - Asset-Management calls API instead of querying DB
   - Use service-to-service JWT auth

8. **Implement Tool Registry Pattern**
   - Create `ToolRegistry` class with `register()` and `execute()` methods
   - Move tool handlers to service classes
   - Dependency injection for tool execution

9. **Availability Calendar Implementation**
   - Implement `asset_occupations` CRUD endpoints
   - Build availability checking logic
   - Integrate with proposal generation (conflict detection)

10. **Real-time Synchronization**
    - Consider event-driven architecture (pub/sub)
    - Asset-Management publishes events (location created, updated, deleted)
    - Sales-Module subscribes and updates caches

---

## Appendix A: File Inventory

### Sales-Module Files

**API Routers:**
- [api/routers/mockups.py](../src/sales-module/api/routers/mockups.py) - Mockup form endpoints (627 lines)
- [api/routers/proposals.py](../src/sales-module/api/routers/proposals.py) - Proposal CRUD (200 lines)
- [api/routers/chat.py](../src/sales-module/api/routers/chat.py) - Web chat endpoints (250 lines)

**Core Business Logic:**
- [core/proposals.py](../src/sales-module/core/proposals.py) - Proposal generation (450 lines)
- [core/llm.py](../src/sales-module/core/llm.py) - AI chat orchestration (600 lines)
- [core/tools.py](../src/sales-module/core/tools.py) - LLM tool definitions (250 lines)
- [core/chat_api.py](../src/sales-module/core/chat_api.py) - Chat API wrapper (200 lines)

**AI Chat Handlers:**
- [routers/mockup_handler.py](../src/sales-module/routers/mockup_handler.py) - Mockup AI workflow (350 lines)

**Generators:**
- [generators/mockup.py](../src/sales-module/generators/mockup.py) - Mockup warping engine (420 lines)
- [generators/pdf.py](../src/sales-module/generators/pdf.py) - PDF operations (150 lines)
- [generators/pptx.py](../src/sales-module/generators/pptx.py) - PPTX generation (200 lines)
- [generators/effects/compositor.py](../src/sales-module/generators/effects/compositor.py) - Warping (200 lines)
- [generators/effects/edge.py](../src/sales-module/generators/effects/edge.py) - Edge blending (150 lines)

**Database:**
- [db/backends/supabase.py](../src/sales-module/db/backends/supabase.py) - Supabase backend (2000+ lines)
- [db/backends/sqlite.py](../src/sales-module/db/backends/sqlite.py) - SQLite backend (1500+ lines)

**Clients:**
- [clients/asset_management.py](../src/sales-module/clients/asset_management.py) - Asset-Management API client (406 lines)

---

### Asset-Management Files

**API Routers:**
- [api/routers/networks.py](../src/asset-management/api/routers/networks.py) - Networks CRUD
- [api/routers/asset_types.py](../src/asset-management/api/routers/asset_types.py) - Asset types CRUD
- [api/routers/locations.py](../src/asset-management/api/routers/locations.py) - Locations CRUD
- [api/routers/packages.py](../src/asset-management/api/routers/packages.py) - Packages CRUD
- [api/routers/eligibility.py](../src/asset-management/api/routers/eligibility.py) - Eligibility checking

**Services:**
- [services/networks.py](../src/asset-management/services/networks.py) - Network business logic
- [services/asset_types.py](../src/asset-management/services/asset_types.py) - Asset type business logic
- [services/locations.py](../src/asset-management/services/locations.py) - Location business logic
- [services/packages.py](../src/asset-management/services/packages.py) - Package business logic
- [services/eligibility.py](../src/asset-management/services/eligibility.py) - Eligibility business logic

**Database:**
- [db/backends/supabase.py](../src/asset-management/db/backends/supabase.py) - Supabase backend
- [db/backends/sqlite.py](../src/asset-management/db/backends/sqlite.py) - SQLite backend
- [db/migrations/01_schema.sql](../src/asset-management/db/migrations/01_schema.sql) - Multi-schema DDL
- [db/scripts/migrate_to_supabase.py](../src/asset-management/db/scripts/migrate_to_supabase.py) - Migration script

---

## Appendix B: API Endpoint Inventory

### Sales-Module Endpoints

**Mockups (Form-based):**
```
GET  /mockup                        - Admin setup interface
GET  /api/mockup/locations          - List locations (user.companies filtered)
POST /api/mockup/save-frame         - Save billboard frame config
POST /api/mockup/test-preview       - Real-time preview
GET  /api/mockup/photos/{location}  - List billboard photos
GET  /api/mockup/templates/{location} - List frame configs
POST /api/mockup/generate           - Generate mockup
```

**Proposals:**
```
GET    /api/proposals     - List proposals (user_id + team filtered)
GET    /api/proposals/{id} - Get proposal with locations
DELETE /api/proposals/{id} - Delete proposal
```

**Chat:**
```
POST /api/chat/message      - Send chat message (non-streaming)
POST /api/chat/stream       - Send chat message (SSE streaming)
GET  /api/chat/history      - Load chat history
```

---

### Asset-Management Endpoints

**Networks:**
```
GET    /api/networks                     - List networks
GET    /api/networks/{company}/{id}      - Get network
POST   /api/networks/{company}           - Create network
PATCH  /api/networks/{company}/{id}      - Update network
DELETE /api/networks/{company}/{id}      - Delete network
```

**Asset Types:**
```
GET    /api/asset-types                  - List asset types
GET    /api/asset-types/{company}/{id}   - Get asset type
POST   /api/asset-types/{company}        - Create asset type
PATCH  /api/asset-types/{company}/{id}   - Update asset type
DELETE /api/asset-types/{company}/{id}   - Delete asset type
```

**Locations:**
```
GET    /api/locations                    - List locations
GET    /api/locations/{company}/{id}     - Get location
GET    /api/locations/by-key/{key}       - Get location by key
POST   /api/locations/{company}          - Create location
PATCH  /api/locations/{company}/{id}     - Update location
DELETE /api/locations/{company}/{id}     - Delete location
POST   /api/locations/expand             - Expand sellable items to flat list
```

**Packages:**
```
GET    /api/packages                           - List packages
GET    /api/packages/{company}/{id}            - Get package
POST   /api/packages/{company}                 - Create package
PATCH  /api/packages/{company}/{id}            - Update package
DELETE /api/packages/{company}/{id}            - Delete package
POST   /api/packages/{company}/{id}/items      - Add item to package
DELETE /api/packages/{company}/{id}/items/{item} - Remove item from package
GET    /api/packages/{company}/{id}/locations  - Get all locations (expanded)
```

**Eligibility:**
```
GET  /api/eligibility/services                       - List services
GET  /api/eligibility/requirements/{service}         - Get requirements
GET  /api/eligibility/check/{company}/{location_id}  - Check location eligibility
GET  /api/eligibility/check-network/{company}/{network_id} - Check network eligibility
POST /api/eligibility/bulk-check                     - Bulk check eligibility
GET  /api/eligibility/eligible-locations             - Get eligible locations for service
GET  /api/eligibility/eligible-networks              - Get eligible networks for service
```

---

## Appendix C: Database Schema Reference

### Sales-Module Schemas

**Public Schema (Cross-company):**
```sql
proposals_log           -- Generated proposals
proposal_locations      -- Junction to locations
booking_orders          -- Parsed BOs
mockup_files            -- Generated mockups
chat_sessions           -- Chat history
chat_messages           -- Chat messages
```

**Company Schemas ({company}.*):**
```sql
locations               -- ⚠️ DUPLICATE of Asset-Management
mockup_frames           -- Billboard photo + frame coordinates
mockup_usage            -- Mockup generation audit
location_photos         -- Real billboard photos
rate_cards              -- Pricing data
```

---

### Asset-Management Schemas

**Public Schema (Cross-company):**
```sql
companies               -- Company hierarchy
```

**Company Schemas ({company}.*):**
```sql
networks                -- Sellable groupings
asset_types             -- Categories (NOT sellable)
locations               -- Individual sellable assets (standalone + network assets merged)
packages                -- Sellable bundles
package_items           -- Junction table
asset_photos            -- Real billboard photos (endpoints NOT implemented)
asset_occupations       -- Booking/availability (endpoints NOT implemented)
```

---

## Conclusion

This audit reveals a **partially integrated microservices architecture** with:

✅ **Strengths:**
- Multi-tenant architecture successfully implemented
- Complete Asset-Management API ready for integration
- Robust authentication/authorization (proxy secret + JWT)
- Dual workflow support (forms + AI chat)

⚠️ **Critical Gaps:**
- Location data duplication (no API integration)
- Fragmented mockup/proposal code
- No eligibility checking in workflows
- Inconsistent access control patterns

🎯 **Next Steps:**
1. Review this audit with stakeholders
2. Prioritize issues (critical → moderate → minor)
3. Create implementation plan with timeline
4. Begin with immediate actions (location API migration, eligibility checking)
5. Systematic refactoring of mockup/proposal code
6. Long-term architecture improvements (tool registry, event-driven sync)

This audit provides the foundation for systematic cleanup and refactoring. All identified issues are actionable with clear file references and recommended fixes.
