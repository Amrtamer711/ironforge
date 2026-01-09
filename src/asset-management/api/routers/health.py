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
