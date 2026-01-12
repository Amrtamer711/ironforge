"""
Companies endpoints for RBAC router.

Provides production endpoints for company management.
Proxies to asset-management service for company data.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.config import get_settings
from backend.middleware.auth import AuthUser, require_permission

logger = logging.getLogger("unified-ui")

router = APIRouter(tags=["rbac-companies"])


# =============================================================================
# GET /companies - List all companies
# =============================================================================

@router.get("/companies")
async def list_companies(
    active_only: bool = Query(default=True, description="Only return active companies"),
    leaf_only: bool = Query(default=True, description="Only return leaf companies (not groups)"),
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    List all companies in the system.

    Proxies to asset-management service.
    Returns list of company codes and their details.
    """
    logger.info("[UI RBAC API] Listing companies")

    settings = get_settings()
    if not settings.ASSET_MANAGEMENT_URL:
        logger.error("[UI RBAC API] Asset Management URL not configured")
        raise HTTPException(
            status_code=503,
            detail="Asset management service not configured"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.ASSET_MANAGEMENT_URL}/api/companies",
                params={"active_only": active_only, "leaf_only": leaf_only}
            )
            response.raise_for_status()
            data = response.json()

            return {
                "companies": data.get("companies", []),
                "details": data.get("details", [])
            }

    except httpx.TimeoutException:
        logger.error("[UI RBAC API] Timeout fetching companies from Asset Management")
        raise HTTPException(status_code=504, detail="Asset management service timeout")
    except httpx.ConnectError as e:
        logger.error(f"[UI RBAC API] Connection error fetching companies: {e}")
        raise HTTPException(status_code=503, detail="Asset management service unavailable")
    except Exception as e:
        logger.error(f"[UI RBAC API] Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch companies")


# =============================================================================
# GET /companies/hierarchy - Get company hierarchy tree
# =============================================================================

@router.get("/companies/hierarchy")
async def get_company_hierarchy(
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Get the full company hierarchy tree.

    Returns all companies with their parent relationships and children.
    Used by admin panels and permission management UIs.

    Hierarchy structure:
    - mmg (root group)
      - backlite (group)
        - backlite_dubai (leaf)
        - backlite_uk (leaf)
      - viola (leaf)
    """
    logger.info("[UI RBAC API] Getting company hierarchy")

    settings = get_settings()
    if not settings.ASSET_MANAGEMENT_URL:
        logger.error("[UI RBAC API] Asset Management URL not configured")
        raise HTTPException(
            status_code=503,
            detail="Asset management service not configured"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.ASSET_MANAGEMENT_URL}/api/companies/hierarchy"
            )
            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException:
        logger.error("[UI RBAC API] Timeout fetching company hierarchy")
        raise HTTPException(status_code=504, detail="Asset management service timeout")
    except httpx.ConnectError as e:
        logger.error(f"[UI RBAC API] Connection error fetching hierarchy: {e}")
        raise HTTPException(status_code=503, detail="Asset management service unavailable")
    except Exception as e:
        logger.error(f"[UI RBAC API] Error fetching company hierarchy: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch company hierarchy")


# =============================================================================
# POST /companies/expand - Expand company codes to leaf companies
# =============================================================================

@router.post("/companies/expand")
async def expand_companies(
    company_codes: list[str] = Query(..., description="Company codes to expand (may include groups)"),
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Expand company codes to all accessible leaf companies.

    Uses the company hierarchy to resolve access:
    - If user has 'mmg' (root group): Returns ALL leaf companies
    - If user has 'backlite' (group): Returns all backlite verticals
    - If user has 'backlite_dubai' (leaf): Returns only 'backlite_dubai'

    Example:
        POST /api/rbac/companies/expand?company_codes=backlite
        Returns: ["backlite_dubai", "backlite_uk", "backlite_abudhabi"]
    """
    logger.info(f"[UI RBAC API] Expanding companies: {company_codes}")

    settings = get_settings()
    if not settings.ASSET_MANAGEMENT_URL:
        logger.error("[UI RBAC API] Asset Management URL not configured")
        raise HTTPException(
            status_code=503,
            detail="Asset management service not configured"
        )

    try:
        # Build query string with all company codes
        params = "&".join(f"company_codes={c}" for c in company_codes)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.ASSET_MANAGEMENT_URL}/api/companies/expand?{params}"
            )
            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException:
        logger.error("[UI RBAC API] Timeout expanding companies")
        raise HTTPException(status_code=504, detail="Asset management service timeout")
    except httpx.ConnectError as e:
        logger.error(f"[UI RBAC API] Connection error expanding companies: {e}")
        raise HTTPException(status_code=503, detail="Asset management service unavailable")
    except Exception as e:
        logger.error(f"[UI RBAC API] Error expanding companies: {e}")
        raise HTTPException(status_code=500, detail="Failed to expand companies")
