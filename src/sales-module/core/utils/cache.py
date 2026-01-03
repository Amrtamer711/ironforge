"""
Caching Layer Abstraction.

This module re-exports from the shared crm_cache package for consistency
across all services. All functionality is provided by crm_cache.

Usage:
    from core.utils.cache import get_cache, cached

    # Get cache instance
    cache = get_cache()

    # Basic operations
    await cache.set("key", {"data": "value"}, ttl=300)
    value = await cache.get("key")
    await cache.delete("key")

    # Decorator for caching function results
    @cached(ttl=60)
    async def expensive_operation(param):
        ...

Configuration:
    CACHE_BACKEND: "memory" or "redis" (default: memory)
    CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)
    REDIS_URL: Redis connection URL (if using redis backend)
"""

# Re-export everything from crm_cache
from crm_cache import (
    # Base classes
    CacheBackend,
    CacheEntry,
    CacheStats,
    # Backends
    MemoryCacheBackend,
    # Client
    CacheConfig,
    configure_cache,
    get_cache,
    set_cache_backend,
    close_cache,
    # Decorators
    cached,
    cached_method,
    cache,  # alias for cached
)

# Try to import Redis backend (optional)
try:
    from crm_cache import RedisCacheBackend
except ImportError:
    pass

__all__ = [
    # Base
    "CacheBackend",
    "CacheEntry",
    "CacheStats",
    # Backends
    "MemoryCacheBackend",
    # Client
    "CacheConfig",
    "configure_cache",
    "get_cache",
    "set_cache_backend",
    "close_cache",
    # Decorators
    "cached",
    "cached_method",
    "cache",
]
