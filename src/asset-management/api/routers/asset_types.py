"""
Asset Types endpoints.

Asset Types are organizational categories within networks (NOT sellable).
Example: "LED Billboard 20x10", "Digital Mupi" within a Highway Network.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.asset_types import AssetType, AssetTypeCreate, AssetTypeUpdate, AssetTypeService
from crm_security import TrustedUserContext, require_permission

router = APIRouter(prefix="/api/asset-types", tags=["Asset Types"])
logger = config.get_logger("api.routers.asset_types")

# Service singleton
_service = AssetTypeService()


@router.get("")
def list_asset_types(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    network_id: int | None = Query(default=None, description="Filter by network"),
    active_only: bool = Query(default=True, description="Only return active types"),
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:read")),
) -> list[AssetType]:
    """
    List all asset types. Requires: assets:asset_types:read

    Asset types are organizational categories (NOT sellable).
    They belong to networks and group network assets.
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.list_asset_types(
        companies=accessible or config.COMPANY_SCHEMAS,
        network_id=network_id,
        active_only=active_only,
    )


@router.get("/by-network/{network_key}")
def get_asset_types_by_network_key(
    network_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    active_only: bool = Query(default=True, description="Only return active types"),
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:read")),
) -> list[AssetType]:
    """
    Get asset types for a specific network by network_key.

    Requires: assets:asset_types:read

    This endpoint looks up the network by key and returns its asset types.
    For standalone networks, returns an empty list (no asset types).
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.get_asset_types_by_network_key(
        network_key=network_key,
        companies=accessible or config.COMPANY_SCHEMAS,
        active_only=active_only,
    )


@router.get("/{company}/{type_id}")
def get_asset_type(
    company: str,
    type_id: int,
    include_locations: bool = Query(default=False, description="Include network assets"),
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:read")),
) -> AssetType:
    """Get a specific asset type. Requires: assets:asset_types:read"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    asset_type = _service.get_asset_type(
        company=company,
        type_id=type_id,
        include_locations=include_locations,
    )
    if not asset_type:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return asset_type


@router.post("/{company}")
def create_asset_type(
    company: str,
    data: AssetTypeCreate,
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:create")),
) -> AssetType:
    """Create a new asset type within a network. Requires: assets:asset_types:create"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    if company not in config.COMPANY_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid company: {company}")

    logger.info(f"User {user.get('id')} creating asset type in {company}")
    return _service.create_asset_type(company=company, data=data, created_by=user.get("id"))


@router.patch("/{company}/{type_id}")
def update_asset_type(
    company: str,
    type_id: int,
    data: AssetTypeUpdate,
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:update")),
) -> AssetType:
    """Update an existing asset type. Requires: assets:asset_types:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} updating asset type {type_id} in {company}")
    asset_type = _service.update_asset_type(
        company=company,
        type_id=type_id,
        data=data,
    )
    if not asset_type:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return asset_type


@router.delete("/{company}/{type_id}")
def delete_asset_type(
    company: str,
    type_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:asset_types:delete")),
) -> dict:
    """Delete an asset type (soft delete). Requires: assets:asset_types:delete"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} deleting asset type {type_id} in {company}")
    success = _service.delete_asset_type(company=company, type_id=type_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return {"status": "deleted", "type_id": type_id}
