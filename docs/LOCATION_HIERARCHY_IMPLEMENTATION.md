# Location Hierarchy Implementation Plan

## Overview

This document outlines the implementation plan for adding hierarchical location management to the CRM platform. The new model supports:

- **Networks**: Groups of assets (sellable as a whole)
- **Asset Types**: Organizational categories within networks (NOT sellable)
- **Locations/Assets**: Individual billboards/screens (sellable individually)
- **Packages**: Company-specific bundles of networks and/or assets (sellable)

### Architecture Decision

The location/asset management functionality will eventually live in a **dedicated `asset-management` service** alongside `sales-module` and `unified-ui`. For now, the database schemas are created within `sales-module`, but will be migrated to the new service.

```
CRM/
├── src/
│   ├── unified-ui/           # Auth gateway + frontend (port 3005)
│   ├── sales-module/         # Proposal bot backend (port 8000)
│   └── asset-management/     # NEW: Asset/location management (port 8001)
```

---

## 1. Data Model

### 1.1 Hierarchy Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPANY INVENTORY (per-schema)                        │
└─────────────────────────────────────────────────────────────────────────────┘

STANDALONE ASSETS (network_id = NULL, type_id = NULL):
├── ADH-STATIC-001 "Corniche Road Billboard" ─────────────────── SELLABLE ✓
├── ADH-DIGITAL-002 "Marina Mall Entrance" ───────────────────── SELLABLE ✓
└── ADH-UNI-003 "Airport Road Unipole" ───────────────────────── SELLABLE ✓


HIGHWAY NETWORK ──────────────────────────────────────────────── SELLABLE ✓
│
├── LED Billboard 20x10 (type) ───────────────────────────────── NOT SELLABLE ✗
│   ├── ADH-HWY-LED-001 "Sheikh Zayed Exit 12" ───────────────── SELLABLE ✓
│   ├── ADH-HWY-LED-002 "Sheikh Zayed Exit 15" ───────────────── SELLABLE ✓
│   └── ADH-HWY-LED-003 "Yas Island Gateway" ─────────────────── SELLABLE ✓
│
├── Digital Mupi (type) ──────────────────────────────────────── NOT SELLABLE ✗
│   ├── ADH-HWY-MUP-001 "Bus Stop Khalifa City" ──────────────── SELLABLE ✓
│   └── ADH-HWY-MUP-002 "Bus Stop Saadiyat" ──────────────────── SELLABLE ✓
│
└── Unipole 14x48 (type) ─────────────────────────────────────── NOT SELLABLE ✗
    ├── ADH-HWY-UNI-001 "E11 Interchange" ────────────────────── SELLABLE ✓
    └── ADH-HWY-UNI-002 "Musaffah Exit" ──────────────────────── SELLABLE ✓
```

### 1.2 Database Relationships

```
networks (1) ──────────────────┐
                               │ 1:N
                               ▼
asset_types (N) ───────────────┐  (each type belongs to ONE network)
                               │ 1:N
                               ▼
locations (N) ─────────────────   (each asset belongs to ONE type, or standalone)
    - network_id: NULL (standalone) OR FK → networks
    - type_id: NULL (standalone) OR FK → asset_types
```

### 1.3 Sellable Units

| Entity | Sellable | Location |
|--------|----------|----------|
| Package | ✓ Yes | company schema (bundles networks/assets within company) |
| Network | ✓ Yes | company schema |
| Location/Asset | ✓ Yes | company schema |
| Type | ✗ No | company schema (organizational only) |

---

## 2. Schema Changes

### 2.1 New Tables (Per-Company Schema)

#### `networks` table
```sql
CREATE TABLE IF NOT EXISTS {schema}.networks (
    id BIGSERIAL PRIMARY KEY,
    network_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);
