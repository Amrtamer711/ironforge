"""
Locations endpoints.

Locations are individual sellable assets (billboards, screens, etc.).
They can be standalone or part of a network/type hierarchy.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.locations import Location, LocationCreate, LocationUpdate, LocationService
from core.packages import PackageService
from db.database import db
from crm_security import (
    TrustedUserContext,
    require_auth,
    require_permission,
)

router = APIRouter(prefix="/api/locations", tags=["Locations"])
logger = config.get_logger("api.routers.locations")

# Service singletons
_location_service = LocationService()
_package_service = PackageService()


@router.get("")
def list_locations(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    network_id: int | None = Query(default=None, description="Filter by network"),
    type_id: int | None = Query(default=None, description="Filter by asset type"),
    active_only: bool = Query(default=True, description="Only return active locations"),
    include_eligibility: bool = Query(default=False, description="Include eligibility info"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> list[Location]:
    """
    List locations with optional filters.

    Requires: assets:locations:read permission

    Locations are individual sellable assets. They can be:
    - Standalone (network_id=NULL) - directly sellable
    - Part of network/type hierarchy - also sellable individually
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _location_service.list_locations(
        companies=accessible or config.COMPANY_SCHEMAS,
        network_id=network_id,
        type_id=type_id,
        active_only=active_only,
        include_eligibility=include_eligibility,
    )


@router.get("/{company}/{location_id}")
def get_location(
    company: str,
    location_id: int,
    include_eligibility: bool = Query(default=True, description="Include eligibility details"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> Location:
    """Get a specific location with eligibility info. Requires: assets:locations:read"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    location = _location_service.get_location(
        company=company,
        location_id=location_id,
        include_eligibility=include_eligibility,
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.get("/by-key/{location_key}")
def get_location_by_key(
    location_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    include_eligibility: bool = Query(default=True, description="Include eligibility details"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> Location:
    """Get a location by its key. Requires: assets:locations:read"""
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    location = _location_service.get_location_by_key(
        location_key=location_key,
        companies=accessible or config.COMPANY_SCHEMAS,
        include_eligibility=include_eligibility,
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.post("/{company}")
def create_location(
    company: str,
    data: LocationCreate,
    user: TrustedUserContext = Depends(require_permission("assets:locations:create")),
) -> Location:
    """Create a new location. Requires: assets:locations:create"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    if company not in config.COMPANY_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid company: {company}")

    logger.info(f"User {user.get('id')} creating location in {company}")
    return _location_service.create_location(company=company, data=data, created_by=user.get("id"))


@router.patch("/{company}/{location_id}")
def update_location(
    company: str,
    location_id: int,
    data: LocationUpdate,
    user: TrustedUserContext = Depends(require_permission("assets:locations:update")),
) -> Location:
    """Update an existing location. Requires: assets:locations:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} updating location {location_id} in {company}")
    location = _location_service.update_location(
        company=company,
        location_id=location_id,
        data=data,
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.delete("/{company}/{location_id}")
def delete_location(
    company: str,
    location_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:locations:delete")),
) -> dict:
    """Delete a location (soft delete). Requires: assets:locations:delete"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} deleting location {location_id} in {company}")
    success = _location_service.delete_location(company=company, location_id=location_id)
    if not success:
        raise HTTPException(status_code=404, detail="Location not found")
    return {"status": "deleted", "location_id": location_id}


@router.post("/expand")
def expand_to_locations(
    items: list[dict],
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> list[dict]:
    """
    Expand sellable items (packages, networks, assets) to flat list of locations.

    Requires: assets:locations:read permission

    Used by proposal generator to resolve what locations are included.

    Request body:
    ```json
    [
        {"item_type": "package", "package_id": 1, "company": "backlite_dubai"},
        {"item_type": "network", "network_id": 5, "company": "backlite_abudhabi"},
        {"item_type": "asset", "location_id": 42, "company": "backlite_dubai"}
    ]
    ```
    """
    all_locations = []
    seen_ids = set()

    for item in items:
        item_type = item.get("item_type")
        company = item.get("company")

        if not company:
            continue

        locations = []

        if item_type == "package":
            package_id = item.get("package_id")
            if package_id:
                locations = db.get_package_locations(package_id, company)

        elif item_type == "network":
            network_id = item.get("network_id")
            if network_id:
                locations = db.list_locations([company], network_id=network_id)

        elif item_type == "asset":
            location_id = item.get("location_id")
            if location_id:
                loc = db.get_location(location_id, [company])
                if loc:
                    locations = [loc]

        # Add unique locations
        for loc in locations:
            loc_id = loc.get("id")
            if loc_id and loc_id not in seen_ids:
                seen_ids.add(loc_id)
                all_locations.append(loc)

    return all_locations
