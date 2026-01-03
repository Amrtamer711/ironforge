"""
Cache backend abstract base class and data models.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        Pattern uses * as wildcard (e.g., "user:123:*").
        Default implementation is inefficient - Redis backend overrides.
        """
        # Default: no-op, subclasses can override
        return 0

    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Atomically increment a counter and return new value.
        Used for rate limiting. Only implemented in Redis backend.
        """
        raise NotImplementedError("incr requires Redis backend")

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set TTL on a key. Only implemented in Redis backend.
        """
        raise NotImplementedError("expire requires Redis backend")

    async def ttl(self, key: str) -> int:
        """
        Get remaining TTL on a key.
        Returns -1 if no expire, -2 if key doesn't exist.
        Only implemented in Redis backend.
        """
        raise NotImplementedError("ttl requires Redis backend")
