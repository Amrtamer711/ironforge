# Sales-Module Refactoring Plan

**Goal:** Transform Sales-Module into a clean, modular, well-integrated service that eliminates code duplication and properly integrates with Asset-Management.

---

## Executive Summary

### Current State Issues
- ❌ **No Asset-Management integration in proposals** - Uses stale local config data
- ❌ **5+ duplicate location matching implementations** - Scattered across files
- ❌ **2 duplicate intro/outro slide extraction functions** - 400+ lines duplicated
- ❌ **Inconsistent path sanitization** - Security risk
- ❌ **Database schema issues** - Text fields for amounts, no proper FKs
- ❌ **Direct SQL execution** - Bypasses abstractions
- ❌ **Config management scattered** - 3+ sources of truth

### Target State
- ✅ **Unified service layer** - Clear separation of concerns
- ✅ **Asset-Management as source of truth** - All location data from authoritative API
- ✅ **Shared utilities module** - No code duplication
- ✅ **Proper database schema** - Normalized, typed, with FKs
- ✅ **Modular capabilities** - Each workflow independent and testable
- ✅ **Service mesh integration** - Clean inter-service communication

---

## Part 1: New Module Structure

### Current Structure (Problematic)
```
src/sales-module/
├── core/
│   ├── proposals.py          # 793 lines - monolithic, duplicates code
│   ├── llm.py                # Contains direct SQL
│   └── ...
├── generators/
│   └── mockup.py             # 609 lines - duplicates validation
├── routers/
│   ├── mockup_handler.py     # 614 lines - duplicates mockup logic
│   └── tool_router.py        # Duplicates location matching
├── api/routers/
│   ├── proposals.py          # 260 lines
│   └── mockups.py            # 637 lines - duplicates validation
└── db/
    └── schema.py             # TEXT fields for amounts, no FKs
```

### New Proposed Structure (Modular)
```
src/sales-module/
├── core/
│   ├── __init__.py
│   ├── utils/                          # NEW: Shared utilities
│   │   ├── __init__.py
│   │   ├── location_matcher.py        # Single source for location matching
│   │   ├── path_sanitizer.py          # Single source for path security
│   │   ├── currency_formatter.py      # Currency handling utilities
│   │   └── validators.py              # Common validation logic
│   │
│   ├── services/                       # NEW: Service layer
│   │   ├── __init__.py
│   │   ├── asset_service.py           # Asset-Management integration
│   │   ├── proposal_service.py        # Proposals business logic (refactored)
│   │   ├── mockup_service.py          # Mockups business logic (refactored)
│   │   └── template_service.py        # Template/slide management
│   │
│   ├── models/                         # NEW: Data models
│   │   ├── __init__.py
│   │   ├── proposal.py                # Proposal domain models
│   │   ├── mockup.py                  # Mockup domain models
│   │   └── location.py                # Location domain models
│   │
│   └── workflows/                      # NEW: High-level workflows
│       ├── __init__.py
│       ├── proposal_workflow.py       # Orchestrates proposal generation
│       └── mockup_workflow.py         # Orchestrates mockup generation
│
├── api/
│   ├── dependencies.py                 # NEW: Shared API dependencies
│   └── routers/
│       ├── __init__.py
│       ├── proposals.py               # Thin controller - delegates to services
│       ├── mockups.py                 # Thin controller - delegates to services
│       └── health.py
│
├── db/
│   ├── __init__.py
│   ├── models.py                      # NEW: SQLAlchemy/ORM models
│   ├── migrations/                    # NEW: Database migrations
│   │   └── 001_normalize_proposals.sql
│   └── repositories/                  # NEW: Data access layer
│       ├── __init__.py
│       ├── proposal_repository.py
│       └── mockup_repository.py
│
├── clients/                           # Service clients
│   ├── __init__.py
│   ├── asset_management.py           # Asset-Management API client (enhanced)
│   └── storage.py                     # Storage service client
│
└── config/
    ├── __init__.py
    └── settings.py                    # Configuration (env-based, no hardcoded data)
```

---

## Part 2: Core Modules Design

### 2.1 Shared Utilities (`core/utils/`)

#### `location_matcher.py`
**Purpose:** Single source of truth for location matching logic
**Replaces:** Duplicate code in proposals.py (lines 76-90, 114-125, 236-250), mockup_handler.py, tool_router.py

```python
# Public API:
def match_location_key(location_input: str) -> str | None
def validate_location_exists(location_key: str) -> bool
def get_location_display_name(location_key: str) -> str
```

**Implementation:**
- First tries Asset-Management API lookup
- Falls back to local cache with TTL
- Fuzzy matching for user convenience
- Logs misses for monitoring

#### `path_sanitizer.py`
**Purpose:** Prevent directory traversal and injection attacks
**Replaces:** Inconsistent sanitization in mockups.py (lines 28-40) vs generators/mockup.py (lines 30-31)

```python
# Public API:
def sanitize_path_component(component: str) -> str
def safe_path_join(base: Path, *parts: str) -> Path
def validate_path_within(path: Path, base: Path) -> bool
```