```

#### `asset_types` table
```sql
CREATE TABLE IF NOT EXISTS {schema}.asset_types (
    id BIGSERIAL PRIMARY KEY,
    network_id BIGINT NOT NULL REFERENCES {schema}.networks(id) ON DELETE CASCADE,
    type_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    specs JSONB DEFAULT '{}',  -- dimensions, display_type, etc.
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    CONSTRAINT asset_types_unique UNIQUE (network_id, type_key)
);
```

#### `locations` table modifications
```sql
ALTER TABLE {schema}.locations
    ADD COLUMN network_id BIGINT REFERENCES {schema}.networks(id) ON DELETE SET NULL,
    ADD COLUMN type_id BIGINT REFERENCES {schema}.asset_types(id) ON DELETE SET NULL;
```

### 2.2 New Tables (Per-Company Schema) - Packages

#### `packages` table
```sql
CREATE TABLE IF NOT EXISTS {schema}.packages (
    id BIGSERIAL PRIMARY KEY,
    package_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);
```

#### `package_items` table
```sql
CREATE TABLE IF NOT EXISTS {schema}.package_items (
    id BIGSERIAL PRIMARY KEY,
    package_id BIGINT NOT NULL REFERENCES {schema}.packages(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('network', 'asset')),
    network_id BIGINT REFERENCES {schema}.networks(id) ON DELETE CASCADE,
    location_id BIGINT REFERENCES {schema}.locations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT package_items_check CHECK (
        (item_type = 'network' AND network_id IS NOT NULL AND location_id IS NULL) OR
        (item_type = 'asset' AND location_id IS NOT NULL AND network_id IS NULL)
    )
);
```

### 2.3 Modified Tables (Public Schema)

#### `proposal_locations` modifications
```sql
ALTER TABLE public.proposal_locations
    ADD COLUMN item_type TEXT DEFAULT 'asset' CHECK (item_type IN ('network', 'asset', 'package')),
    ADD COLUMN network_id BIGINT,
    ADD COLUMN package_id BIGINT REFERENCES public.packages(id);
```

---

## 3. Implementation Phases

### Phase 1: Database Migration
**Files:**
- `src/sales-module/db/migrations/salesbot/03_add_networks_hierarchy.sql`

**Tasks:**
1. Create `networks` table in company schemas
2. Create `asset_types` table in company schemas
3. Add `network_id`, `type_id` columns to `locations`
4. Create `packages`, `package_items` tables in public schema
5. Modify `proposal_locations` to support item types
6. Update `create_company_schema()` function
7. Update cross-schema views

### Phase 2: Migration Script Update
**Files:**
- `src/sales-module/db/scripts/migrate_to_supabase.py`

**Tasks:**
1. Add `seed_networks()` function
2. Add `seed_asset_types()` function
3. Add functions to assign locations to networks/types
4. Add sample data for Abu Dhabi networks

### Phase 3: Centralized Location Module
**Files:**
```
src/sales-module/locations/
├── __init__.py           # Public exports
├── models.py             # Pydantic models
├── schemas.py            # Request/Response schemas
├── repository.py         # Database access layer
├── service.py            # Business logic
├── router.py             # API endpoints
└── exceptions.py         # Custom exceptions
```

**Tasks:**
1. Create module structure
2. Implement Pydantic models
3. Implement repository layer
4. Implement service layer with business logic
5. Create API endpoints
6. Write tests

### Phase 4: Refactor Existing Code
**Files to modify:**
- `src/sales-module/services/proposal_generator.py`
- `src/sales-module/services/bo_parser.py`
- Any other files with location queries

**Tasks:**
1. Replace direct location queries with `LocationService`
2. Update proposal generator to use `expand_to_locations()`
3. Update BO parser to use `LocationService`
4. Remove scattered location logic

---

## 4. Centralized Location Module API

### 4.1 Models

```python
# locations/models.py

class Network(BaseModel):
    id: int
    network_key: str
    name: str
    description: str | None
    company: str  # schema name
    asset_types: list["AssetType"] = []
    location_count: int = 0
    is_active: bool = True

