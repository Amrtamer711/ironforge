"""
Network Assets endpoints.

Network assets are individual billboards/screens within a network.
They are NOT directly sellable - networks are sold as complete units.
These endpoints are for admin/management features.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.network_assets import (
    NetworkAsset,
    NetworkAssetCreate,
    NetworkAssetUpdate,
    NetworkAssetService,
)
from crm_security import TrustedUserContext, require_permission

router = APIRouter(prefix="/api/network-assets", tags=["Network Assets"])
logger = config.get_logger("api.routers.network_assets")

# Service singleton
_service = NetworkAssetService()


@router.get("")
def list_network_assets(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    network_id: int | None = Query(default=None, description="Filter by network"),
    type_id: int | None = Query(default=None, description="Filter by asset type"),
    active_only: bool = Query(default=True, description="Only return active assets"),
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:read")),
) -> list[NetworkAsset]:
    """
    List network assets with optional filters.

    Requires: assets:network_assets:read permission

    Network assets are individual billboards within a network.
    They are NOT directly sellable - the parent network is sold as a unit.
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.list_network_assets(
        companies=accessible or config.COMPANY_SCHEMAS,
        network_id=network_id,
        type_id=type_id,
        active_only=active_only,
    )


@router.get("/{company}/{asset_id}")
def get_network_asset(
    company: str,
    asset_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:read")),
) -> NetworkAsset:
    """Get a specific network asset. Requires: assets:network_assets:read"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    asset = _service.get_network_asset(company=company, asset_id=asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Network asset not found")
    return asset


@router.get("/by-key/{asset_key}")
def get_network_asset_by_key(
    asset_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:read")),
) -> NetworkAsset:
    """Get a network asset by its key. Requires: assets:network_assets:read"""
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    asset = _service.get_network_asset_by_key(
        asset_key=asset_key,
        companies=accessible or config.COMPANY_SCHEMAS,
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Network asset not found")
    return asset


@router.post("/{company}")
def create_network_asset(
    company: str,
    data: NetworkAssetCreate,
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:create")),
) -> NetworkAsset:
    """Create a new network asset. Requires: assets:network_assets:create"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    if company not in config.COMPANY_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid company: {company}")

    logger.info(f"User {user.get('id')} creating network asset in {company}")
    return _service.create_network_asset(company=company, data=data, created_by=user.get("id"))


@router.patch("/{company}/{asset_id}")
def update_network_asset(
    company: str,
    asset_id: int,
    data: NetworkAssetUpdate,
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:update")),
) -> NetworkAsset:
    """Update an existing network asset. Requires: assets:network_assets:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} updating network asset {asset_id} in {company}")
    asset = _service.update_network_asset(
        company=company,
        asset_id=asset_id,
        data=data,
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Network asset not found")
    return asset


@router.delete("/{company}/{asset_id}")
def delete_network_asset(
    company: str,
    asset_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:network_assets:delete")),
) -> dict:
    """Delete a network asset (soft delete). Requires: assets:network_assets:delete"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} deleting network asset {asset_id} in {company}")
    success = _service.delete_network_asset(company=company, asset_id=asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Network asset not found")
    return {"status": "deleted", "asset_id": asset_id}
