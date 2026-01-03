"""
Cache client factory and configuration.

Usage:
    from crm_cache import get_cache, configure_cache

    # Option 1: Auto-configure from environment
    cache = get_cache()

    # Option 2: Manual configuration
    configure_cache(
        backend="redis",
        redis_url="redis://localhost:6379",
        default_ttl=300,
    )
    cache = get_cache()

Environment variables:
    CACHE_BACKEND: "memory" or "redis" (default: memory)
    CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)
    CACHE_MAX_SIZE: Max entries for memory backend (default: 1000)
    REDIS_URL: Redis connection URL (required if backend=redis)
    CACHE_KEY_PREFIX: Prefix for all keys (default: "cache:")
"""

import logging
import os
from dataclasses import dataclass

from .base import CacheBackend
from .backends.memory import MemoryCacheBackend

logger = logging.getLogger("crm_cache.client")

# Global cache instance
_cache: CacheBackend | None = None
_config: "CacheConfig | None" = None


@dataclass
class CacheConfig:
    """Cache configuration."""

    backend: str = "memory"  # "memory" or "redis"
    redis_url: str | None = None
    key_prefix: str = "cache:"
    default_ttl: int = 300
    max_size: int = 1000  # for memory backend


def configure_cache(
    backend: str = "memory",
    redis_url: str | None = None,
    key_prefix: str = "cache:",
    default_ttl: int = 300,
    max_size: int = 1000,
) -> None:
    """
    Configure the cache backend.

    Call this once at application startup before using get_cache().
    """
    global _config, _cache

    _config = CacheConfig(
        backend=backend,
        redis_url=redis_url,
        key_prefix=key_prefix,
        default_ttl=default_ttl,
        max_size=max_size,
    )
    # Reset cache so next get_cache() uses new config
    _cache = None


def get_cache() -> CacheBackend:
    """
    Get or create the cache backend.

    If not explicitly configured, reads from environment variables.
    """
    global _cache, _config

    if _cache is not None:
        return _cache

    # Auto-configure from environment if not configured
    if _config is None:
        _config = CacheConfig(
            backend=os.getenv("CACHE_BACKEND", "memory"),
            redis_url=os.getenv("REDIS_URL"),
            key_prefix=os.getenv("CACHE_KEY_PREFIX", "cache:"),
            default_ttl=int(os.getenv("CACHE_DEFAULT_TTL", "300")),
            max_size=int(os.getenv("CACHE_MAX_SIZE", "1000")),
        )

    if _config.backend == "redis":
        if _config.redis_url:
            try:
                from .backends.redis import RedisCacheBackend

                _cache = RedisCacheBackend(
                    redis_url=_config.redis_url,
                    key_prefix=_config.key_prefix,
                    default_ttl=_config.default_ttl,
                )
                logger.info("[CACHE] Using Redis backend")
            except ImportError:
                logger.warning(
                    "[CACHE] redis package not installed, falling back to memory"
                )
                _cache = MemoryCacheBackend(
                    max_size=_config.max_size,
                    default_ttl=_config.default_ttl,
                )
            except Exception as e:
                logger.warning(
                    f"[CACHE] Failed to initialize Redis: {e}. "
                    "Falling back to memory backend."
                )
                _cache = MemoryCacheBackend(
                    max_size=_config.max_size,
                    default_ttl=_config.default_ttl,
                )
        else:
            logger.warning("[CACHE] REDIS_URL not set, falling back to memory backend")
            _cache = MemoryCacheBackend(
                max_size=_config.max_size,
                default_ttl=_config.default_ttl,
            )
    else:
        _cache = MemoryCacheBackend(
            max_size=_config.max_size,
            default_ttl=_config.default_ttl,
        )
        logger.info("[CACHE] Using memory backend")

    # Configure decorators to use this backend
    from . import decorators

    decorators.configure(_cache)

    return _cache


def set_cache_backend(backend: CacheBackend) -> None:
    """
    Set a custom cache backend (for testing).
    """
    global _cache
    _cache = backend

    # Configure decorators to use this backend
    from . import decorators

    decorators.configure(_cache)


async def close_cache() -> None:
    """
    Close the cache backend connection.

    Call this on application shutdown.
    """
    global _cache

    if _cache is not None:
        # Redis backend has close method
        if hasattr(_cache, "close"):
            await _cache.close()
        _cache = None
