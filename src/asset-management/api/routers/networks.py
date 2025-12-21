"""
Networks endpoints.

Networks are sellable groupings of assets.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.networks import Network, NetworkCreate, NetworkUpdate, NetworkService
from crm_security import TrustedUserContext, require_permission

router = APIRouter(prefix="/api/networks", tags=["Networks"])
logger = config.get_logger("api.routers.networks")

# Service singleton
_service = NetworkService()


@router.get("")
def list_networks(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    active_only: bool = Query(default=True, description="Only return active networks"),
    user: TrustedUserContext = Depends(require_permission("assets:networks:read")),
) -> list[Network]:
    """
    List all networks. Requires: assets:networks:read

    Networks are sellable groupings of assets (e.g., "Abu Dhabi Highways").
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.list_networks(
        companies=accessible or config.COMPANY_SCHEMAS,
        active_only=active_only,
    )


@router.get("/{company}/{network_id}")
def get_network(
    company: str,
    network_id: int,
    include_types: bool = Query(default=True, description="Include asset types"),
    include_locations: bool = Query(default=False, description="Include locations"),
    user: TrustedUserContext = Depends(require_permission("assets:networks:read")),
) -> Network:
    """Get a specific network with optional nested data. Requires: assets:networks:read"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    network = _service.get_network(
        company=company,
        network_id=network_id,
        include_types=include_types,
        include_locations=include_locations,
    )
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return network


@router.post("/{company}")
def create_network(
    company: str,
    data: NetworkCreate,
    user: TrustedUserContext = Depends(require_permission("assets:networks:create")),
) -> Network:
    """Create a new network in a company schema. Requires: assets:networks:create"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    if company not in config.COMPANY_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid company: {company}")

    logger.info(f"User {user.get('id')} creating network in {company}")
    return _service.create_network(company=company, data=data, created_by=user.get("id"))


@router.patch("/{company}/{network_id}")
def update_network(
    company: str,
    network_id: int,
    data: NetworkUpdate,
    user: TrustedUserContext = Depends(require_permission("assets:networks:update")),
) -> Network:
    """Update an existing network. Requires: assets:networks:update"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} updating network {network_id} in {company}")
    network = _service.update_network(
        company=company,
        network_id=network_id,
        data=data,
    )
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return network


@router.delete("/{company}/{network_id}")
def delete_network(
    company: str,
    network_id: int,
    user: TrustedUserContext = Depends(require_permission("assets:networks:delete")),
) -> dict:
    """Delete a network (soft delete). Requires: assets:networks:delete"""
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.get('id')} deleting network {network_id} in {company}")
    success = _service.delete_network(company=company, network_id=network_id)
    if not success:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"status": "deleted", "network_id": network_id}