class AssetType(BaseModel):
    id: int
    type_key: str
    name: str
    network_id: int
    description: str | None
    specs: dict = {}  # dimensions, display_type, etc.
    location_count: int = 0
    is_active: bool = True

class Location(BaseModel):
    id: int
    location_key: str
    display_name: str
    company: str
    network: Network | None = None      # None = standalone
    asset_type: AssetType | None = None # None = standalone
    display_type: str
    # ... existing fields

class Package(BaseModel):
    id: int
    package_key: str
    name: str
    description: str | None
    items: list["PackageItem"] = []
    is_active: bool = True

class PackageItem(BaseModel):
    item_type: Literal["network", "asset"]
    company: str
    network: Network | None = None
    location: Location | None = None

class SellableItem(BaseModel):
    """Input for expand_to_locations()"""
    item_type: Literal["package", "network", "asset"]
    package_id: int | None = None
    network_id: int | None = None
    location_id: int | None = None
    company: str | None = None  # required for network/asset
```

### 4.2 Service Interface

```python
# locations/service.py

class LocationService:
    """Centralized location management"""

    # === QUERIES ===
    async def get_all_locations(
        companies: list[str],
        include_networks: bool = True
    ) -> list[Location]:
        """Get all locations for given companies"""

    async def get_standalone_locations(
        companies: list[str]
    ) -> list[Location]:
        """Get locations not part of any network"""

    async def get_network_locations(
        network_id: int,
        company: str
    ) -> list[Location]:
        """Get all locations in a network"""

    # === NETWORKS ===
    async def get_networks(
        companies: list[str]
    ) -> list[Network]:
        """Get all networks for given companies"""

    async def get_network_with_assets(
        network_id: int,
        company: str
    ) -> Network:
        """Get network with all its types and locations"""

    async def create_network(
        company: str,
        data: NetworkCreate
    ) -> Network:
        """Create a new network"""

    # === ASSET TYPES ===
    async def get_asset_types(
        network_id: int,
        company: str
    ) -> list[AssetType]:
        """Get all types in a network"""

    async def create_asset_type(
        network_id: int,
        company: str,
        data: AssetTypeCreate
    ) -> AssetType:
        """Create a new asset type"""

    # === PACKAGES ===
    async def get_packages() -> list[Package]:
        """Get all packages"""

    async def get_package_expanded(
        package_id: int
    ) -> Package:
        """Get package with all items expanded"""

    async def create_package(
        data: PackageCreate
    ) -> Package:
        """Create a new package"""

    # === SELLABLE EXPANSION ===
    async def expand_to_locations(
        items: list[SellableItem]
    ) -> list[Location]:
        """
        Expand packages/networks/assets to flat list of locations.
        Used by proposal generator.

        Example:
            items = [
                SellableItem(item_type="package", package_id=1),
                SellableItem(item_type="network", network_id=5, company="backlite_abudhabi"),
                SellableItem(item_type="asset", location_id=42, company="backlite_dubai"),
            ]
            locations = await expand_to_locations(items)
            # Returns: [Location(...), Location(...), ...]
        """

    # === AVAILABILITY ===
    async def check_availability(
        location_ids: list[int],
        company: str,
        start_date: date,
        end_date: date
    ) -> dict[int, list[Occupation]]:
        """Check location availability for date range"""
```

### 4.3 API Endpoints

```python
# locations/router.py

router = APIRouter(prefix="/api/locations", tags=["locations"])

# === LOCATIONS ===
@router.get("/")
async def list_locations(
    companies: list[str] = Query(...),
    include_networks: bool = True,
    standalone_only: bool = False
) -> list[LocationResponse]

@router.get("/{company}/{location_id}")
async def get_location(
    company: str,
    location_id: int
) -> LocationResponse

# === NETWORKS ===
@router.get("/networks")
async def list_networks(
    companies: list[str] = Query(...)
) -> list[NetworkResponse]

@router.get("/networks/{company}/{network_id}")
async def get_network(
    company: str,
    network_id: int,
    include_locations: bool = True
) -> NetworkResponse

