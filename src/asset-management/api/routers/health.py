"""
Health check and metadata endpoints.
"""

from fastapi import APIRouter, Query

import config
from db.database import db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "asset-management",
        "environment": config.ENVIRONMENT,
    }


@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "asset-management",
        "version": "0.1.0",
        "docs": "/docs",
    }


@router.get("/api/companies")
async def list_companies(
    active_only: bool = Query(default=True, description="Only return active companies"),
    leaf_only: bool = Query(default=True, description="Only return leaf companies (not groups)"),
):
    """
    List all companies in the system.

    This is a public endpoint for metadata - no auth required.
    Used by admin panels and dev tools to get the list of available companies.

    Returns list of company codes (leaf companies only by default).
    """
    companies = db.get_companies(active_only=active_only, leaf_only=leaf_only)

    # Return just the codes for simple use cases
    return {
        "companies": [c["code"] for c in companies],
        "details": companies,
    }


@router.post("/api/companies/expand")
async def expand_companies(
    company_codes: list[str] = Query(..., description="Company codes to expand (may include groups)"),
):
    """
    Expand company codes to all accessible leaf companies.

    Uses the company hierarchy to resolve access:
    - If user has 'mmg' (root group): Returns ALL leaf companies
    - If user has 'backlite' (group): Returns all backlite verticals
    - If user has 'backlite_dubai' (leaf): Returns only 'backlite_dubai'

    Example:
        POST /api/companies/expand?company_codes=backlite
        Returns: ["backlite_dubai", "backlite_uk", "backlite_abudhabi"]
    """
    expanded = db.expand_companies(company_codes)
    return {
        "input": company_codes,
        "expanded": expanded,
        "count": len(expanded),
    }


@router.get("/api/companies/hierarchy")
async def get_company_hierarchy():
    """
    Get the full company hierarchy tree.

    Returns all companies with their parent relationships and children.
    Used by admin panels and permission management UIs.

    Hierarchy structure:
    - mmg (root group)
      - backlite (group)
        - backlite_dubai (leaf)
        - backlite_uk (leaf)
        - backlite_abudhabi (leaf)
      - viola (leaf)
    """
    hierarchy = db.get_company_hierarchy()
    return {
        "hierarchy": hierarchy,
        "count": len(hierarchy),
    }
