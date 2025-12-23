"""
Caching Layer Abstraction.

Provides a unified caching interface with swappable backends:
- Memory: In-process LRU cache (default)
- Redis: Distributed cache for multi-instance deployments

Usage:
    from core.utils.cache import get_cache, cache

    # Get cache instance
    cache = get_cache()

    # Basic operations
    await cache.set("key", {"data": "value"}, ttl=300)
    value = await cache.get("key")
    await cache.delete("key")

    # Decorator for caching function results
    @cache(ttl=60)
    async def expensive_operation(param):
        ...

Configuration:
    CACHE_BACKEND: "memory" or "redis" (default: memory)
    CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)
    REDIS_URL: Redis connection URL (if using redis backend)
"""

import asyncio
import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from core.utils.logging import get_logger

logger = get_logger("utils.cache")

T = TypeVar("T")


@dataclass
class CacheEntry:
    """A cached value with expiration."""
    value: Any
    expires_at: float | None = None  # Unix timestamp

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate percentage."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100


class CacheBackend(ABC):
    """Abstract base for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in cache."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache entries."""
        pass

    @abstractmethod
    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        pass

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache."""
        results = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                results[key] = value
        return results

    async def set_many(
        self,
        mapping: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Set multiple values in cache."""
        success = True
        for key, value in mapping.items():
            if not await self.set(key, value, ttl):
                success = False
        return success

    async def delete_many(self, keys: list[str]) -> int:
        """Delete multiple keys. Returns count of deleted keys."""
        count = 0
        for key in keys:
            if await self.delete(key):
                count += 1
        return count


class MemoryCacheBackend(CacheBackend):
    """
    In-memory LRU cache backend.

    Features:
    - LRU eviction when max_size is reached
    - TTL support per entry
    - Thread-safe via asyncio locks
    - Periodic cleanup of expired entries

    Good for single-instance deployments.
    Data is lost on restart.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int | None = None,
        cleanup_interval: int = 60,
    ):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        self._lock = asyncio.Lock()
        self._stats = CacheStats()

    async def _maybe_cleanup(self) -> None:
        """Periodically clean up expired entries."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.evictions += 1

        if expired_keys:
            logger.debug(f"[CACHE] Cleaned up {len(expired_keys)} expired entries")

    async def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is full."""
        while len(self._cache) >= self._max_size:
            # Remove oldest (first) entry
            self._cache.popitem(last=False)
            self._stats.evictions += 1

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        async with self._lock:
            await self._maybe_cleanup()

            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._stats.hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in cache."""
        async with self._lock:
            # Calculate expiration
            expires_at = None
            effective_ttl = ttl if ttl is not None else self._default_ttl
            if effective_ttl is not None:
                expires_at = time.time() + effective_ttl

            # Remove existing key if present
            if key in self._cache:
                del self._cache[key]

            # Evict if needed
            await self._evict_if_needed()

            # Add new entry
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            self._stats.sets += 1
            return True

    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.deletes += 1
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            logger.info("[CACHE] Memory cache cleared")

    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            sets=self._stats.sets,
            deletes=self._stats.deletes,
            evictions=self._stats.evictions,
        )

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


