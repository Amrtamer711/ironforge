"""
FastAPI Dependencies for Security Service.

Handles authentication of calling services.
"""

import hmac
import logging
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from config import settings

logger = logging.getLogger("security-service")


# =============================================================================
# SERVICE AUTHENTICATION
# =============================================================================

async def verify_service_secret(request: Request) -> str:
    """
    Verify that the request comes from an authorized service.

    Checks X-Service-Secret header against INTER_SERVICE_SECRET.

    Returns:
        Service name from X-Service-Name header

    Raises:
        HTTPException: If secret is missing or invalid
    """
    # Get headers
    service_secret = request.headers.get("X-Service-Secret")
    service_name = request.headers.get("X-Service-Name", "unknown")

    # Check if service auth is required
    if not settings.INTER_SERVICE_SECRET:
        # No secret configured - allow (development mode)
        logger.debug(f"[AUTH] No INTER_SERVICE_SECRET configured, allowing {service_name}")
        return service_name

    if not service_secret:
        logger.warning(f"[AUTH] Missing X-Service-Secret from {service_name}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing service secret",
        )

    # Constant-time comparison
    if not hmac.compare_digest(service_secret, settings.INTER_SERVICE_SECRET):
        logger.warning(f"[AUTH] Invalid service secret from {service_name}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service secret",
        )

    logger.debug(f"[AUTH] Verified service: {service_name}")
    return service_name


async def require_service_auth(
    service: str = Depends(verify_service_secret),
) -> str:
    """
    Require service authentication.

    Use as dependency on internal endpoints.
    """
    return service


def require_specific_service(allowed_services: list[str]) -> Callable:
    """
    Factory for requiring specific services.

    Usage:
        @router.get("/internal/sensitive")
        async def sensitive_data(
            service: str = Depends(require_specific_service(["unified-ui"]))
        ):
            ...
    """
    async def _require_specific_service(
        service: str = Depends(verify_service_secret),
    ) -> str:
        if service not in allowed_services:
            logger.warning(
                f"[AUTH] Service {service} not allowed to access this endpoint"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {service} not authorized",
            )
        return service

    return _require_specific_service


# =============================================================================
# REQUEST CONTEXT
# =============================================================================

def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request."""
    # Try X-Forwarded-For first (for proxied requests)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Try X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


def get_request_id(request: Request) -> str | None:
    """Get request ID from headers."""
    return request.headers.get("X-Request-ID")