**Features:**
- Removes `..`, `/`, `\`, null bytes
- Validates result stays within allowed directory
- Raises clear exceptions for security violations

#### `currency_formatter.py`
**Purpose:** Consistent currency handling
**Replaces:** Hardcoded currency strings, TEXT storage

```python
# Public API:
def format_amount(amount: Decimal, currency: str) -> str
def parse_amount(amount_str: str) -> tuple[Decimal, str]
def validate_currency(currency: str) -> bool
```

**Features:**
- Uses Decimal for precision
- Supports multiple currencies
- Locale-aware formatting

#### `validators.py`
**Purpose:** Shared validation logic
**Replaces:** Duplicate validation in API and generators

```python
# Public API:
def validate_frame_count(frames: list) -> None
def validate_proposal_data(data: dict) -> dict  # Returns normalized
def validate_mockup_config(config: dict) -> dict
```

---

### 2.2 Service Layer (`core/services/`)

#### `asset_service.py` - Asset-Management Integration
**Purpose:** Single point of integration with Asset-Management service

```python
class AssetService:
    """Manages all Asset-Management interactions."""

    def __init__(self, client: AssetManagementClient):
        self.client = client
        self._cache = TTLCache(maxsize=1000, ttl=300)  # 5min cache

    # Location operations
    async def get_location(self, location_key: str, company: str) -> Location:
        """Get location with caching."""

    async def list_locations(self, companies: list[str], filters: dict) -> list[Location]:
        """List locations with filters."""

    async def check_eligibility(
        self,
        location_key: str,
        service: str  # "proposal_generator" | "mockup_generator"
    ) -> EligibilityResult:
        """Check if location is eligible for a service."""

    # Network operations
    async def get_network(self, network_id: int, company: str) -> Network:
        """Get network details."""

    async def expand_package(self, package_id: int, company: str) -> list[Location]:
        """Expand package to flat list of locations."""

    # Pricing operations
    async def get_pricing(self, location_key: str) -> PricingInfo:
        """Get current pricing (rates, upload fees, etc.)."""
```

**Key Features:**
- Caching layer to reduce API calls
- Graceful degradation if Asset-Management is down
- Automatic retry with exponential backoff
- Comprehensive error handling

#### `proposal_service.py` - Proposals Business Logic
**Purpose:** Clean, testable proposal generation logic
**Refactored from:** core/proposals.py (793 lines → ~300 lines)

```python
class ProposalService:
    """Handles proposal generation business logic."""

    def __init__(
        self,
        asset_service: AssetService,
        template_service: TemplateService,
        repository: ProposalRepository,
    ):
        self.assets = asset_service
        self.templates = template_service
        self.repo = repository

    async def create_proposal(
        self,
        locations: list[str],  # location_keys or display names
        duration: int,
        start_date: date,
        currency: str,
        user_id: str,
        company: str,
    ) -> Proposal:
        """
        Create a proposal for given locations.

        Steps:
        1. Validate and resolve location keys via AssetService
        2. Check eligibility for proposal_generator
        3. Fetch pricing from AssetService
        4. Generate proposal data
        5. Create PDF via TemplateService
        6. Store in repository
        7. Return Proposal model
        """

    async def create_package_proposal(
        self,
        items: list[dict],  # [{type: "network"|"package"|"location", id: ...}]
        duration: int,
        start_date: date,
        currency: str,
        user_id: str,
        company: str,
    ) -> Proposal:
        """
        Create proposal from mixed items (networks, packages, locations).

        Steps:
        1. Expand packages/networks to locations via AssetService
        2. Deduplicate locations
        3. Delegate to create_proposal()
        """

    async def get_proposal(self, proposal_id: str, user_id: str) -> Proposal:
        """Retrieve proposal with access control."""

    async def list_proposals(
        self,
        user_id: str,
        filters: dict,
    ) -> list[Proposal]:
        """List user's proposals with filtering."""
```

**Extracted Functions:**
```python
# Private helper methods (no longer duplicated):
def _extract_intro_outro_slides(
    self,
    locations: list[Location],
    template_mapping: dict,
) -> tuple[list[Path], list[Path]]:
    """
    Extract intro/outro slides for locations.

    REPLACES duplicate code in:
    - proposals.py lines 281-431 (combined package)
    - proposals.py lines 518-743 (separate proposals)

    Now single implementation used by both workflows.
    """

def _calculate_total_amount(
    self,
    location_pricing: list[PricingInfo],
    duration: int,
) -> Decimal:
    """Calculate total proposal amount."""

def _build_proposal_deck(
    self,
    intro_slides: list[Path],
    location_slides: list[Path],
    outro_slides: list[Path],
    remove_first: bool,
    remove_last: bool,
) -> Path:
    """Assemble final PDF deck."""
```

#### `mockup_service.py` - Mockups Business Logic
**Purpose:** Clean mockup generation logic
**Refactored from:** generators/mockup.py (609 lines) + routers/mockup_handler.py (614 lines)

```python
class MockupService:
    """Handles mockup generation business logic."""

    def __init__(
        self,
        asset_service: AssetService,
        storage_service: StorageService,
    ):
        self.assets = asset_service
        self.storage = storage_service

    async def generate_mockup(
        self,
        location_key: str,
        creative_path: str,
        config: MockupConfig,
        user_id: str,
        company: str,
    ) -> MockupResult:
        """
        Generate mockup for location.

        Steps:
        1. Validate location via AssetService
        2. Check eligibility for mockup_generator
        3. Load frame data
        4. Validate and sanitize paths
        5. Generate mockup (warp creative)
        6. Store result
        7. Return MockupResult
        """

    async def save_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        user_id: str,
        company: str,
    ) -> Frame:
        """Save mockup frame coordinates."""

    async def get_frames(
        self,
        location_key: str,
        company: str,
    ) -> list[Frame]:
        """Get saved frames for location."""
