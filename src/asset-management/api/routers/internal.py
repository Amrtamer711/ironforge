"""
Internal API endpoints for service-to-service communication.

These endpoints require service JWT authentication (INTER_SERVICE_SECRET)
but do NOT require user permissions. Used for:
- Sales-Module fetching locations at startup
- Background jobs
- Cron tasks
- Service health checks
"""

import logging
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status

import config
from core.locations import Location, LocationService
from core.networks import Network, NetworkService
from core.packages import Package, PackageService
from db.database import db

router = APIRouter(prefix="/api/internal", tags=["Internal"])
logger = logging.getLogger("asset-management")

# Service singletons
_location_service = LocationService()
_network_service = NetworkService()
_package_service = PackageService()


# =============================================================================
# SERVICE AUTHENTICATION
# =============================================================================

async def verify_service_token(
    authorization: str = Header(..., description="Bearer token with service JWT")
) -> dict:
    """
    Verify service-to-service JWT token.

    Tokens must be signed with INTER_SERVICE_SECRET and contain:
    - service: calling service name (e.g., "sales-module")
    - type: "service"
    - exp: expiration time
    """
    if not config.INTER_SERVICE_SECRET:
        logger.warning("[INTERNAL] INTER_SERVICE_SECRET not configured, rejecting request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication not configured",
        )

    # Extract token from "Bearer <token>"
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization[7:]  # Remove "Bearer "

    try:
        payload = jwt.decode(
            token,
            config.INTER_SERVICE_SECRET,
            algorithms=["HS256"],
        )

        # Verify it's a service token (matches ServiceAuthClient format)
        if payload.get("type") != "service":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not a service token",
            )

        # Get service name from 'service' key (ServiceAuthClient format)
        service_name = payload.get("service", "unknown")
        if not service_name or service_name == "unknown":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing service name in token",
            )

        logger.debug(f"[INTERNAL] Authenticated service: {service_name}")
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service token expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[INTERNAL] Invalid service token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


# =============================================================================
# INTERNAL ENDPOINTS
# =============================================================================

@router.get("/locations")
def list_locations_internal(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    network_id: int | None = Query(default=None, description="Filter by network"),
    type_id: int | None = Query(default=None, description="Filter by asset type"),
    active_only: bool = Query(default=True, description="Only return active locations"),
    include_eligibility: bool = Query(default=False, description="Include eligibility info"),
    service: dict = Depends(verify_service_token),
) -> list[Location]:
    """
    List all locations for service-to-service calls.

    Unlike /api/locations, this endpoint:
    - Requires service JWT auth (not user auth)
    - Does NOT require user permissions
    - Returns all locations across all companies if no filter specified

    Used by Sales-Module at startup to build location cache.
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching locations (companies={companies}, active_only={active_only})")

    # If no companies specified, return all
    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        locations = _location_service.list_locations(
            companies=filter_companies,
            network_id=network_id,
            type_id=type_id,
            active_only=active_only,
            include_eligibility=include_eligibility,
        )
        logger.info(f"[INTERNAL] Returning {len(locations)} locations to {caller}")
        return locations
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to list locations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve locations",
        )


@router.get("/networks")
def list_networks_internal(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    service: dict = Depends(verify_service_token),
) -> list[Network]:
    """
    List all networks for service-to-service calls.

    Used by other services for network lookups.
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching networks (companies={companies})")

    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        networks = _network_service.list_networks(companies=filter_companies)
        logger.info(f"[INTERNAL] Returning {len(networks)} networks to {caller}")
        return networks
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to list networks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve networks",
        )


@router.get("/packages")
def list_packages_internal(
    companies: list[str] = Query(default=None, description="Filter by company schemas"),
    active_only: bool = Query(default=True, description="Only return active packages"),
    include_items: bool = Query(default=False, description="Include package items (networks)"),
    service: dict = Depends(verify_service_token),
) -> list[Package]:
    """
    List all packages for service-to-service calls.

    Used by Sales-Module for package eligibility checks.
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching packages (companies={companies}, active_only={active_only}, include_items={include_items})")

    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        packages = _package_service.list_packages(
            companies=filter_companies,
            active_only=active_only,
            include_items=include_items,
        )
        logger.info(f"[INTERNAL] Returning {len(packages)} packages to {caller}")
        return packages
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to list packages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve packages",
        )


@router.get("/packages/{company}/{package_id}")
def get_package_internal(
    company: str,
    package_id: int,
    include_items: bool = Query(default=True, description="Include package items"),
    service: dict = Depends(verify_service_token),
) -> Package | None:
    """
    Get a specific package by ID for service-to-service calls.

    Used by Sales-Module for package eligibility and template fetching.
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching package {package_id} from {company}")

    try:
        package = _package_service.get_package(
            company=company,
            package_id=package_id,
            expand_locations=include_items,
        )
        if not package:
            raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")
        return package
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to get package: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve package",
        )