@router.post("/networks/{company}")
async def create_network(
    company: str,
    data: NetworkCreate
) -> NetworkResponse

# === ASSET TYPES ===
@router.get("/networks/{company}/{network_id}/types")
async def list_asset_types(
    company: str,
    network_id: int
) -> list[AssetTypeResponse]

@router.post("/networks/{company}/{network_id}/types")
async def create_asset_type(
    company: str,
    network_id: int,
    data: AssetTypeCreate
) -> AssetTypeResponse

# === PACKAGES ===
@router.get("/packages")
async def list_packages() -> list[PackageResponse]

@router.get("/packages/{package_id}")
async def get_package(
    package_id: int,
    expand: bool = True
) -> PackageResponse

@router.post("/packages")
async def create_package(
    data: PackageCreate
) -> PackageResponse

# === EXPANSION ===
@router.post("/expand")
async def expand_sellables(
    items: list[SellableItem]
) -> list[LocationResponse]:
    """Expand packages/networks to individual locations"""
```

---

## 5. Sample Data

### 5.1 Abu Dhabi Networks Example

```sql
-- Network: Abu Dhabi Highways
INSERT INTO backlite_abudhabi.networks (network_key, name, description) VALUES
('adh_highways', 'Abu Dhabi Highways', 'Premium highway locations across Abu Dhabi');

-- Asset Types under this network
INSERT INTO backlite_abudhabi.asset_types (network_id, type_key, name, specs) VALUES
((SELECT id FROM backlite_abudhabi.networks WHERE network_key = 'adh_highways'),
 'led_20x10', 'LED Billboard 20x10',
 '{"width": "20m", "height": "10m", "display_type": "digital"}'),

((SELECT id FROM backlite_abudhabi.networks WHERE network_key = 'adh_highways'),
 'unipole_14x48', 'Unipole 14x48',
 '{"width": "14ft", "height": "48ft", "display_type": "static"}'),

((SELECT id FROM backlite_abudhabi.networks WHERE network_key = 'adh_highways'),
 'digital_mupi', 'Digital Mupi',
 '{"width": "1.2m", "height": "1.8m", "display_type": "digital"}');

-- Update existing locations to belong to network/type
UPDATE backlite_abudhabi.locations SET
    network_id = (SELECT id FROM backlite_abudhabi.networks WHERE network_key = 'adh_highways'),
    type_id = (SELECT id FROM backlite_abudhabi.asset_types WHERE type_key = 'led_20x10')
WHERE location_key IN ('adh_led_001', 'adh_led_002');
```

### 5.2 Package Example

```sql
-- Abu Dhabi premium bundle (per-company)
INSERT INTO backlite_abudhabi.packages (package_key, name, description) VALUES
('adh_premium_2024', 'Abu Dhabi Premium Bundle 2024', 'Premium locations across Abu Dhabi');

-- Package items - include entire Highway Network
INSERT INTO backlite_abudhabi.package_items (package_id, item_type, network_id) VALUES
((SELECT id FROM backlite_abudhabi.packages WHERE package_key = 'adh_premium_2024'),
 'network',
 (SELECT id FROM backlite_abudhabi.networks WHERE network_key = 'adh_highways'));

-- Package items - include specific standalone assets
INSERT INTO backlite_abudhabi.package_items (package_id, item_type, location_id) VALUES
((SELECT id FROM backlite_abudhabi.packages WHERE package_key = 'adh_premium_2024'),
 'asset',
 (SELECT id FROM backlite_abudhabi.locations WHERE location_key = 'adh_standalone_001'));
```

---

## 6. Migration Script Updates

### 6.1 New Functions

```python
def seed_networks(supabase: Client, company: str, dry_run: bool = False) -> int:
    """Seed networks for a company from configuration."""

def seed_asset_types(supabase: Client, company: str,
                     network_map: dict, dry_run: bool = False) -> int:
    """Seed asset types for networks."""