```

**Extracted Functions:**
```python
# Private helper methods:
def _validate_and_merge_config(
    self,
    photo_config: dict,
    frame_config: dict,
    override_config: dict,
) -> MockupConfig:
    """
    Merge configs with clear precedence.

    REPLACES scattered config management in:
    - mockups.py lines 129-133
    - generators/mockup.py lines 488-495
    - db/database.py lines 231-241

    Order: photo_config < frame_config < override_config
    """

def _warp_creative_to_frame(
    self,
    creative: Image,
    frame: FrameCoordinates,
    config: MockupConfig,
) -> Image:
    """Apply perspective warp to creative."""
```

#### `template_service.py` - Template Management
**Purpose:** Handle PDF templates and slide extraction

```python
class TemplateService:
    """Manages proposal templates and PDF operations."""

    async def get_template_for_location(
        self,
        location: Location,
    ) -> Path:
        """Get appropriate template PDF for location."""

    async def extract_slides(
        self,
        pdf_path: Path,
        remove_first: bool = False,
        remove_last: bool = False,
    ) -> list[Path]:
        """Extract slides from PDF as images."""

    async def merge_pdfs(
        self,
        pdfs: list[Path],
        output_path: Path,
    ) -> Path:
        """Merge multiple PDFs into one."""
```

---

### 2.3 Data Models (`core/models/`)

#### `proposal.py`
```python
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import date, datetime

class ProposalLocation(BaseModel):
    """Individual location in a proposal."""
    location_key: str
    display_name: str
    net_rate: Decimal
    upload_fee: Decimal
    duration: int  # days
    start_date: date

class Proposal(BaseModel):
    """Proposal domain model."""
    id: str
    proposal_number: str  # Human-readable identifier
    user_id: str
    company: str

    # Locations
    locations: list[ProposalLocation]

    # Financial
    currency: str
    subtotal: Decimal
    upload_fees_total: Decimal
    total_amount: Decimal

    # Metadata
    created_at: datetime
    pdf_path: str | None
    status: str  # "draft" | "sent" | "accepted" | "rejected"
```

#### `mockup.py`
```python
class FrameCoordinates(BaseModel):
    """Billboard frame coordinates for perspective warp."""
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_right: tuple[int, int]
    bottom_left: tuple[int, int]

class MockupConfig(BaseModel):
    """Mockup generation configuration."""
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    quality: int = 95
    # ... other settings

class MockupResult(BaseModel):
    """Result of mockup generation."""
    mockup_url: str
    location_key: str
    creative_path: str
    config: MockupConfig
    generated_at: datetime
    user_id: str
```

#### `location.py`
```python
class Location(BaseModel):
    """Location model (from Asset-Management)."""
    location_key: str
    display_name: str
    display_type: str
    company: str

    # Specs
    series: str | None
    height: str | None
    width: str | None
    number_of_faces: int

    # Display specs
    spot_duration: int
    loop_duration: int
    sov_percent: float

    # Pricing
    upload_fee: Decimal

    # Location
    city: str | None
    area: str | None

    # Eligibility
    eligible_for_proposals: bool
    eligible_for_mockups: bool

class PricingInfo(BaseModel):
    """Pricing information for a location."""
    location_key: str
    base_rate: Decimal
    upload_fee: Decimal
    currency: str
    valid_from: date
    valid_until: date | None
```

---

## Part 3: Database Schema Improvements

### Current Schema Issues
```sql
-- PROBLEMS:
CREATE TABLE proposals_log (
    -- No proper primary key strategy
    created_at TEXT,

    -- Financial data as TEXT (can't sort/filter/aggregate)
    total_amount TEXT,  -- Stores "AED 1,000.00" as string

    -- No currency tracking
    -- Missing: currency CHAR(3)

    -- Locations as comma-separated string (not normalized)
    locations TEXT,  -- "loc1,loc2,loc3"

    -- No foreign keys
    -- No status tracking
)
```

### New Normalized Schema

```sql
-- proposals table (main)
CREATE TABLE proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_number VARCHAR(50) UNIQUE NOT NULL,  -- Human-readable: "PROP-2024-001"

    -- Ownership
    user_id VARCHAR(255) NOT NULL,
    company VARCHAR(100) NOT NULL,

    -- Financial
    currency CHAR(3) NOT NULL,  -- ISO 4217: AED, USD, etc.
    subtotal DECIMAL(15, 2) NOT NULL,
    upload_fees_total DECIMAL(15, 2) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Status workflow
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft, sent, accepted, rejected

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sent_at TIMESTAMP WITH TIME ZONE,

    -- PDF storage
    pdf_path TEXT,
    pdf_storage_url TEXT,

    -- Indexes
    INDEX idx_proposals_user (user_id),
    INDEX idx_proposals_company (company),
    INDEX idx_proposals_status (status),
    INDEX idx_proposals_created (created_at DESC)
);

-- proposal_locations table (junction)
CREATE TABLE proposal_locations (
    id SERIAL PRIMARY KEY,
    proposal_id UUID NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,

    -- Location reference (from Asset-Management)
    location_key VARCHAR(100) NOT NULL,
    display_name VARCHAR(255) NOT NULL,  -- Cached for reporting

    -- Campaign details
    start_date DATE NOT NULL,
    duration_days INTEGER NOT NULL,

    -- Pricing (snapshot at proposal creation time)
    net_rate DECIMAL(15, 2) NOT NULL,
    upload_fee DECIMAL(15, 2) NOT NULL,

    -- Calculated
    line_total DECIMAL(15, 2) NOT NULL,

    -- Order
    display_order INTEGER NOT NULL,  -- For maintaining location order in proposal

    -- Indexes
    INDEX idx_prop_locs_proposal (proposal_id),
    INDEX idx_prop_locs_location (location_key)
);

