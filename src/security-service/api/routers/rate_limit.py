"""
Rate Limiting API endpoints.

Handles rate limit checking and status queries.
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import require_service_auth
from core import rate_limit_service
from models import (
    RateLimitCheckRequest,
    RateLimitCheckResponse,
    RateLimitIncrementRequest,
    RateLimitIncrementResponse,
    RateLimitStatusResponse,
)

router = APIRouter(prefix="/api/rate-limit", tags=["rate-limit"])


@router.post("/check", response_model=RateLimitCheckResponse)
async def check_rate_limit(
    request: RateLimitCheckRequest,
    service: str = Depends(require_service_auth),
):
    """
    Check and increment rate limit for a key.

    This is the main endpoint for rate limiting. It:
    1. Checks if the request is allowed
    2. Increments the counter if allowed
    3. Returns remaining quota and reset time

    Returns:
        RateLimitCheckResponse with:
        - allowed: Whether the request is allowed
        - remaining: Requests remaining in window
        - limit: The rate limit
        - reset_at: Unix timestamp when limit resets
        - retry_after: Seconds until reset (if denied)
    """
    result = rate_limit_service.check_rate_limit(
        key=request.key,
        limit=request.limit,
        window_seconds=request.window_seconds,
    )

    return RateLimitCheckResponse(
        allowed=result.get("allowed", True),
        remaining=result.get("remaining", 0),
        limit=result.get("limit", request.limit),
        reset_at=result.get("reset_at", 0),
        retry_after=result.get("retry_after"),
    )


@router.post("/check-only", response_model=RateLimitCheckResponse)
async def check_rate_limit_only(
    request: RateLimitCheckRequest,
    service: str = Depends(require_service_auth),
):
    """
    Check rate limit status without incrementing.

    Useful for displaying rate limit info to users without
    consuming quota.

    Returns:
        Same as /check but does not increment counter
    """
    result = rate_limit_service.check_only(
        key=request.key,
        limit=request.limit,
        window_seconds=request.window_seconds,
    )

    return RateLimitCheckResponse(
        allowed=result.get("allowed", True),
        remaining=result.get("remaining", 0),
        limit=result.get("limit", request.limit),
        reset_at=result.get("reset_at", 0),
        current=result.get("current", 0),
    )


@router.get("/status/{key}", response_model=RateLimitStatusResponse)
async def get_rate_limit_status(
    key: str,
    service: str = Depends(require_service_auth),
):
    """
    Get current rate limit status for a key.

    Returns:
        RateLimitStatusResponse with current state
    """
    state = rate_limit_service.get_status(key)

    return RateLimitStatusResponse(
        key=state.key,
        request_count=state.request_count,
        window_start=state.window_start,
        window_seconds=state.window_seconds,
    )


# =============================================================================
# CONVENIENCE ENDPOINTS
# =============================================================================


@router.post("/check/user")
async def check_user_rate_limit(
    user_id: str,
    endpoint: str | None = Query(None, description="Specific endpoint to limit"),
    limit: int = Query(100, description="Requests per minute"),
    service: str = Depends(require_service_auth),
):
    """
    Check rate limit for a user.

    Convenience endpoint that builds the rate limit key automatically.
    """
    result = rate_limit_service.check_user_rate_limit(
        user_id=user_id,
        endpoint=endpoint,
        limit=limit,
    )

    return {
        "key": rate_limit_service.build_user_key(user_id, endpoint),
        **result,
    }


@router.post("/check/ip")
async def check_ip_rate_limit(
    ip_address: str,
    endpoint: str | None = Query(None, description="Specific endpoint to limit"),
    limit: int = Query(100, description="Requests per minute"),
    service: str = Depends(require_service_auth),
):
    """
    Check rate limit for an IP address.

    Convenience endpoint that builds the rate limit key automatically.
    """
    result = rate_limit_service.check_ip_rate_limit(
        ip_address=ip_address,
        endpoint=endpoint,
        limit=limit,
    )

    return {
        "key": rate_limit_service.build_ip_key(ip_address, endpoint),
        **result,
    }


@router.post("/check/api-key")
async def check_api_key_rate_limit(
    key_id: str,
    limit_per_minute: int = Query(100, description="Requests per minute"),
    endpoint: str | None = Query(None, description="Specific endpoint to limit"),
    service: str = Depends(require_service_auth),
):
    """
    Check rate limit for an API key.

    Convenience endpoint that builds the rate limit key automatically.
    """
    result = rate_limit_service.check_api_key_rate_limit(
        key_id=key_id,
        limit_per_minute=limit_per_minute,
        endpoint=endpoint,
    )

    return {
        "key": rate_limit_service.build_api_key_key(key_id, endpoint),
        **result,
    }


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================


@router.post("/cleanup")
async def cleanup_expired_limits(
    service: str = Depends(require_service_auth),
):
    """
    Clean up expired rate limit windows.

    Should be called periodically (e.g., every 5 minutes) by a scheduler.

    Returns:
        Number of expired windows removed
    """
    count = rate_limit_service.cleanup_expired()

    return {
        "cleaned_up": count,
    }
