"""
Health check endpoints.
"""

from fastapi import APIRouter

from config import settings
from db import db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns service status and basic info.
    """
    return {
        "status": "healthy",
        "service": "security-service",
        "environment": settings.ENVIRONMENT,
        "database": db.backend_name,
    }


@router.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "security-service",
        "version": "1.0.0",
        "description": "Centralized authentication, authorization, and audit logging",
        "docs": "/docs",
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check for container orchestration.

    Verifies database connections are working.
    """
    checks = {
        "security_db": False,
        "ui_db": False,
    }

    # Check Security Supabase
    try:
        from db.clients import get_security_client
        client = get_security_client()
        checks["security_db"] = client is not None
    except Exception:
        pass

    # Check UI Supabase
    try:
        from db.clients import get_ui_client
        client = get_ui_client()
        checks["ui_db"] = client is not None
    except Exception:
        pass

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
    }
