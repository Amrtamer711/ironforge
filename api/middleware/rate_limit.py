"""
Rate Limiting Middleware.

Provides request rate limiting to prevent abuse and ensure fair usage.
Uses a sliding window algorithm with in-memory or Redis backing.

Usage:
    from api.middleware.rate_limit import RateLimiter, rate_limit

    # Create limiter with default settings (100 req/min)
    limiter = RateLimiter()

    # Use as dependency
    @app.get("/api/data")
    async def get_data(request: Request, _: None = Depends(limiter.limit())):
        return {"data": "..."}

    # Custom limit for specific endpoint
    @app.post("/api/expensive")
    async def expensive_op(request: Request, _: None = Depends(limiter.limit(10, 60))):
        return {"result": "..."}

Configuration:
    RATE_LIMIT_ENABLED: Set to "true" to enable rate limiting
    RATE_LIMIT_DEFAULT: Default requests per minute (default: 100)
    RATE_LIMIT_BACKEND: "memory" or "redis" (default: memory)
    REDIS_URL: Redis connection URL (if using redis backend)
"""

import asyncio
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from utils.logging import get_logger

logger = get_logger("api.middleware.rate_limit")


@dataclass
class RateLimitInfo:
    """Information about current rate limit status."""
    limit: int           # Max requests allowed
    remaining: int       # Requests remaining in window
    reset_at: float      # Unix timestamp when window resets
    retry_after: int     # Seconds until retry is allowed (if blocked)