-- mockup_frames table (improved)
CREATE TABLE mockup_frames (
    id SERIAL PRIMARY KEY,

    -- Location reference
    location_key VARCHAR(100) NOT NULL,

    -- Photo reference
    photo_filename VARCHAR(255) NOT NULL,
    time_of_day VARCHAR(20),  -- day, night
    finish VARCHAR(20),  -- backlit, frontlit

    -- Frame data (JSONB for querying)
    frames_data JSONB NOT NULL,  -- CHANGED from TEXT

    -- Version tracking
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,

    -- Ownership
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    UNIQUE INDEX idx_frame_unique (location_key, photo_filename, version),
    INDEX idx_frame_location (location_key),
    INDEX idx_frame_active (is_active)
);

-- mockup_usage table (enhanced)
CREATE TABLE mockup_usage (
    id SERIAL PRIMARY KEY,

    -- References
    location_key VARCHAR(100) NOT NULL,
    frame_id INTEGER REFERENCES mockup_frames(id),

    -- Creative
    creative_path TEXT NOT NULL,

    -- Result
    mockup_url TEXT NOT NULL,

    -- Config snapshot (JSONB)
    config_used JSONB NOT NULL,  -- CHANGED from scattered fields

    -- Ownership
    user_id VARCHAR(255) NOT NULL,
    company VARCHAR(100) NOT NULL,

    -- Metadata
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    generation_time_ms INTEGER,  -- Performance tracking

    -- Indexes
    INDEX idx_mockup_usage_user (user_id),
    INDEX idx_mockup_usage_location (location_key),
    INDEX idx_mockup_usage_generated (generated_at DESC)
);
```

### Migration Strategy
```sql
-- Migration 001: Normalize proposals
-- Step 1: Create new tables
-- Step 2: Migrate data from proposals_log to new schema
-- Step 3: Keep proposals_log for 30 days as backup
-- Step 4: Drop proposals_log

-- Example migration script:
INSERT INTO proposals (proposal_number, user_id, company, currency, total_amount, ...)
SELECT
    'PROP-' || to_char(created_at, 'YYYY-MM-DD-HH24MISS') as proposal_number,
    user_id,
    company,
    'AED' as currency,  -- Parse from total_amount TEXT field
    parse_currency_amount(total_amount)::DECIMAL as total_amount,
    ...
FROM proposals_log;

-- Parse and insert locations
INSERT INTO proposal_locations (proposal_id, location_key, ...)
SELECT
    p.id,
    unnest(string_to_array(pl.locations, ',')) as location_key,
    ...
FROM proposals_log pl
JOIN proposals p ON ...;
```

---

## Part 4: Service Integration Architecture

### 4.1 Service Mesh Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Unified-UI (Frontend)                   │
│            (Next.js - User-facing interface)                 │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP + Proxy Secret
                      │
        ┌─────────────┴──────────────┐
        │                            │
        ▼                            ▼
┌────────────────────┐      ┌────────────────────┐
│  Security-Service  │      │   Sales-Module     │
│  (Authentication)  │      │  (THIS SERVICE)    │
└────────────────────┘      └─────────┬──────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
         ┌──────────────────┐ ┌─────────────┐ ┌──────────────┐
         │ Asset-Management │ │   Storage   │ │ Notification │
         │    (Assets)      │ │ (Files/CDN) │ │   (Email)    │
         └──────────────────┘ └─────────────┘ └──────────────┘
```

### 4.2 Asset-Management Integration

**Client Implementation:** `clients/asset_management.py`

```python
from crm_security import ServiceAuthClient

class AssetManagementClient:
    """
    Client for Asset-Management service.

    Uses JWT service-to-service authentication.
    """

    def __init__(self):
        self.base_url = config.ASSET_MANAGEMENT_URL
        self.auth_client = ServiceAuthClient(
            service_id="sales-module",
            service_secret=config.SERVICE_SECRET,
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """Make authenticated request to Asset-Management."""
        # Get service JWT token
        token = await self.auth_client.get_service_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    # Location operations
    async def get_location(
        self,
        location_key: str,
        company: str,
    ) -> dict:
        """GET /api/locations/by-key/{location_key}?companies={company}"""
        return await self._request(
            "GET",
            f"/api/locations/by-key/{location_key}",
            params={"companies": [company]},
        )

    async def list_locations(
        self,
        companies: list[str],
        network_id: int | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """GET /api/locations"""
        return await self._request(
            "GET",
            "/api/locations",
            params={
                "companies": companies,
                "network_id": network_id,
                "active_only": active_only,
            },
        )

    # Eligibility operations
    async def check_location_eligibility(
        self,
        location_key: str,
        company: str,
        service: str,
    ) -> dict:
        """GET /api/eligibility/location/{company}/{location_key}"""
        result = await self._request(
            "GET",
            f"/api/eligibility/location/{company}/{location_key}",
        )

        return {
            "eligible": result["service_eligibility"].get(service, False),
            "details": result.get("details", []),
        }

    # Package operations
    async def expand_package(
        self,
        package_id: int,
        company: str,
    ) -> list[dict]:
        """GET /api/packages/{company}/{package_id}?expand_locations=true"""
        result = await self._request(
            "GET",
            f"/api/packages/{company}/{package_id}",
            params={"expand_locations": True},
        )

        return result.get("expanded_locations", [])

    # Network operations
    async def get_network(
        self,
        network_id: int,
        company: str,
    ) -> dict:
        """GET /api/networks/{company}/{network_id}"""
        return await self._request(
            "GET",
            f"/api/networks/{company}/{network_id}",
        )
```

