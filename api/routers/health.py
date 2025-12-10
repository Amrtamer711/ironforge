"""
Health check and metrics endpoints.

Provides:
- /health: Basic health check for load balancers (fast, simple)
- /health/ready: Readiness check with dependency status
- /metrics: Detailed performance and resource metrics
"""

import os
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, Depends

from api.auth import require_auth
from integrations.auth import AuthUser
from utils.time import get_uae_time
from utils.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger("api.health")


async def check_database() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        from db.database import db

        # Try a simple operation to verify connectivity
        # Using get_proposals_summary as a lightweight check
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, db.get_proposals_summary)

        return {
            "status": "healthy",
            "backend": db.backend_name,
            "connected": True,
        }
    except Exception as e:
        logger.warning(f"[HEALTH] Database check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "connected": False,
        }


async def check_slack() -> Dict[str, Any]:
    """Check Slack API connectivity."""
    try:
        import config
        if not config.SLACK_BOT_TOKEN:
            return {
                "status": "not_configured",
                "message": "Slack token not set",
            }

        # Just verify token is present (actual API call would be expensive)
        return {
            "status": "configured",
            "has_token": True,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


async def check_llm_providers() -> Dict[str, Any]:
    """Check LLM provider configuration."""
    try:
        import config
        providers = {}

        # OpenAI
        if config.OPENAI_API_KEY:
            providers["openai"] = {"status": "configured"}
        else:
            providers["openai"] = {"status": "not_configured"}

        # Google
        if config.GOOGLE_API_KEY:
            providers["google"] = {"status": "configured"}
        else:
            providers["google"] = {"status": "not_configured"}

        return {
            "status": "healthy" if any(p.get("status") == "configured" for p in providers.values()) else "degraded",
            "providers": providers,
            "active_llm": config.LLM_PROVIDER,
            "active_image": config.IMAGE_PROVIDER,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@router.get("/health")
async def health():
    """
    Basic health check endpoint.

    Returns a simple response for load balancer health checks.
    This endpoint should be fast and not make external calls.
    """
    environment = os.getenv("ENVIRONMENT", "development")
    return {
        "status": "healthy",
        "timestamp": get_uae_time().isoformat(),
        "environment": environment,
        "timezone": "UAE (GMT+4)"
    }


@router.get("/health/ready")
async def health_ready():
    """
    Readiness check with dependency status.

    Checks connectivity to:
    - Database (SQLite/Supabase)
    - Slack API (if configured)
    - LLM providers (OpenAI/Google)

    Returns overall status and per-dependency details.
    Use this for deployment readiness checks.
    """
    environment = os.getenv("ENVIRONMENT", "development")

    # Run checks concurrently
    db_check, slack_check, llm_check = await asyncio.gather(
        check_database(),
        check_slack(),
        check_llm_providers(),
        return_exceptions=True,
    )

    # Handle any exceptions from gather
    if isinstance(db_check, Exception):
        db_check = {"status": "error", "error": str(db_check)}
    if isinstance(slack_check, Exception):
        slack_check = {"status": "error", "error": str(slack_check)}
    if isinstance(llm_check, Exception):
        llm_check = {"status": "error", "error": str(llm_check)}

    # Determine overall status
    critical_healthy = db_check.get("status") in ("healthy", "configured")
    services_healthy = all(
        check.get("status") in ("healthy", "configured", "not_configured")
        for check in [slack_check, llm_check]
    )

    if critical_healthy and services_healthy:
        overall_status = "ready"
    elif critical_healthy:
        overall_status = "degraded"
    else:
        overall_status = "not_ready"

    return {
        "status": overall_status,
        "timestamp": get_uae_time().isoformat(),
        "environment": environment,
        "checks": {
            "database": db_check,
            "slack": slack_check,
            "llm": llm_check,
        }
    }


@router.get("/health/auth")
async def health_auth():
    """
    Debug endpoint to check auth configuration.

    Shows which auth provider is configured and JWKS URL setup.
    Does NOT require authentication (for debugging auth issues).
    """
    import os
    from integrations.auth import get_auth_client

    auth_provider = os.getenv("AUTH_PROVIDER", "local_dev")
    environment = os.getenv("ENVIRONMENT", "development")

    # Check Supabase URL env vars for JWKS
    supabase_urls = {
        "UI_DEV_SUPABASE_URL": os.getenv("UI_DEV_SUPABASE_URL", ""),
        "UI_PROD_SUPABASE_URL": os.getenv("UI_PROD_SUPABASE_URL", ""),
        "UI_SUPABASE_URL": os.getenv("UI_SUPABASE_URL", ""),
    }

    # Get the actual auth client to see what's configured
    try:
        client = get_auth_client()
        provider_name = client.provider_name

        # Check JWKS URL configuration (new ES256 method)
        jwks_url = getattr(client._provider, '_jwks_url', None)
        ui_supabase_url = getattr(client._provider, '_ui_supabase_url', None)
    except Exception as e:
        provider_name = f"error: {e}"
        jwks_url = None
        ui_supabase_url = None

    return {
        "auth_provider_env": auth_provider,
        "environment": environment,
        "active_provider": provider_name,
        "supabase_urls_available": {k: bool(v) for k, v in supabase_urls.items()},
        "active_ui_supabase_url": ui_supabase_url or "(not set)",
        "active_jwks_url": jwks_url or "(not set)",
        "jwks_configured": bool(jwks_url),
        "timestamp": get_uae_time().isoformat(),
    }


@router.post("/health/auth/test")
async def health_auth_test():
    """
    Test endpoint that requires authentication.

    If this returns 401, auth is not working.
    If this returns 200, auth is working.
    """
    from fastapi import Request, HTTPException
    from api.auth import get_token_from_request, get_current_user

    # This endpoint intentionally doesn't use Depends(require_auth)
    # so we can return detailed error messages
    return {
        "message": "To test auth, call POST /api/chat/message or GET /health/auth/test-protected",
        "timestamp": get_uae_time().isoformat(),
    }


@router.get("/health/auth/test-protected")
async def health_auth_test_protected(user: AuthUser = Depends(require_auth)):
    """
    Protected test endpoint - requires valid auth.

    If you can call this, auth is working correctly.
    """
    return {
        "status": "authenticated",
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "timestamp": get_uae_time().isoformat(),
    }


@router.get("/metrics")
async def metrics(user: AuthUser = Depends(require_auth)):
    """
    Performance metrics endpoint for monitoring.

    Requires authentication to protect sensitive system information.
    """
    import psutil

    import config
    from generators.pdf import _CONVERT_SEMAPHORE
    from db.cache import user_history, pending_location_additions

    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()

    # Get CPU count
    cpu_count = psutil.cpu_count()

    # Get current PDF conversion semaphore status
    pdf_conversions_active = _CONVERT_SEMAPHORE._initial_value - _CONVERT_SEMAPHORE._value

    return {
        "memory": {
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
        },
        "cpu": {
            "percent": process.cpu_percent(interval=0.1),
            "count": cpu_count,
        },
        "pdf_conversions": {
            "active": pdf_conversions_active,
            "max_concurrent": _CONVERT_SEMAPHORE._initial_value,
        },
        "cache_sizes": {
            "user_histories": len(user_history),
            "pending_locations": len(pending_location_additions),
            "templates_cached": len(config.get_location_mapping()),
        },
        "timestamp": get_uae_time().isoformat()
    }
