"""
CRM Cache SDK

Provides a unified caching interface with swappable backends:
- Memory: In-process LRU cache (default, no dependencies)
- Redis: Distributed cache for multi-instance deployments

Install:
    pip install "crm-cache @ git+https://github.com/org/CRM.git#subdirectory=src/shared/crm-cache"

    # With Redis support:
    pip install "crm-cache[redis] @ git+https://github.com/org/CRM.git#subdirectory=src/shared/crm-cache"

Usage:
    from crm_cache import get_cache, cached, configure_cache

    # Option 1: Auto-configure from environment (CACHE_BACKEND, REDIS_URL)
    cache = get_cache()

    # Option 2: Manual configuration
    configure_cache(backend="redis", redis_url="redis://localhost:6379")
    cache = get_cache()

    # Basic operations
    await cache.set("key", {"data": "value"}, ttl=300)
    value = await cache.get("key")
    await cache.delete("key")

    # Decorator for caching function results
    @cached(ttl=60)
    async def expensive_operation(param):
        ...

    # Custom key builder
    @cached(ttl=300, key_builder=lambda user_id: f"user:{user_id}")
    async def get_user(user_id: str):
        ...

Cache Invalidation:
    # Delete single key
    await cache.delete("user:123")

    # Delete by pattern (Redis only - memory backend uses fnmatch)
    await cache.delete_pattern("user:123:*")

Environment Variables:
    CACHE_BACKEND: "memory" or "redis" (default: memory)
    CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)
    CACHE_MAX_SIZE: Max entries for memory backend (default: 1000)
    REDIS_URL: Redis connection URL (if using redis backend)
    CACHE_KEY_PREFIX: Prefix for all cache keys (default: "cache:")
"""

# Base classes and models
from .base import (
    CacheBackend,
    CacheEntry,
    CacheStats,
)

# Backends
from .backends.memory import MemoryCacheBackend

# Client factory
from .client import (
    CacheConfig,
    configure_cache,
    get_cache,
    set_cache_backend,
    close_cache,
)

# Decorators
from .decorators import (
    cached,
    cached_method,
    cache,  # alias
)

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

# Optional Redis backend
try:
    from .backends.redis import RedisCacheBackend

    __all__.append("RedisCacheBackend")
except ImportError:
    pass