**Usage in ProposalService:**
```python
# Before (WRONG - uses local config):
location_mapping = config.get_location_mapping()
location_data = location_mapping.get(location_key)

# After (CORRECT - uses Asset-Management):
location = await self.asset_service.get_location(
    location_key=location_key,
    company=user_company,
)

# Validate eligibility
eligibility = await self.asset_service.check_eligibility(
    location_key=location_key,
    service="proposal_generator",
)

if not eligibility["eligible"]:
    raise ValueError(
        f"Location {location_key} not eligible for proposals: "
        f"{eligibility['details']}"
    )
```

### 4.3 Caching Strategy

**Problem:** Calling Asset-Management for every location lookup is slow.

**Solution:** Multi-layer caching

```python
from cachetools import TTLCache
from functools import wraps

class AssetService:
    def __init__(self, client: AssetManagementClient):
        self.client = client

        # L1: In-memory cache (5 minutes)
        self._location_cache = TTLCache(maxsize=1000, ttl=300)

        # L2: Redis cache (if available) - 15 minutes
        self._redis = redis.Redis(...) if config.REDIS_URL else None

    async def get_location(self, location_key: str, company: str) -> Location:
        # Check L1 cache
        cache_key = f"location:{company}:{location_key}"

        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        # Check L2 cache (Redis)
        if self._redis:
            cached = self._redis.get(cache_key)
            if cached:
                location = Location.model_validate_json(cached)
                self._location_cache[cache_key] = location
                return location

        # Fetch from Asset-Management
        data = await self.client.get_location(location_key, company)
        location = Location.model_validate(data)

        # Store in both caches
        self._location_cache[cache_key] = location
        if self._redis:
            self._redis.setex(
                cache_key,
                900,  # 15 minutes
                location.model_dump_json(),
            )

        return location
```

**Cache Invalidation:**
- TTL-based (automatic expiration)
- Webhook from Asset-Management on location updates (future)
- Manual cache clear endpoint for admins

---

## Part 5: Workflow Orchestration

### 5.1 Proposal Workflow (New)

**File:** `core/workflows/proposal_workflow.py`

```python
class ProposalWorkflow:
    """
    Orchestrates the complete proposal generation workflow.

    This is the high-level entry point that coordinates multiple services.
    """

    def __init__(
        self,
        asset_service: AssetService,
        proposal_service: ProposalService,
        notification_service: NotificationService,
    ):
        self.assets = asset_service
        self.proposals = proposal_service
        self.notifications = notification_service

    async def create_proposal_from_locations(
        self,
        request: CreateProposalRequest,
        user: TrustedUserContext,
    ) -> ProposalResult:
        """
        Complete workflow for creating proposal from location names.

        Steps:
        1. Parse and validate input
        2. Resolve location names to keys via Asset-Management
        3. Validate eligibility for all locations
        4. Fetch pricing
        5. Generate proposal
        6. Send notification (optional)
        7. Return result
        """

        # Step 1: Validate input
        self._validate_request(request)

        # Step 2: Resolve locations
        resolved_locations = await self._resolve_locations(
            location_inputs=request.locations,
            company=user.company,
        )

        # Step 3: Check eligibility
        ineligible = []
        for loc in resolved_locations:
            eligibility = await self.assets.check_eligibility(
                location_key=loc.location_key,
                service="proposal_generator",
            )
            if not eligibility["eligible"]:
                ineligible.append({
                    "location": loc.display_name,
                    "reason": eligibility["details"],
                })

        if ineligible:
            raise ValidationError(
                f"Some locations are not eligible for proposals",
                ineligible=ineligible,
            )

        # Step 4: Fetch pricing
        pricing = await self._fetch_pricing(resolved_locations)

        # Step 5: Generate proposal
        proposal = await self.proposals.create_proposal(
            locations=resolved_locations,
            pricing=pricing,
            duration=request.duration,
            start_date=request.start_date,
            currency=request.currency,
            user_id=user.id,
            company=user.company,
        )

        # Step 6: Send notification (async, don't wait)
        if request.send_notification:
            asyncio.create_task(
                self.notifications.send_proposal_created(
                    proposal=proposal,
                    user=user,
                )
            )

        # Step 7: Return result
        return ProposalResult(
            proposal_id=proposal.id,
            proposal_number=proposal.proposal_number,
            pdf_url=proposal.pdf_storage_url,
            total_amount=proposal.total_amount,
            currency=proposal.currency,
            location_count=len(proposal.locations),
        )

    async def _resolve_locations(
        self,
        location_inputs: list[str],
        company: str,
    ) -> list[Location]:
        """Resolve location display names or keys to full Location objects."""

        resolved = []
        for input_str in location_inputs:
            # Try direct lookup by key
            try:
                location = await self.assets.get_location(
                    location_key=input_str,
                    company=company,
                )
                resolved.append(location)
                continue
            except NotFoundError:
                pass

            # Try fuzzy match by display name
            location_key = match_location_key(input_str)
            if location_key:
                location = await self.assets.get_location(
                    location_key=location_key,
                    company=company,
                )
                resolved.append(location)
            else:
                raise ValidationError(
                    f"Could not find location: {input_str}"
                )

        return resolved
```