class RateLimitBackend(ABC):
    """Abstract base for rate limit storage backends."""

    @abstractmethod
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, RateLimitInfo]:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Unique identifier (e.g., IP, user ID, API key)
            limit: Max requests allowed in window
            window_seconds: Window duration in seconds

        Returns:
            Tuple of (allowed: bool, info: RateLimitInfo)
        """
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        pass


class RedisRateLimitBackend(RateLimitBackend):
    """
    Redis-backed rate limit storage using sliding window.

    Good for distributed deployments with multiple instances.
    Data persists across restarts and is shared between instances.

    Requires:
        pip install redis

    Environment:
        REDIS_URL: Redis connection URL (e.g., redis://localhost:6379)
    """

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis: "redis.asyncio.Redis" | None = None
        self._initialized = False

    async def _get_redis(self) -> "redis.asyncio.Redis":
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis_async
                self._redis = redis_async.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
                logger.info("[RATE_LIMIT] Connected to Redis")
            except ImportError:
                raise RuntimeError(
                    "Redis rate limiting requires 'redis' package. "
                    "Install with: pip install redis"
                )
            except Exception as e:
                logger.error(f"[RATE_LIMIT] Failed to connect to Redis: {e}")
                raise
        return self._redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, RateLimitInfo]:
        """
        Check rate limit using Redis sorted sets with sliding window.

        Uses a Lua script for atomic operations:
        1. Remove old entries outside the window
        2. Count current entries
        3. Add new entry if under limit
        4. Set expiration on the key
        """
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - window_seconds

        # Redis key for this rate limit
        redis_key = f"ratelimit:{key}"

        # Lua script for atomic rate limit check
        # This ensures thread-safety in distributed environments
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local window_seconds = tonumber(ARGV[3])
        local limit = tonumber(ARGV[4])

        -- Remove old entries outside the window
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

        -- Count current entries
        local current_count = redis.call('ZCARD', key)

        -- Calculate remaining
        local remaining = limit - current_count

        -- Get oldest timestamp for reset calculation
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_at
        if #oldest > 0 then
            reset_at = tonumber(oldest[2]) + window_seconds
        else
            reset_at = now + window_seconds
        end

        if current_count < limit then
            -- Add this request
            redis.call('ZADD', key, now, now .. ':' .. math.random())
            -- Set expiration to clean up old keys
            redis.call('EXPIRE', key, window_seconds + 60)
            return {1, remaining - 1, reset_at, 0}
        else
            -- Rate limited
            local retry_after = math.ceil(reset_at - now) + 1
            return {0, 0, reset_at, retry_after}
        end
        """

        try:
            result = await redis_client.eval(
                lua_script,
                1,  # Number of keys
                redis_key,  # KEYS[1]
                str(now),  # ARGV[1]
                str(window_start),  # ARGV[2]
                str(window_seconds),  # ARGV[3]
                str(limit),  # ARGV[4]
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_at = float(result[2])
            retry_after = int(result[3])

            return allowed, RateLimitInfo(
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        except Exception as e:
            logger.error(f"[RATE_LIMIT] Redis error: {e}")
            # Fail open - allow request if Redis is unavailable
            # This prevents Redis issues from blocking all requests
            return True, RateLimitInfo(
                limit=limit,
                remaining=limit,
                reset_at=now + window_seconds,
                retry_after=0,
            )

    async def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        try:
            redis_client = await self._get_redis()
            redis_key = f"ratelimit:{key}"
            await redis_client.delete(redis_key)
        except Exception as e:
            logger.error(f"[RATE_LIMIT] Failed to reset key {key}: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class MemoryRateLimitBackend(RateLimitBackend):
    """
    In-memory rate limit storage using sliding window.

    Good for single-instance deployments.
    Data is lost on restart.
    """

    def __init__(self, cleanup_interval: int = 60):
        # key -> list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    async def _cleanup_old_entries(self) -> None:
        """Remove expired entries to prevent memory growth."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        async with self._lock:
            self._last_cleanup = now
            cutoff = now - 3600  # Keep 1 hour of data max

            keys_to_delete = []
            for key, timestamps in self._requests.items():
                # Filter out old timestamps
                self._requests[key] = [ts for ts in timestamps if ts > cutoff]
                if not self._requests[key]:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._requests[key]

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, RateLimitInfo]:
        """Check rate limit using sliding window."""
        now = time.time()
        window_start = now - window_seconds

        # Cleanup periodically
        await self._cleanup_old_entries()

        async with self._lock:
            # Filter to only requests within window
            timestamps = self._requests[key]
            valid_timestamps = [ts for ts in timestamps if ts > window_start]
            self._requests[key] = valid_timestamps

            current_count = len(valid_timestamps)
            remaining = max(0, limit - current_count)

            # Calculate reset time (end of oldest request's window)
            if valid_timestamps:
                oldest = min(valid_timestamps)
                reset_at = oldest + window_seconds
            else:
                reset_at = now + window_seconds

            if current_count < limit:
                # Allow request, record timestamp
                self._requests[key].append(now)
                return True, RateLimitInfo(
                    limit=limit,
                    remaining=remaining - 1,  # Account for this request
                    reset_at=reset_at,
                    retry_after=0,
                )
            else:
                # Rate limited
                retry_after = int(reset_at - now) + 1
                return False, RateLimitInfo(
                    limit=limit,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                )

    async def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        async with self._lock:
            if key in self._requests:
                del self._requests[key]


# Global backend instance
_backend: RateLimitBackend | None = None


def _get_backend() -> RateLimitBackend:
    """Get or create the rate limit backend."""
    global _backend
    if _backend is None:
        from app_settings import settings

        backend_type = settings.rate_limit_backend

        if backend_type == "redis":
            redis_url = settings.redis_url
            if redis_url:
                try:
                    _backend = RedisRateLimitBackend(redis_url)
                    logger.info("[RATE_LIMIT] Using Redis backend")
                except Exception as e:
                    logger.warning(
                        f"[RATE_LIMIT] Failed to initialize Redis backend: {e}. "
                        "Falling back to memory backend."
                    )
                    _backend = MemoryRateLimitBackend()
            else:
                logger.warning(
                    "[RATE_LIMIT] REDIS_URL not set, falling back to memory backend"
                )
                _backend = MemoryRateLimitBackend()
        else:
            _backend = MemoryRateLimitBackend()
            logger.info("[RATE_LIMIT] Using memory backend")

    return _backend


def set_rate_limit_backend(backend: RateLimitBackend) -> None:
    """Set a custom rate limit backend (for testing)."""
    global _backend
    _backend = backend


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
        # Use hash to avoid storing raw key
        import hashlib
        return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

    # Check for authenticated user
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"

    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP in chain (original client)
        client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    # Fall back to direct client IP
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


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
        from app_settings import settings

        self.default_limit = default_limit or settings.rate_limit_default
        self.default_window = default_window
        self.enabled = settings.rate_limit_enabled

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
            # Skip if disabled
            if not self.enabled:
                return

            backend = _get_backend()
            key = _key_func(request)

            allowed, info = await backend.check_rate_limit(key, _limit, _window)

            # Add rate limit headers to response
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
