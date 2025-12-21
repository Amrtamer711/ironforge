"""
Rate Limiting - SDK Client.

Thin client that checks rate limits via the security-service.
All rate limit state storage is handled by the service.

Usage:
    from crm_security import rate_limit

    @app.get("/api/data")
    async def get_data(request: Request, _: None = Depends(rate_limit())):
        return {"data": "..."}

    # Custom limit for specific endpoint
    @app.post("/api/expensive")
    async def expensive_op(request: Request, _: None = Depends(rate_limit(10, 60))):
        return {"result": "..."}
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request, status

from .config import security_config

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """Information about current rate limit status."""
    limit: int           # Max requests allowed
    remaining: int       # Requests remaining in window
    reset_at: float      # Unix timestamp when window resets
    retry_after: int     # Seconds until retry is allowed (if blocked)


def _get_client_key(request: Request) -> str:
    """
    Get unique client identifier for rate limiting.

    Priority:
    1. API Key (if present)
    2. Authenticated user ID
    3. X-Forwarded-For header (for proxied requests)
    4. Client IP address
    """
    # Check for API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

    # Check for authenticated user
    user_id = request.headers.get("X-Trusted-User-Id")
    if user_id:
        return f"user:{user_id}"

    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    # Fall back to direct client IP
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


async def _check_rate_limit_via_service(
    key: str,
    limit: int,
    window: int,
) -> tuple[bool, RateLimitInfo]:
    """Check rate limit by calling security-service."""
    if not security_config.security_service_url:
        # No service configured - allow all (local development)
        logger.debug("[RATE_LIMIT] SECURITY_SERVICE_URL not configured, allowing request")
        return True, RateLimitInfo(
            limit=limit,
            remaining=limit - 1,
            reset_at=0,
            retry_after=0,
        )

    try:
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": security_config.service_name,
        }
        if security_config.service_api_secret:
            headers["X-Service-Secret"] = security_config.service_api_secret

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{security_config.security_service_url}/api/rate-limit/check",
                json={
                    "key": key,
                    "limit": limit,
                    "window_seconds": window,
                },
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                info = RateLimitInfo(
                    limit=data.get("limit", limit),
                    remaining=data.get("remaining", 0),
                    reset_at=data.get("reset_at", 0),
                    retry_after=data.get("retry_after", 0),
                )
                return data.get("allowed", True), info

            elif response.status_code == 429:
                # Rate limited by service
                data = response.json()
                info = RateLimitInfo(
                    limit=data.get("limit", limit),
                    remaining=0,
                    reset_at=data.get("reset_at", 0),
                    retry_after=data.get("retry_after", 60),
                )
                return False, info

            else:
                logger.warning(f"[RATE_LIMIT] Service returned {response.status_code}")
                # Fail open on service error
                return True, RateLimitInfo(
                    limit=limit,
                    remaining=limit - 1,
                    reset_at=0,
                    retry_after=0,
                )

    except httpx.TimeoutException:
        logger.warning("[RATE_LIMIT] Timeout calling security-service")
        # Fail open on timeout
        return True, RateLimitInfo(
            limit=limit,
            remaining=limit - 1,
            reset_at=0,
            retry_after=0,
        )
    except Exception as e:
        logger.error(f"[RATE_LIMIT] Error checking rate limit: {e}")
        # Fail open on error
        return True, RateLimitInfo(
            limit=limit,
            remaining=limit - 1,
            reset_at=0,
            retry_after=0,
        )


class RateLimiter:
    """
    Rate limiter with configurable limits.

    Usage:
        limiter = RateLimiter()

        @app.get("/api/data")
        async def get_data(_: None = Depends(limiter.limit())):
            ...
    """

    def __init__(
        self,
        default_limit: int | None = None,
        default_window: int = 60,
    ):
        """
        Initialize rate limiter.

        Args:
            default_limit: Default requests per window (from settings)
            default_window: Default window in seconds
        """
        self.default_limit = default_limit or security_config.rate_limit_default
        self.default_window = default_window
        self.enabled = security_config.rate_limit_enabled

    def limit(
        self,
        limit: int | None = None,
        window: int | None = None,
        key_func: Callable[[Request], str] | None = None,
    ) -> Callable:
        """
        Create a rate limit dependency.

        Args:
            limit: Max requests in window (default: self.default_limit)
            window: Window size in seconds (default: self.default_window)
            key_func: Custom function to extract client key

        Returns:
            FastAPI dependency
        """
        _limit = limit or self.default_limit
        _window = window or self.default_window
        _key_func = key_func or _get_client_key

        async def _check_rate_limit(request: Request) -> None:
            # Bypass if rate limiting disabled
            if not self.enabled:
                return

            key = _key_func(request)

            allowed, info = await _check_rate_limit_via_service(
                key=key,
                limit=_limit,
                window=_window,
            )

            # Store info for middleware to add headers
            request.state.rate_limit_info = info

            if not allowed:
                logger.warning(
                    f"[RATE_LIMIT] Rate limited: {key} "
                    f"(limit: {info.limit}, retry_after: {info.retry_after}s)"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={
                        "X-RateLimit-Limit": str(info.limit),
                        "X-RateLimit-Remaining": str(info.remaining),
                        "X-RateLimit-Reset": str(int(info.reset_at)),
                        "Retry-After": str(info.retry_after),
                    },
                )

        return _check_rate_limit


# Global limiter instance for convenience
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def rate_limit(
    limit: int | None = None,
    window: int | None = None,
) -> Callable:
    """
    Convenience function for rate limiting.

    Usage:
        @app.get("/api/data")
        async def get_data(_: None = Depends(rate_limit())):
            ...

        @app.post("/api/expensive")
        async def expensive(_: None = Depends(rate_limit(10, 60))):
            ...
    """
    limiter = get_rate_limiter()
    return limiter.limit(limit, window)