### 5.2 Mockup Workflow (New)

Similar structure for mockup generation workflow.

---

## Part 6: API Layer Refactoring

### Before (Fat Controllers)
```python
# api/routers/proposals.py - 260 lines
@router.post("/process")
async def process_proposals(...):
    # 100+ lines of business logic IN THE CONTROLLER
    # - Location matching
    # - Validation
    # - PDF generation
    # - Database operations
    # ALL MIXED TOGETHER
```

### After (Thin Controllers)
```python
# api/routers/proposals.py - ~50 lines
from core.workflows import ProposalWorkflow
from core.services import AssetService, ProposalService

# Dependency injection
def get_proposal_workflow() -> ProposalWorkflow:
    asset_service = AssetService(
        client=AssetManagementClient(),
    )
    proposal_service = ProposalService(
        asset_service=asset_service,
        template_service=TemplateService(),
        repository=ProposalRepository(),
    )
    return ProposalWorkflow(
        asset_service=asset_service,
        proposal_service=proposal_service,
        notification_service=NotificationService(),
    )

@router.post("/proposals")
async def create_proposal(
    request: CreateProposalRequest,
    user: TrustedUserContext = Depends(require_permission("proposals:create")),
    workflow: ProposalWorkflow = Depends(get_proposal_workflow),
) -> ProposalResponse:
    """
    Create a new proposal.

    Controller is now THIN - just delegates to workflow.
    """
    try:
        result = await workflow.create_proposal_from_locations(
            request=request,
            user=user,
        )
        return ProposalResponse(
            success=True,
            data=result,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to create proposal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )
```

**Benefits:**
- Controllers are thin (10-20 lines each)
- Business logic in services (testable without HTTP)
- Clear separation of concerns
- Easy to add new endpoints

---

## Part 7: Testing Strategy

### Test Structure
```
tests/
├── unit/                          # Fast, isolated tests
│   ├── utils/
│   │   ├── test_location_matcher.py
│   │   ├── test_path_sanitizer.py
│   │   └── test_validators.py
│   ├── services/
│   │   ├── test_asset_service.py
│   │   ├── test_proposal_service.py
│   │   └── test_mockup_service.py
│   └── models/
│       ├── test_proposal.py
│       └── test_mockup.py
│
├── integration/                   # Tests with external dependencies
│   ├── test_asset_management_integration.py
│   ├── test_proposal_workflow.py
│   └── test_mockup_workflow.py
│
└── e2e/                          # Full end-to-end tests
    ├── test_create_proposal_api.py
    └── test_generate_mockup_api.py
```

### Example Unit Test
```python
# tests/unit/utils/test_location_matcher.py
import pytest
from core.utils.location_matcher import match_location_key

def test_match_location_exact():
    """Test exact location key match."""
    result = match_location_key("SZR_Habtoor_Palace")
    assert result == "SZR_Habtoor_Palace"

def test_match_location_fuzzy():
    """Test fuzzy matching by display name."""
    result = match_location_key("habtoor palace")
    assert result == "SZR_Habtoor_Palace"

def test_match_location_not_found():
    """Test non-existent location."""
    result = match_location_key("nonexistent_location")
    assert result is None
```

### Example Integration Test
```python
# tests/integration/test_asset_management_integration.py
import pytest
from core.services import AssetService

@pytest.mark.asyncio
async def test_get_location_from_asset_management(
    asset_service: AssetService,
    mock_asset_management_server,
):
    """Test fetching location from Asset-Management service."""

    # Setup mock response
    mock_asset_management_server.mock_response(
        "/api/locations/by-key/SZR_Habtoor_Palace",
        {
            "location_key": "SZR_Habtoor_Palace",
            "display_name": "SZR - Habtoor Palace",
            "company": "backlite_dubai",
            # ... other fields
        },
    )

    # Execute
    location = await asset_service.get_location(
        location_key="SZR_Habtoor_Palace",
        company="backlite_dubai",
    )

    # Assert
    assert location.location_key == "SZR_Habtoor_Palace"
    assert location.display_name == "SZR - Habtoor Palace"
```

---

## Part 8: Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Set up new structure and shared utilities

**Tasks:**
1. ✅ Create new module structure (directories)
2. ✅ Implement `core/utils/` modules:
   - location_matcher.py
   - path_sanitizer.py
   - currency_formatter.py
   - validators.py
3. ✅ Write unit tests for all utilities (>90% coverage)
4. ✅ Create data models in `core/models/`
5. ✅ Set up dependency injection framework

**Deliverable:** Shared utilities module with tests

---

### Phase 1.5: True Modularization (In Progress)
**Goal:** Break down monolithic files into clean, testable, class-based modules

**Problem:** Phase 1 eliminated duplicate code but kept monolithic functions (proposals.py: 787 lines, mockup_handler.py: 614 lines). This phase applies proper separation of concerns.

**Tasks:**
1. 🔄 Create `core/proposals/` module (class-based):
   - `validator.py` - ProposalValidator class
   - `processor.py` - ProposalProcessor class
   - `renderer.py` - ProposalRenderer class
   - `intro_outro.py` - IntroOutroHandler class
   - `__init__.py` - Public API (backwards compatible)

2. 🔄 Create `core/mockups/` module (strategy pattern):
   - `coordinator.py` - MockupCoordinator class
   - `validator.py` - MockupValidator class
   - `strategies/base.py` - MockupStrategy (abstract)
   - `strategies/upload.py` - UploadMockupStrategy
   - `strategies/ai.py` - AIMockupStrategy
   - `strategies/followup.py` - FollowupMockupStrategy
   - `__init__.py` - Public API (backwards compatible)

