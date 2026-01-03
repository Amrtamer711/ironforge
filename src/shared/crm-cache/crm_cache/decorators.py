"""
Caching decorators for function/method result caching.
"""

import hashlib
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger("crm_cache.decorators")

T = TypeVar("T")

# Global cache instance - set via configure()
_cache_backend: "CacheBackend | None" = None


def configure(backend: "CacheBackend") -> None:
    """Configure the cache backend for decorators."""
    global _cache_backend
    _cache_backend = backend


def get_configured_backend() -> "CacheBackend | None":
    """Get the configured cache backend."""
    return _cache_backend


def cached(
    ttl: int | None = None,
    key_prefix: str = "",
    key_builder: Callable[..., str] | None = None,
):
    """
    Decorator for caching async function results.

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
            cache_backend = _cache_backend

            # If no cache configured, just call function
            if cache_backend is None:
                return await func(*args, **kwargs)

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
                logger.debug(f"[CACHE] Hit: {cache_key}")
                return cached_value

            # Call function and cache result
            logger.debug(f"[CACHE] Miss: {cache_key}")
            result = await func(*args, **kwargs)
            await cache_backend.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator


def cached_method(
    ttl: int | None = None,
    key_prefix: str = "",
    key_builder: Callable[..., str] | None = None,
):
    """
    Decorator for caching instance method results.

    Same as @cached but skips 'self' argument in key building.

    Usage:
        class UserService:
            @cached_method(ttl=60, key_builder=lambda self, user_id: f"user:{user_id}")
            async def get_user(self, user_id: str):
                ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs) -> T:
            cache_backend = _cache_backend

            # If no cache configured, just call function
            if cache_backend is None:
                return await func(self, *args, **kwargs)

            # Build cache key
            if key_builder:
                cache_key = key_builder(self, *args, **kwargs)
            else:
                # Default: hash of class.method + args + kwargs (excluding self)
                key_parts = [
                    self.__class__.__module__,
                    self.__class__.__name__,
                    func.__name__,
                ]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key_data = ":".join(key_parts)
                cache_key = hashlib.md5(key_data.encode()).hexdigest()

            if key_prefix:
                cache_key = f"{key_prefix}:{cache_key}"

            # Try to get from cache
            cached_value = await cache_backend.get(cache_key)
            if cached_value is not None:
                logger.debug(f"[CACHE] Hit: {cache_key}")
                return cached_value

            # Call function and cache result
            logger.debug(f"[CACHE] Miss: {cache_key}")
            result = await func(self, *args, **kwargs)
            await cache_backend.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator


# Alias for convenience
cache = cached
