"""
Health Check Router for Video Critique.

Provides health and readiness endpoints for monitoring.
"""

from datetime import datetime

from fastapi import APIRouter, Response

import config
from db.database import get_database
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
@router.get("/")
async def health_check():
    """
    Basic health check endpoint.

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "video-critique",
        "timestamp": datetime.now(config.UAE_TZ).isoformat(),
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.

    Returns:
        Readiness status with component checks
    """
    checks = {}
    all_healthy = True

    # Check database
    try:
        db = get_database()
        # Simple query to verify connection
        await db.list_tasks({"limit": 1})
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        all_healthy = False

    # Check Slack (optional)
    try:
        from integrations.channels import get_channel
        channel = get_channel("slack")
        # Just verify we can create the client
        checks["slack"] = "ok"
    except Exception as e:
        checks["slack"] = f"warning: {str(e)}"
        # Slack not being available is a warning, not an error

    # Check LLM provider
    try:
        from integrations.llm import LLMClient
        client = LLMClient.from_config()
        checks["llm"] = "ok"
    except Exception as e:
        checks["llm"] = f"error: {str(e)}"
        all_healthy = False

    status_code = 200 if all_healthy else 503

    return Response(
        content={
            "status": "ready" if all_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now(config.UAE_TZ).isoformat(),
        }.__str__(),
        status_code=status_code,
        media_type="application/json",
    )


@router.get("/live")
async def liveness_check():
    """
    Liveness check - verifies the service is running.

    Returns:
        Simple alive status
    """
    return {"status": "alive"}