def assign_locations_to_hierarchy(supabase: Client, company: str,
                                  network_map: dict, type_map: dict,
                                  dry_run: bool = False) -> int:
    """Assign existing locations to networks and types based on patterns."""

def seed_packages(supabase: Client, dry_run: bool = False) -> int:
    """Seed cross-company packages."""
```

### 6.2 Configuration Format

```python
NETWORK_CONFIG = {
    'backlite_abudhabi': {
        'networks': [
            {
                'network_key': 'adh_highways',
                'name': 'Abu Dhabi Highways',
                'description': 'Premium highway locations',
                'types': [
                    {
                        'type_key': 'led_20x10',
                        'name': 'LED Billboard 20x10',
                        'specs': {'width': '20m', 'height': '10m', 'display_type': 'digital'},
                        'location_patterns': ['adh_led_*', 'adh_highway_led_*'],
                    },
                    {
                        'type_key': 'unipole_14x48',
                        'name': 'Unipole 14x48',
                        'specs': {'width': '14ft', 'height': '48ft', 'display_type': 'static'},
                        'location_patterns': ['adh_uni_*'],
                    },
                ],
            },
        ],
    },
}
```

---

## 7. Testing Plan

### 7.1 Unit Tests

- [ ] Test network CRUD operations
- [ ] Test asset type CRUD operations
- [ ] Test location hierarchy assignment
- [ ] Test package CRUD operations
- [ ] Test `expand_to_locations()` with various inputs

### 7.2 Integration Tests

- [ ] Test proposal generation with networks
- [ ] Test proposal generation with packages
- [ ] Test cross-company package expansion
- [ ] Test availability checking across hierarchy

### 7.3 Migration Tests

- [ ] Test migration script with dry-run
- [ ] Test migration on dev database
- [ ] Verify data integrity after migration

---

## 8. Rollback Plan

If issues are encountered:

1. **Schema rollback**: Run `04_rollback_networks_hierarchy.sql`
2. **Data preservation**: All original data remains intact (additive migration)
3. **Code rollback**: Revert to previous commit

---

## 9. Timeline

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| 1 | Database Migration SQL | None |
| 2 | Migration Script Update | Phase 1 |
| 3 | Centralized Location Module | Phase 1 |
| 4 | Refactor Existing Code | Phase 3 |
| 5 | Testing & Validation | Phase 4 |

---

## 10. Checklist

### Database
- [ ] Create `03_add_networks_hierarchy.sql`
- [ ] Test migration on dev database
- [ ] Update `create_company_schema()` function
- [ ] Update cross-schema views

### Migration Script
- [ ] Add network seeding functions
- [ ] Add asset type seeding functions
- [ ] Add package seeding functions
- [ ] Add sample Abu Dhabi data
- [ ] Test with `--dry-run`

### Location Module
- [ ] Create module structure
- [ ] Implement models
- [ ] Implement repository
- [ ] Implement service
- [ ] Create API endpoints
- [ ] Write tests

### Integration
- [ ] Refactor proposal generator
- [ ] Refactor BO parser
- [ ] Update frontend (if needed)
- [ ] End-to-end testing

---

## 11. Location Eligibility & Service Visibility

Locations/networks should only appear in specific services (proposal generator, mockup generator, etc.) when they have sufficient data. This prevents users from creating proposals with incomplete information.

### 11.1 Eligibility Criteria Model

```python
class ServiceEligibility(BaseModel):
    """Defines which services a location/network can appear in"""
    proposal_generator: bool = False
    mockup_generator: bool = False
    availability_calendar: bool = False
    # Add more services as needed

class EligibilityReason(BaseModel):
    """Why a location is/isn't eligible"""
    eligible: bool
    missing_fields: list[str] = []
    warnings: list[str] = []