@router.get("/locations/by-key/{location_key}")
def get_location_by_key_internal(
    location_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    include_eligibility: bool = Query(default=True, description="Include eligibility details"),
    service: dict = Depends(verify_service_token),
) -> Location:
    """
    Get a location by its key for service-to-service calls.

    Unlike /api/locations/by-key/{key}, this endpoint:
    - Requires service JWT auth (not user auth)
    - Does NOT require user permissions

    Used by Sales-Module for location validation during mockup operations.
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching location by key: {location_key}")

    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        location = _location_service.get_location_by_key(
            location_key=location_key,
            companies=filter_companies,
            include_eligibility=include_eligibility,
        )
        if not location:
            raise HTTPException(status_code=404, detail=f"Location not found: {location_key}")
        return location
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to get location by key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve location",
        )


@router.get("/mockup-storage-info/{network_key}")
def get_mockup_storage_info_internal(
    network_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    service: dict = Depends(verify_service_token),
) -> dict:
    """
    Get mockup storage info for a network.

    Returns the storage keys needed to fetch/store mockups:
    - For standalone networks: returns network_key (mockups at network level)
    - For traditional networks: returns asset type paths (mockups at type level)

    This abstracts the unified architecture - callers just use the returned
    storage_keys without knowing if it's standalone or traditional.

    Args:
        network_key: Network identifier
        companies: Company schemas to search

    Response:
    {
        "network_key": str,
        "company": str,
        "is_standalone": bool,
        "storage_keys": list[str],
            - Standalone: [network_key]
            - Traditional: ["{network_key}/{type_key}", ...]
        "asset_types": list[dict]  # For traditional: type details with storage_key
    }
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching mockup storage info for: {network_key}")

    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        result = db.get_mockup_storage_info(network_key, filter_companies)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Network not found: {network_key}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to get mockup storage info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve mockup storage info",
        )


@router.get("/asset-types/{network_key}")
def get_network_asset_types_internal(
    network_key: str,
    companies: list[str] = Query(default=None, description="Company schemas to search"),
    service: dict = Depends(verify_service_token),
) -> dict:
    """
    Get asset types for a traditional network.

    Used by the mockup setup UI to show the asset type picker.
    For standalone networks, returns empty list (no asset types).

    Args:
        network_key: Network identifier
        companies: Company schemas to search

    Response:
    {
        "network_key": str,
        "company": str,
        "is_standalone": bool,
        "asset_types": list[dict]
            - type_key: str
            - type_name: str
            - type_id: int
            - environment: str (default for the type)
    }
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching asset types for network: {network_key}")

    filter_companies = companies or config.COMPANY_SCHEMAS

    try:
        # Use get_mockup_storage_info which already returns asset_types
        result = db.get_mockup_storage_info(network_key, filter_companies)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Network not found: {network_key}"
            )

        return {
            "network_key": result.get("network_key"),
            "company": result.get("company"),
            "is_standalone": result.get("is_standalone", False),
            "asset_types": result.get("asset_types", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to get asset types for network: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve asset types",
        )


@router.get("/companies")
def list_companies_internal(
    codes: list[str] = Query(default=None, description="Filter by company codes"),
    service: dict = Depends(verify_service_token),
) -> list[dict]:
    """
    List companies with their display names.

    Used by Sales-Module to get proper display names for company schemas.

    Returns:
        List of company dicts with code (schema name) and name (display name)
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} fetching companies (codes={codes})")

    try:
        companies = db.get_companies(active_only=True, leaf_only=True)
        # Filter by codes if specified
        if codes:
            companies = [c for c in companies if c.get("code") in codes]
        return companies
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to list companies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve companies",
        )


@router.get("/health")
def internal_health_check(
    service: dict = Depends(verify_service_token),
) -> dict:
    """
    Internal health check endpoint.

    Used by other services to verify Asset-Management is available.
    """
    caller = service.get("service", "unknown")
    return {
        "status": "healthy",
        "service": "asset-management",
        "caller": caller,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/cache/invalidate")
def invalidate_cache_internal(
    pattern: str = Query(default="all", description="Cache pattern to invalidate: 'all', 'packages', 'networks', 'locations'"),
    service: dict = Depends(verify_service_token),
) -> dict:
    """
    Invalidate asset caches.

    Used to clear stale cache entries after database updates.

    Patterns:
    - 'all': Clear all asset-related caches
    - 'packages': Clear package and package_items caches
    - 'networks': Clear network caches
    - 'locations': Clear location caches
    """
    caller = service.get("service", "unknown")
    logger.info(f"[INTERNAL] {caller} invalidating cache (pattern={pattern})")

    try:
        if pattern == "all":
            db.invalidate_asset_caches()
            # Also clear package_items which isn't in the standard method
            from db.backends.supabase import _run_async
            _run_async(db._cache_delete_pattern("package_items:*"))
            return {"status": "ok", "message": "All asset caches invalidated"}
        elif pattern == "packages":
            from db.backends.supabase import _run_async
            _run_async(db._cache_delete_pattern("packages:*"))
            _run_async(db._cache_delete_pattern("package:*"))
            _run_async(db._cache_delete_pattern("package_items:*"))
            return {"status": "ok", "message": "Package caches invalidated"}
        elif pattern == "networks":
            from db.backends.supabase import _run_async
            _run_async(db._cache_delete_pattern("networks:*"))
            _run_async(db._cache_delete_pattern("network:*"))
            _run_async(db._cache_delete_pattern("network_key:*"))
            return {"status": "ok", "message": "Network caches invalidated"}
        elif pattern == "locations":
            from db.backends.supabase import _run_async
            _run_async(db._cache_delete_pattern("locations:*"))
            _run_async(db._cache_delete_pattern("location:*"))
            _run_async(db._cache_delete_pattern("location_id:*"))
            return {"status": "ok", "message": "Location caches invalidated"}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pattern: {pattern}. Use 'all', 'packages', 'networks', or 'locations'"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Failed to invalidate cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate cache: {str(e)}",
        )