class RedisCacheBackend(CacheBackend):
    """
    Redis-backed cache backend.

    Features:
    - Distributed caching for multi-instance deployments
    - Native TTL support
    - Atomic operations
    - Persistent across restarts

    Requires:
        pip install redis

    Environment:
        REDIS_URL: Redis connection URL
        CACHE_KEY_PREFIX: Prefix for all cache keys (default: "cache:")
    """

    def __init__(
        self,
        redis_url: str | None = None,
        key_prefix: str = "cache:",
        default_ttl: int | None = None,
    ):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._redis: "redis.asyncio.Redis" | None = None
        self._stats = CacheStats()

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
                await self._redis.ping()
                logger.info("[CACHE] Connected to Redis")
            except ImportError:
                raise RuntimeError(
                    "Redis caching requires 'redis' package. "
                    "Install with: pip install redis"
                )
            except Exception as e:
                logger.error(f"[CACHE] Failed to connect to Redis: {e}")
                raise
        return self._redis

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            value = await redis_client.get(redis_key)

            if value is None:
                self._stats.misses += 1
                return None

            self._stats.hits += 1
            return json.loads(value)

        except Exception as e:
            logger.error(f"[CACHE] Redis get error: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in cache."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            serialized = json.dumps(value)

            effective_ttl = ttl if ttl is not None else self._default_ttl

            if effective_ttl is not None:
                await redis_client.setex(redis_key, effective_ttl, serialized)
            else:
                await redis_client.set(redis_key, serialized)

            self._stats.sets += 1
            return True

        except Exception as e:
            logger.error(f"[CACHE] Redis set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            deleted = await redis_client.delete(redis_key)
            if deleted:
                self._stats.deletes += 1
            return deleted > 0

        except Exception as e:
            logger.error(f"[CACHE] Redis delete error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            return await redis_client.exists(redis_key) > 0

        except Exception as e:
            logger.error(f"[CACHE] Redis exists error: {e}")
            return False

    async def clear(self) -> None:
        """Clear all cache entries with our prefix."""
        try:
            redis_client = await self._get_redis()
            pattern = f"{self._key_prefix}*"

            # Use SCAN to find keys (safe for large datasets)
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                if keys:
                    await redis_client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break

            logger.info(f"[CACHE] Redis cache cleared ({deleted} keys)")

        except Exception as e:
            logger.error(f"[CACHE] Redis clear error: {e}")

    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            sets=self._stats.sets,
            deletes=self._stats.deletes,
            evictions=0,  # Redis handles eviction internally
        )

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache (optimized for Redis)."""
        if not keys:
            return {}

        try:
            redis_client = await self._get_redis()
            redis_keys = [self._make_key(k) for k in keys]
            values = await redis_client.mget(redis_keys)

            results = {}
            for key, value in zip(keys, values, strict=False):
                if value is not None:
                    results[key] = json.loads(value)
                    self._stats.hits += 1
                else:
                    self._stats.misses += 1

            return results

        except Exception as e:
            logger.error(f"[CACHE] Redis mget error: {e}")
            return {}

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Global cache instance
_cache: CacheBackend | None = None


def get_cache() -> CacheBackend:
    """Get or create the cache backend."""
    global _cache
    if _cache is None:
        from app_settings import settings

        backend_type = settings.cache_backend
        default_ttl = settings.cache_default_ttl

        if backend_type == "redis":
            redis_url = settings.redis_url
            if redis_url:
                try:
                    _cache = RedisCacheBackend(
                        redis_url=redis_url,
                        default_ttl=default_ttl,
                    )
                    logger.info("[CACHE] Using Redis backend")
                except Exception as e:
                    logger.warning(
                        f"[CACHE] Failed to initialize Redis: {e}. "
                        "Falling back to memory backend."
                    )
                    _cache = MemoryCacheBackend(default_ttl=default_ttl)
            else:
                logger.warning(
                    "[CACHE] REDIS_URL not set, falling back to memory backend"
                )
                _cache = MemoryCacheBackend(default_ttl=default_ttl)
        else:
            _cache = MemoryCacheBackend(
                max_size=settings.cache_max_size,
                default_ttl=default_ttl,
            )
            logger.info("[CACHE] Using memory backend")

    return _cache


def set_cache_backend(backend: CacheBackend) -> None:
    """Set a custom cache backend (for testing)."""
    global _cache
    _cache = backend


def cached(
    ttl: int | None = None,
    key_prefix: str = "",
    key_builder: Callable[..., str] | None = None,
):
    """
    Decorator for caching function results.

    Args:
        ttl: Cache TTL in seconds (uses default if not specified)
        key_prefix: Prefix for cache key
        key_builder: Custom function to build cache key from args/kwargs

    Usage:
        @cached(ttl=60)
        async def get_user(user_id: str):
            ...

        @cached(key_builder=lambda user_id, **kw: f"user:{user_id}")
        async def get_user(user_id: str, include_details: bool = False):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            cache_backend = get_cache()

            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default: hash of function name + args + kwargs
                key_parts = [func.__module__, func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key_data = ":".join(key_parts)
                cache_key = hashlib.md5(key_data.encode()).hexdigest()

            if key_prefix:
                cache_key = f"{key_prefix}:{cache_key}"

            # Try to get from cache
            cached_value = await cache_backend.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)
            await cache_backend.set(cache_key, result, ttl=ttl)
            return result

        return wrapper
    return decorator


# Alias for convenience
cache = cached