3. 🔄 Simplify routing layers (thin controllers):
   - Update `routers/tool_router.py` → calls `core/proposals`, `core/mockups`
   - Update `api/routers/proposals.py` → calls `core/proposals`
   - Update `api/routers/mockups.py` → calls `core/mockups`

4. 🔄 Clean up old code:
   - Delete `core/proposals.py` (logic moved to `core/proposals/*`)
   - Delete `routers/mockup_handler.py` (logic moved to `core/mockups/*`)

**Benefits:**
- ✅ **Testability:** Each class independently testable
- ✅ **Maintainability:** ~100 lines per file vs 787-line monoliths
- ✅ **Extensibility:** Add new mockup strategies without touching existing code
- ✅ **Clarity:** Clear responsibilities, single source of truth for each concern

**Deliverable:** Fully modularized proposals and mockups with class-based architecture

---

### Phase 1.6: Directory Restructure (Planned)
**Goal:** Clean up directory structure to eliminate confusion and bloat

**Current Issues:**
- `routers/` vs `api/routers/` - confusing naming (both called "routers")
- `utils/` vs `core/utils/` - two utility directories
- `clients/` - single file, should be in integrations/
- Loose files at root (`font_utils.py`, `pdf_slide_utils.py`)

**Target Structure:**
```
sales-module/
├── api/                    # HTTP layer
│   └── routers/
├── core/                   # Business logic
│   ├── mockups/
│   ├── proposals/
│   ├── models/
│   ├── services/
│   └── utils/              # ← Single utils location
├── db/                     # Database
├── generators/             # Content generation
├── handlers/               # ← Renamed from routers/
├── integrations/           # External services
│   ├── asset_management/   # ← Moved from clients/
│   ├── auth/
│   ├── channels/
│   ├── llm/
│   ├── rbac/
│   └── storage/
├── workflows/              # Business workflows
├── data/                   # Runtime data
│   ├── templates/
│   └── storage/
├── tests/
├── config.py
└── main.py
```

**Tasks:**
1. 📋 Rename `routers/` → `handlers/` (update all imports)
2. 📋 Move `clients/asset_management.py` → `integrations/asset_management/`
3. 📋 Move `font_utils.py` → `utils/`
4. 📋 Move `pdf_slide_utils.py` → `utils/`
5. 📋 Consolidate `utils/` into `core/utils/` (single source)

**Benefits:**
- ✅ Clear naming (handlers vs routers distinction)
- ✅ Single utils location
- ✅ All external service clients in integrations/
- ✅ No loose utility files at root

**Deliverable:** Clean, consistent directory structure

---

### Phase 1.75: Request Classification (Planned)
**Goal:** Decouple request classification from LLM prompt and both workflows

**Problem:** Classification logic (BO vs Mockups vs Proposals) is embedded in LLM system prompt and duplicated across handlers. When file uploads happen, the decision logic is scattered and hard to test.

