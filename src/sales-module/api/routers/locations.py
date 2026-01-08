"""
Locations API endpoints.

Provides access to available locations filtered by user's company access
and optionally by service eligibility.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from crm_security import AuthUser, require_auth_user as require_auth
from core.services.asset_service import get_asset_service


router = APIRouter(prefix="/api/locations", tags=["locations"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class LocationResponse(BaseModel):
    """Location information response."""
    location_key: str
    display_name: str
    display_type: str  # "digital" | "static"
    company_schema: str

    # Optional fields
    series: str | None = None
    city: str | None = None
    area: str | None = None

    # Pricing (for form auto-population)
    upload_fee: float | None = None

    # Static location specs
    height: str | None = None
    width: str | None = None
    number_of_faces: int | None = None

    # Digital location specs
    spot_duration: int | None = None
    loop_duration: int | None = None
    sov_percent: float | None = None

    # Eligibility (Phase 2)
    eligible_for_proposals: bool = True  # Stub - always True in Phase 1
    eligible_for_mockups: bool = True    # Stub - always True in Phase 1


class LocationListResponse(BaseModel):
    """Response for list of locations."""
    locations: list[LocationResponse]
    total: int
    companies: list[str]  # Companies that were queried


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("", response_model=LocationListResponse)
async def get_available_locations(
    service: str | None = Query(
        default=None,
        description="Filter by service eligibility: 'proposals' or 'mockups' (Phase 2 feature)"
    ),
    display_type: str | None = Query(
        default=None,
        description="Filter by type: 'digital' or 'static'"
    ),
    user: AuthUser = Depends(require_auth),
):
    """
    Get all locations available to the authenticated user.

    Filters by:
    - User's company access (always applied)
    - Service eligibility (optional, Phase 2 feature)
    - Display type (optional)

    **Phase 1**: Returns all locations user has access to (no eligibility filtering yet)
    **Phase 2**: Will filter by actual eligibility from Asset-Management

    Examples:
    - `GET /api/locations` - All locations user can access
    - `GET /api/locations?display_type=digital` - Only digital locations
    - `GET /api/locations?service=proposals` - Only proposal-eligible locations (Phase 2)
    """
    try:
        # Validate company access
        if not user.has_company_access:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to any company data. Please contact your administrator."
            )

        # Get singleton AssetService (shared cache)
        asset_service = get_asset_service()

        # Get all locations for user's companies (async)
        all_locations = await asset_service.get_locations_for_companies(user.companies)

        # Filter by display_type if specified
        if display_type:
            all_locations = asset_service.filter_locations(
                all_locations,
                display_type=display_type
            )

        # Phase 2: Filter by service eligibility
        # For now, include all locations (no filtering)
        # Future: Use asset_service.check_eligibility() for each location

        # Convert to response model
        location_responses = []
        for loc in all_locations:
            location_responses.append(
                LocationResponse(
                    location_key=loc.get("location_key", ""),
                    display_name=loc.get("display_name", loc.get("location_key", "")),
                    display_type=loc.get("display_type", "unknown"),
                    company_schema=loc.get("company_schema") or loc.get("company") or "unknown",
                    series=loc.get("series"),
                    city=loc.get("city"),
                    area=loc.get("area"),
                    # Pricing
                    upload_fee=loc.get("upload_fee"),
                    # Static specs
                    height=loc.get("height"),
                    width=loc.get("width"),
                    number_of_faces=loc.get("number_of_faces"),
                    # Digital specs
                    spot_duration=loc.get("spot_duration"),
                    loop_duration=loc.get("loop_duration"),
                    sov_percent=loc.get("sov_percent"),
                    # Phase 1: Assume all eligible
                    eligible_for_proposals=True,
                    eligible_for_mockups=True,
                )
            )

        return LocationListResponse(
            locations=location_responses,
            total=len(location_responses),
            companies=user.companies,
        )

    except HTTPException:
        raise
    except Exception as e:
        import config
        config.logger.error(f"[LOCATIONS API] Error fetching locations: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch locations"
        )


@router.get("/{location_key}", response_model=LocationResponse)
async def get_location_by_key(
    location_key: str,
    user: AuthUser = Depends(require_auth),
):
    """
    Get a specific location by its key.

    **Access Control**: User must have access to the location's company.
    """
    try:
        # Validate company access
        if not user.has_company_access:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to any company data."
            )

        # Get singleton AssetService (shared cache)
        asset_service = get_asset_service()

        # Validate user has access
        has_access, error = await asset_service.validate_location_access(
            location_key=location_key,
            user_companies=user.companies,
        )

        if not has_access:
            raise HTTPException(
                status_code=404,
                detail=error or f"Location '{location_key}' not found"
            )

        # Get location
        location = await asset_service.get_location_by_key(location_key, user.companies)

        if not location:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_key}' not found"
            )

        return LocationResponse(
            location_key=location.get("location_key", ""),
            display_name=location.get("display_name", location_key),
            display_type=location.get("display_type", "unknown"),
            company_schema=location.get("company_schema") or location.get("company") or "unknown",
            series=location.get("series"),
            city=location.get("city"),
            area=location.get("area"),
            # Pricing
            upload_fee=location.get("upload_fee"),
            # Static specs
            height=location.get("height"),
            width=location.get("width"),
            number_of_faces=location.get("number_of_faces"),
            # Digital specs
            spot_duration=location.get("spot_duration"),
            loop_duration=location.get("loop_duration"),
            sov_percent=location.get("sov_percent"),
            eligible_for_proposals=True,  # Phase 1 stub
            eligible_for_mockups=True,    # Phase 1 stub
        )

    except HTTPException:
        raise
    except Exception as e:
        import config
        config.logger.error(f"[LOCATIONS API] Error fetching location {location_key}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch location '{location_key}'"
        )
