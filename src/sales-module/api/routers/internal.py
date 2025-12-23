"""
Internal API Endpoints.

Protected endpoints for inter-service communication.
Used by Asset-Management to check eligibility of locations/networks.

All endpoints require inter-service JWT authentication via verify_service_token.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from core.services.eligibility_service import (
    EligibilityService,
    LocationEligibilityResult,
    MockupVariant,
    NetworkEligibilityResult,
)
from core.utils.logging import get_logger
from crm_security import require_service, verify_service_token

router = APIRouter(prefix="/internal", tags=["Internal"])
logger = get_logger("api.internal")


def get_eligibility_service(company_schemas: list[str]) -> EligibilityService:
    """Create eligibility service with specified companies."""
    return EligibilityService(company_schemas=company_schemas)


@router.get(
    "/eligibility/location/{location_key}",
    response_model=LocationEligibilityResult,
    summary="Check location eligibility",
    description="Check if a location is eligible for proposals and mockups. "
    "Returns eligibility status, missing fields, and available mockup variants.",
)
async def check_location_eligibility(
    location_key: str,
    company_schemas: list[str] = Query(
        ...,
        description="Company schemas to search for the location",
        example=["backlite_dubai", "backlite_uk"],
    ),
    calling_service: str = Depends(verify_service_token),
) -> LocationEligibilityResult:
    """
    Check eligibility for a specific location.

    This endpoint is called by Asset-Management to determine if a location
    is eligible for proposal generation and mockup generation.

    Returns:
        LocationEligibilityResult with:
        - proposal_eligible: True if location can be used in proposals
        - proposal_missing_fields: List of fields that need to be filled
        - template_exists: True if template exists in storage
        - mockup_eligible: True if mockup frames exist
        - mockup_variants: List of available time_of_day/finish combinations
    """
    logger.info(
        f"[INTERNAL] Location eligibility check from {calling_service}: {location_key}"
    )

    service = get_eligibility_service(company_schemas)
    result = await service.check_location_eligibility(location_key, company_schemas)

    logger.info(
        f"[INTERNAL] Location {location_key}: "
        f"proposal={result.proposal_eligible}, mockup={result.mockup_eligible}"
    )

    return result


@router.get(
    "/eligibility/network/{network_key}",
    response_model=NetworkEligibilityResult,
    summary="Check network eligibility",
    description="Check if a network is eligible for proposals and mockups.",
)
async def check_network_eligibility(
    network_key: str,
    company_schemas: list[str] = Query(
        ...,
        description="Company schemas to search for the network",
        example=["backlite_dubai", "backlite_uk"],
    ),
    calling_service: str = Depends(verify_service_token),
) -> NetworkEligibilityResult:
    """
    Check eligibility for a specific network.

    Networks have lighter eligibility requirements than locations.
    For proposals, they just need a name and template.
    For mockups, they need at least one mockup frame.
    """
    logger.info(
        f"[INTERNAL] Network eligibility check from {calling_service}: {network_key}"
    )

    service = get_eligibility_service(company_schemas)
    result = await service.check_network_eligibility(network_key, company_schemas)

    logger.info(
        f"[INTERNAL] Network {network_key}: "
        f"proposal={result.proposal_eligible}, mockup={result.mockup_eligible}"
    )

    return result


@router.get(
    "/eligibility/template/{location_key}",
    response_model=dict,
    summary="Check template existence",
    description="Check if a template exists in storage for a location.",
)
async def check_template_exists(
    location_key: str,
    company_schemas: list[str] = Query(
        ...,
        description="Company schemas to search",
        example=["backlite_dubai"],
    ),
    calling_service: str = Depends(verify_service_token),
) -> dict:
    """
    Check if a template exists for a location.

    Simple endpoint to verify template availability without full eligibility check.
    """
    service = get_eligibility_service(company_schemas)
    exists = await service.check_template_exists(location_key)
    return {
        "location_key": location_key,
        "template_exists": exists,
    }


@router.get(
    "/eligibility/mockup-variants/{location_key}",
    response_model=list[MockupVariant],
    summary="Get mockup variants",
    description="Get available mockup variants (time_of_day/finish combos) for a location.",
)
async def get_mockup_variants(
    location_key: str,
    company_schemas: list[str] = Query(
        ...,
        description="Company schemas to search",
        example=["backlite_dubai"],
    ),
    calling_service: str = Depends(verify_service_token),
) -> list[MockupVariant]:
    """
    Get available mockup variants for a location.

    Returns a list of time_of_day/finish combinations that have mockup frames
    available for the specified location.
    """
    service = get_eligibility_service(company_schemas)
    variants = await service.get_mockup_variants(location_key)
    return variants


@router.get(
    "/eligibility/bulk",
    response_model=list[LocationEligibilityResult],
    summary="Bulk check location eligibility",
    description="Check eligibility for multiple locations in a single request.",
)
async def bulk_check_eligibility(
    location_keys: list[str] = Query(
        ...,
        description="List of location keys to check",
        example=["dubai_mall", "mall_of_emirates"],
    ),
    company_schemas: list[str] = Query(
        ...,
        description="Company schemas to search",
        example=["backlite_dubai", "backlite_uk"],
    ),
    calling_service: str = Depends(verify_service_token),
) -> list[LocationEligibilityResult]:
    """
    Bulk check eligibility for multiple locations.

    More efficient than making individual requests for each location.
    """
    logger.info(
        f"[INTERNAL] Bulk eligibility check from {calling_service}: {len(location_keys)} locations"
    )

    service = get_eligibility_service(company_schemas)
    results = []
    for location_key in location_keys:
        result = await service.check_location_eligibility(location_key, company_schemas)
        results.append(result)

    eligible_count = sum(1 for r in results if r.proposal_eligible)
    logger.info(
        f"[INTERNAL] Bulk check complete: {eligible_count}/{len(results)} eligible for proposals"
    )

    return results
