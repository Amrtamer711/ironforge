"""
Packages endpoints.

Packages are company-specific bundles of networks and/or individual assets.
They are sellable as a single unit.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.packages import Package, PackageCreate, PackageUpdate, PackageService
from crm_security import TrustedUserContext, require_permission

router = APIRouter(prefix="/api/packages", tags=["Packages"])
logger = config.get_logger("api.routers.packages")

# Service singleton
_service = PackageService()


@router.get("")
def list_packages(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    active_only: bool = Query(default=True, description="Only return active packages"),
    user: TrustedUserContext = Depends(require_permission("assets:packages:read")),
) -> list[Package]:
    """
    List all packages. Requires: assets:packages:read

    Packages are company-specific bundles that can contain:
    - Entire networks (all locations in the network)
    - Individual assets (specific locations)
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.list_packages(
        companies=accessible or config.COMPANY_SCHEMAS,
        active_only=active_only,
    )


@router.get("/{company}/{package_id}")
def get_package(
    company: str,
    package_id: int,
    expand: bool = Query(default=False, description="Expand to show all locations"),
    user: TrustedUserContext = Depends(require_permission("assets:packages:read")),
) -> Package:
    """Get a specific package with optional location expansion. Requires: assets:packages:read"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    package = _service.get_package(
        company=company,
        package_id=package_id,
        expand_locations=expand,
    )
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.post("/{company}")
def create_package(
    company: str,
    data: PackageCreate,
    user: TrustedUserContext = Depends(require_permission("assets:packages:create")),
) -> Package:
    """Create a new package. Requires: assets:packages:create"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    if company not in config.COMPANY_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid company: {company}")

    logger.info(f"User {user.get('id')} creating package in {company}")
    return _service.create_package(company=company, data=data, created_by=user.get("id"))


@router.patch("/{company}/{package_id}")
def update_package(
    company: str,
    package_id: int,
    data: PackageUpdate,
    user: TrustedUserContext = Depends(require_permission("assets:packages:update")),
) -> Package:
    """Update an existing package. Requires: assets:packages:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} updating package {package_id} in {company}")
    package = _service.update_package(
        company=company,
        package_id=package_id,
        data=data,
    )
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.delete("/{company}/{package_id}")
def delete_package(
    company: str,
    package_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:packages:delete")),
) -> dict:
    """Delete a package (soft delete). Requires: assets:packages:delete"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} deleting package {package_id} in {company}")
    success = _service.delete_package(company=company, package_id=package_id)
    if not success:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"status": "deleted", "package_id": package_id}


@router.post("/{company}/{package_id}/items")
def add_package_item(
    company: str,
    package_id: int,
    item_type: str = Query(..., description="'network' or 'asset'"),
    network_id: int | None = Query(default=None, description="Network ID (if item_type='network')"),
    location_id: int | None = Query(default=None, description="Location ID (if item_type='asset')"),
    user: TrustedUserContext = Depends(require_permission("assets:packages:update")),
) -> Package:
    """Add an item (network or asset) to a package. Requires: assets:packages:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    # Verify package exists
    package = _service.get_package(company=company, package_id=package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    # Add item
    logger.info(f"User {user.get('id')} adding {item_type} to package {package_id}")
    _service.add_item(
        company=company,
        package_id=package_id,
        item_type=item_type,
        network_id=network_id,
        location_id=location_id,
    )

    # Return updated package
    return _service.get_package(company=company, package_id=package_id)


@router.delete("/{company}/{package_id}/items/{item_id}")
def remove_package_item(
    company: str,
    package_id: int,
    item_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:packages:update")),
) -> Package:
    """Remove an item from a package. Requires: assets:packages:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    # Verify package exists
    package = _service.get_package(company=company, package_id=package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    # Remove item
    logger.info(f"User {user.get('id')} removing item {item_id} from package {package_id}")
    success = _service.remove_item(company=company, item_id=item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    # Return updated package
    return _service.get_package(company=company, package_id=package_id)


@router.get("/{company}/{package_id}/locations")
def get_package_locations(
    company: str,
    package_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:packages:read")),
) -> list[dict]:
    """
    Get all locations included in a package (expanded). Requires: assets:packages:read

    This resolves networks to their individual locations and includes
    directly added assets.
    """
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    # Verify package exists
    package = _service.get_package(company=company, package_id=package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    locations = _service.get_package_locations(company=company, package_id=package_id)
    return [loc.model_dump() for loc in locations]
