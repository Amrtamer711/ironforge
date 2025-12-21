"""
Health check endpoints.
"""

from fastapi import APIRouter

import config

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