```

### 11.2 Required Fields by Service

| Service | Asset (Location) Required Fields | Network Required Fields |
|---------|----------------------------------|-------------------------|
| **Proposal Generator** | display_name, display_type, rate_card | name, at least 1 active location with rate_card |
| **Mockup Generator** | display_name, mockup_frame, template_path | N/A (networks don't have mockups) |
| **Availability Calendar** | display_name | name, at least 1 active location |

### 11.3 Database Schema Addition

```sql
-- Add eligibility tracking to locations
ALTER TABLE {schema}.locations ADD COLUMN IF NOT EXISTS
    service_eligibility JSONB DEFAULT '{
        "proposal_generator": false,
        "mockup_generator": false,
        "availability_calendar": false
    }';

-- Trigger to auto-update eligibility on location changes
CREATE OR REPLACE FUNCTION update_location_eligibility()
RETURNS TRIGGER AS $$
BEGIN
    NEW.service_eligibility = jsonb_build_object(
        'proposal_generator', (
            NEW.display_name IS NOT NULL AND
            NEW.display_type IS NOT NULL AND
            EXISTS (SELECT 1 FROM rate_cards WHERE location_id = NEW.id AND is_active = true)
        ),
        'mockup_generator', (
            NEW.display_name IS NOT NULL AND
            EXISTS (SELECT 1 FROM mockup_frames WHERE location_id = NEW.id)
        ),
        'availability_calendar', (
            NEW.display_name IS NOT NULL AND
            NEW.is_active = true
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### 11.4 Service Integration

```python
# In LocationService
async def get_eligible_locations(
    service: Literal["proposal_generator", "mockup_generator", "availability_calendar"],
    companies: list[str],
    include_networks: bool = True
) -> list[Location]:
    """Get only locations eligible for a specific service"""

async def check_eligibility(
    location_id: int,
    company: str,
    service: str
) -> EligibilityReason:
    """Check why a location is/isn't eligible for a service"""

async def get_eligible_networks(
    service: str,
    companies: list[str]
) -> list[Network]:
    """Get networks where ALL locations are eligible for service"""
```

### 11.5 API Response Enhancement

```python
class LocationResponse(BaseModel):
    id: int
    location_key: str
    display_name: str
    # ... other fields

    # Eligibility info
    service_eligibility: dict[str, bool]
    eligibility_details: dict[str, EligibilityReason] | None = None  # Optional detailed info
```

---

## 12. Future: Dedicated Asset-Management Service

> **Note**: The `asset-management` service will be built fresh alongside existing services. Database schemas are created in `sales-module` Supabase for now, but `asset-management` will connect to its own Supabase project when ready.

### 12.1 Service Architecture

```
CRM/
├── src/
│   ├── unified-ui/           # Auth gateway + frontend (port 3005)
│   │   └── Uses: unified-ui Supabase project
│   │
│   ├── sales-module/         # Proposal bot backend (port 8000)
│   │   └── Uses: salesbot Supabase project
│   │
│   └── asset-management/     # NEW: Asset/location management (port 8001)
│       ├── app/
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── api/
│       │   │   └── v1/
│       │   │       ├── networks.py
│       │   │       ├── asset_types.py
│       │   │       ├── locations.py
│       │   │       ├── packages.py
│       │   │       └── eligibility.py
│       │   ├── models/
│       │   ├── services/
│       │   │   ├── location_service.py
│       │   │   └── eligibility_service.py
│       │   ├── repositories/
│       │   └── schemas/
│       ├── db/
│       │   ├── migrations/
│       │   └── scripts/
│       ├── tests/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── pyproject.toml
```

### 12.2 New Supabase Project

Create a dedicated Supabase project for asset management:

```bash
# Project: asset-management
# URL: https://[project-ref].supabase.co
# Purpose: Asset inventory, networks, packages, eligibility management
```

**Environment Variables** (add to `.env`):
```bash
# Asset Management Supabase
ASSET_MGMT_SUPABASE_URL=https://[project-ref].supabase.co
ASSET_MGMT_SUPABASE_KEY=eyJ...
ASSET_MGMT_SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### 12.3 Docker Compose Integration

Add to `docker/docker-compose.yml`:

```yaml
services:
  # ... existing services ...

  asset-management:
    build:
      context: ../src/asset-management
      dockerfile: Dockerfile
    container_name: crm-asset-management
    ports:
      - "8001:8001"
    environment:
      - SUPABASE_URL=${ASSET_MGMT_SUPABASE_URL}
      - SUPABASE_KEY=${ASSET_MGMT_SUPABASE_KEY}
      - SUPABASE_SERVICE_ROLE_KEY=${ASSET_MGMT_SUPABASE_SERVICE_ROLE_KEY}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - crm-network
```

### 12.4 Makefile Updates

Add to root `Makefile`:

```makefile
# Asset Management Service
asset-mgmt-dev:
	cd src/asset-management && uvicorn app.main:app --reload --port 8001

asset-mgmt-test:
	cd src/asset-management && pytest tests/ -v
```

### 12.5 run_all_services.py Updates

```python
SERVICES = [
    # ... existing services ...
    {
        "name": "asset-management",
        "path": "src/asset-management",
        "command": ["uvicorn", "app.main:app", "--reload", "--port", "8001"],
        "port": 8001,
        "health_check": "http://localhost:8001/health",
    },
]
```

### 12.6 Inter-Service Communication

Sales-module calls asset-management for location data:

```python
# In sales-module, calling asset-management
async def get_eligible_locations_for_proposal(company: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ASSET_MGMT_URL}/api/v1/locations",
            params={"service": "proposal_generator", "company": company}
        )
        return response.json()
```

---

## 13. Summary: Current vs Future State

### Current State (After This Implementation)

```
┌─────────────────────────────────────────────────────────────────┐
│                         CRM Platform                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  unified-ui (port 3005)          sales-module (port 8000)       │
│  ├── Auth gateway                ├── Proposal generation        │
│  ├── Frontend                    ├── BO parsing                 │
│  └── Supabase: unified-ui        ├── locations/ module  ◄──┐   │
│                                  └── Supabase: salesbot     │   │
│                                      ├── networks           │   │
│                                      ├── asset_types        │   │
│                                      ├── locations      ────┘   │
│                                      ├── packages               │
│                                      └── proposals              │
└─────────────────────────────────────────────────────────────────┘
```

### Future State (With Asset-Management Service)

```
┌─────────────────────────────────────────────────────────────────┐
│                         CRM Platform                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  unified-ui        sales-module        asset-management         │
│  (port 3005)       (port 8000)         (port 8001)              │
│  ├── Auth          ├── Proposals  ───► ├── Networks API         │
│  ├── Frontend      ├── BO parsing      ├── Locations API        │
│  └── Supabase:     └── Supabase:       ├── Packages API         │
│      unified-ui        salesbot        ├── Eligibility API      │
│                                        └── Supabase:            │
│                                            asset-mgmt           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 14. Quick Reference

### SQL Migration Files
| File | Purpose | Run Order |
|------|---------|-----------|
| `01_schema.sql` | Base schema with networks support | 1 (new installs) |
| `02_add_location_company.sql` | Add location_company columns | 2 (if needed) |
| `03_add_networks_hierarchy.sql` | Add networks/types to existing DB | 3 (migrations) |

### Key Database Functions
| Function | Purpose |
|----------|---------|
| `get_network_locations(company, network_id)` | Get all locations in a network |
| `expand_package_to_locations(company, package_id)` | Expand package to location list |

### Key Views
| View | Purpose |
|------|---------|
| `public.all_networks` | All networks across companies |
| `public.all_asset_types` | All types across companies |
| `public.all_packages` | All packages across companies |
| `public.all_locations` | All locations across companies |

### Eligibility Services
| Endpoint | Purpose |
|----------|---------|
| `GET /locations?service=proposal_generator` | Get eligible locations for proposals |
| `GET /locations/{id}/eligibility` | Check why location is/isn't eligible |
| `GET /networks?service=proposal_generator` | Get networks with all eligible locations |