**Current State:**
- Classification rules in LLM prompt ([chat.py:50-65](src/sales-module/integrations/llm/prompts/chat.py#L50-L65))
- File type detection logic duplicated
- No fast-path for deterministic requests (e.g., PDF upload = BO)
- Hard to test classification without full LLM integration

**Tasks:**
1. 📋 Create `core/classification/` module:
   - `models.py` - RequestType enum, ClassificationResult model
   - `detectors/base.py` - Detector interface
   - `detectors/file_detector.py` - File-based classification (PDF→BO, Image→Mockup)
   - `detectors/intent_detector.py` - Text intent detection (keywords, patterns)
   - `detectors/context_detector.py` - Context switching detection
   - `classifier.py` - RequestClassifier orchestrator
   - `__init__.py` - Public API

2. 📋 Update routing layers:
   - Use RequestClassifier BEFORE LLM for fast-path decisions
   - Simplify LLM system prompt (remove classification rules)
   - Deterministic classification for file uploads

3. 📋 Benefits:
   - ✅ **Testable:** Classification logic isolated and unit-testable
   - ✅ **Fast-path:** File uploads bypass LLM (instant routing)
   - ✅ **Reusable:** Same classifier across Slack, Web, API
   - ✅ **Decoupled:** Independent of proposals, mockups, BO workflows
   - ✅ **Extensible:** Easy to add new request types

**Architecture:**
```
User Request (text + files)
         ↓
RequestClassifier.classify()
    ├─→ FileDetector: Check for PDF/Image
    ├─→ IntentDetector: Extract keywords, entities
    └─→ ContextDetector: Check history, context switches
         ↓
ClassificationResult
    ├─ RequestType (PROPOSAL, MOCKUP, BO_PARSING)
    ├─ Confidence (0-1)
    ├─ Detected entities (locations, dates)
    └─ Suggested tool call
         ↓
Router → Appropriate Workflow
```

**Example:**
```python
# Before (scattered logic):
if "files" in event and is_pdf(event["files"][0]):
    # BO parsing
elif "files" in event and is_image(event["files"][0]):
    # Mockup
else:
    # Send to LLM to decide

# After (centralized):
result = await classifier.classify(
    text=user_input,
    files=uploaded_files,
    user_history=history
)

if result.type == RequestType.MOCKUP:
    # Fast-path to mockup coordinator
elif result.type == RequestType.BO_PARSING:
    # Fast-path to BO parser
else:
    # LLM for complex decisions
```

**Deliverable:** Modular, testable request classification system

---

### Phase 2: Service Layer (Week 2)
**Goal:** Implement service layer with Asset-Management integration

**Tasks:**
1. ✅ Enhance `clients/asset_management.py`
   - Add all required API methods
   - Add retry logic
   - Add error handling
2. ✅ Implement `AssetService` with caching
3. ✅ Implement `TemplateService`
4. ✅ Write integration tests for Asset-Management client

**Deliverable:** Working AssetService with caching and tests

---

### Phase 3: Refactor Proposals (Week 3)
**Goal:** Refactor proposals workflow to use new architecture

**Tasks:**
1. ✅ Implement `ProposalService`:
   - Extract `_extract_intro_outro_slides()` (removes duplicate code)
   - Use AssetService for location data
   - Use TemplateService for PDF operations
2. ✅ Implement `ProposalWorkflow`
3. ✅ Refactor `api/routers/proposals.py` to thin controller
4. ✅ Write comprehensive tests
5. ✅ Run parallel with old code (feature flag)

**Deliverable:** New proposals workflow (feature flagged)

---

### Phase 4: Refactor Mockups (Week 4)
**Goal:** Refactor mockups workflow to use new architecture

**Tasks:**
1. ✅ Implement `MockupService`:
   - Consolidate config management
   - Use AssetService for location validation
   - Add path sanitization everywhere
2. ✅ Implement `MockupWorkflow`
3. ✅ Refactor `api/routers/mockups.py` to thin controller
4. ✅ Write comprehensive tests
5. ✅ Run parallel with old code (feature flag)

**Deliverable:** New mockups workflow (feature flagged)

---

### Phase 5: Database Migration (Week 5)
**Goal:** Migrate to new normalized database schema

**Tasks:**
1. ✅ Create migration scripts
2. ✅ Implement new repository classes
3. ✅ Test migration on staging data
4. ✅ Execute migration in production
5. ✅ Keep old tables for 30 days as backup

**Deliverable:** Normalized database schema

---

### Phase 6: Cleanup & Cutover (Week 6)
**Goal:** Remove old code and fully transition to new architecture

**Tasks:**
1. ✅ Enable new workflows in production (flip feature flags)
2. ✅ Monitor for errors/performance issues
3. ✅ Remove old code:
   - Delete duplicate functions
   - Delete old controllers
   - Remove feature flags
4. ✅ Update documentation
5. ✅ Performance testing & optimization

**Deliverable:** Clean, production-ready Sales-Module

---

## Part 9: Rollback Strategy

### Feature Flags
```python
# config/settings.py
USE_NEW_PROPOSAL_WORKFLOW = os.getenv("USE_NEW_PROPOSAL_WORKFLOW", "false").lower() == "true"
USE_NEW_MOCKUP_WORKFLOW = os.getenv("USE_NEW_MOCKUP_WORKFLOW", "false").lower() == "true"
```

```python
# api/routers/proposals.py
@router.post("/proposals")
async def create_proposal(...):
    if config.USE_NEW_PROPOSAL_WORKFLOW:
        # Use new workflow
        return await new_workflow.create_proposal(...)
    else:
        # Use old code
        return await old_process_proposals(...)
```

### Rollback Plan
1. If new workflow fails → flip feature flag to false → instant rollback
2. If database migration fails → restore from backup → revert migration
3. Keep old code in separate branch for 1 month after cutover

---

## Part 10: Success Metrics

### Code Quality Metrics
- ✅ Reduce code duplication by >80% (eliminate 5+ duplicate blocks)
- ✅ Increase test coverage from ~30% to >85%
- ✅ Reduce cyclomatic complexity (avg <10 per function)
- ✅ 0 direct SQL executions outside repository layer

### Performance Metrics
- ✅ Proposal generation time < 5 seconds (p95)
- ✅ Mockup generation time < 3 seconds (p95)
- ✅ Asset-Management API calls < 100ms with caching (p95)
- ✅ Database query time < 50ms (p95)

### Reliability Metrics
- ✅ Proposal success rate > 99.5%
- ✅ Mockup success rate > 99%
- ✅ Zero path traversal vulnerabilities
- ✅ 100% of locations validated via Asset-Management

### Integration Metrics
- ✅ Asset-Management API availability > 99.9%
- ✅ Cache hit rate > 80% for location lookups
- ✅ Graceful degradation if Asset-Management is down

---

## Part 11: Documentation Requirements

### API Documentation
- OpenAPI/Swagger docs for all endpoints
- Request/response examples
- Error codes and handling
- Rate limits

### Architecture Documentation
- Service interaction diagrams
- Database schema diagrams
- Sequence diagrams for key workflows
- Caching strategy documentation

### Developer Documentation
- Setup guide
- Testing guide
- Deployment guide
- Troubleshooting guide

---

## Summary

This refactoring plan transforms Sales-Module from a monolithic, tightly-coupled codebase into a clean, modular, well-tested service that:

1. **Eliminates Code Duplication** - Single source of truth for all common logic
2. **Integrates Properly** - Asset-Management as authoritative data source
3. **Improves Modularity** - Clear separation between controllers, services, workflows
4. **Enhances Security** - Consistent path sanitization and validation
5. **Enables Testing** - Business logic isolated from HTTP/database concerns
6. **Fixes Database** - Normalized schema with proper types and relationships
7. **Maintains Compatibility** - Feature flags for gradual rollout
8. **Provides Observability** - Metrics and monitoring at all layers

The result is a production-grade service that's maintainable, testable, and scalable.
