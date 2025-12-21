"""
Eligibility endpoints.

Eligibility determines which locations/networks can appear in specific services
(proposal generator, mockup generator, etc.) based on required field completion.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import config
from core.eligibility import (
    EligibilityCheck,
    EligibilityService,
    BulkEligibilityItem,
)
from crm_security import TrustedUserContext, require_auth, require_permission

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility"])
logger = config.get_logger("api.routers.eligibility")

# Service singleton
_service = EligibilityService()


@router.get("/services")
def list_services(
    user: TrustedUserContext = Depends(require_auth),
) -> list[str]:
    """List all services that have eligibility requirements."""
    return ["proposal_generator", "mockup_generator", "availability_calendar"]


@router.get("/requirements/{service}")
def get_service_requirements(
    service: str,
    user: TrustedUserContext = Depends(require_auth),
) -> dict:
    """
    Get eligibility requirements for a specific service.

    Returns required fields for both locations and networks.
    """
    requirements = _service.get_requirements(service)
    if not requirements:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    return requirements


@router.get("/check/{company}/{location_id}")
def check_location_eligibility(
    company: str,
    location_id: int,
    service: str | None = Query(default=None, description="Check for specific service"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> EligibilityCheck:
    """
    Check eligibility for a specific location. Requires: assets:locations:read

    Returns eligibility status for all services (or specific service if provided).
    Includes missing fields and warnings.
    """
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.check_location_eligibility(
        company=company,
        location_id=location_id,
        service=service,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.get("/check-network/{company}/{network_id}")
def check_network_eligibility(
    company: str,
    network_id: int,
    service: str | None = Query(default=None, description="Check for specific service"),
    user: TrustedUserContext = Depends(require_permission("assets:networks:read")),
) -> EligibilityCheck:
    """
    Check eligibility for a network. Requires: assets:networks:read

    A network is eligible if it has at least one eligible location for the service.
    """
    # Verify company access
    user_companies = user.get("companies", [])
    if user_companies and company not in user_companies:
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.check_network_eligibility(
        company=company,
        network_id=network_id,
        service=service,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Network not found")
    return result


@router.post("/bulk-check")
def bulk_check_eligibility(
    items: list[dict],
    service: str = Query(..., description="Service to check eligibility for"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> list[EligibilityCheck]:
    """
    Bulk check eligibility for multiple items. Requires: assets:locations:read

    Request body:
    ```json
    [
        {"type": "location", "company": "backlite_dubai", "id": 42},
        {"type": "network", "company": "backlite_abudhabi", "id": 5}
    ]
    ```
    """
    # Convert dicts to BulkEligibilityItem
    bulk_items = [
        BulkEligibilityItem(
            type=item.get("type", ""),
            company=item.get("company", ""),
            id=item.get("id", 0),
        )
        for item in items
    ]
    return _service.bulk_check_eligibility(items=bulk_items, service=service)


@router.get("/eligible-locations")
def get_eligible_locations(
    service: str = Query(..., description="Service to filter by"),
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    user: TrustedUserContext = Depends(require_permission("assets:locations:read")),
) -> list[dict]:
    """
    Get all locations eligible for a specific service. Requires: assets:locations:read

    This is a convenience endpoint for services like proposal generator
    to get only the locations they can use.
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.get_eligible_locations(
        service=service,
        companies=accessible or config.COMPANY_SCHEMAS,
    )


@router.get("/eligible-networks")
def get_eligible_networks(
    service: str = Query(..., description="Service to filter by"),
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    user: TrustedUserContext = Depends(require_permission("assets:networks:read")),
) -> list[dict]:
    """
    Get all networks that have at least one eligible location for a service. Requires: assets:networks:read
    """
    # Filter to user's accessible companies
    user_companies = user.get("companies", [])
    requested = companies or user_companies
    accessible = [c for c in requested if c in user_companies] if user_companies else requested

    return _service.get_eligible_networks(
        service=service,
        companies=accessible or config.COMPANY_SCHEMAS,
    )
