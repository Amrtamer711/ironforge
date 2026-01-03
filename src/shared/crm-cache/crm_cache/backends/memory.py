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

import asyncio
import fnmatch
import logging
import time
from collections import OrderedDict
from typing import Any

from ..base import CacheBackend, CacheEntry, CacheStats

logger = logging.getLogger("crm_cache.memory")


class MemoryCacheBackend(CacheBackend):
    """In-memory LRU cache backend."""

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
            key for key, entry in self._cache.items() if entry.is_expired()
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

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching glob pattern."""
        async with self._lock:
            matching_keys = [
                key for key in self._cache.keys() if fnmatch.fnmatch(key, pattern)
            ]
            for key in matching_keys:
                del self._cache[key]
                self._stats.deletes += 1
            return len(matching_keys)

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)
