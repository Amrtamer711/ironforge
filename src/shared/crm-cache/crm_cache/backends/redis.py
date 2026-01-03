"""
Redis-backed cache backend.

Features:
- Distributed caching for multi-instance deployments
- Native TTL support
- Atomic operations
- Persistent across restarts
- Pattern-based deletion
- Automatic reconnection with connection pooling
- Event loop aware (handles sync-to-async bridges)

Requires:
    pip install redis

Environment:
    REDIS_URL: Redis connection URL
    CACHE_KEY_PREFIX: Prefix for all cache keys (default: "cache:")
"""

import asyncio
import json
import logging
import os
from typing import Any

from ..base import CacheBackend, CacheStats

logger = logging.getLogger("crm_cache.redis")

# Per-event-loop connection storage
# This handles the case where asyncio.run() creates new event loops
_loop_connections: dict[int, tuple["redis.asyncio.Redis", "redis.asyncio.ConnectionPool"]] = {}
_logged_connection = False


class RedisCacheBackend(CacheBackend):
    """Redis-backed cache backend with connection pooling and auto-reconnect."""

    def __init__(
        self,
        redis_url: str | None = None,
        key_prefix: str = "cache:",
        default_ttl: int | None = None,
        max_connections: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._retry_on_timeout = retry_on_timeout
        self._health_check_interval = health_check_interval
        self._stats = CacheStats()

    async def _get_redis(self) -> "redis.asyncio.Redis":
        """Get or create Redis connection for current event loop."""
        global _logged_connection

        # Get current event loop
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            raise RuntimeError("No running event loop")

        # Check if we have a connection for this loop
        if loop_id in _loop_connections:
            redis_client, _ = _loop_connections[loop_id]
            return redis_client

        # Create new connection for this loop
        try:
            import redis.asyncio as redis_async

            # Create a connection pool for this event loop
            pool = redis_async.ConnectionPool.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                retry_on_timeout=self._retry_on_timeout,
                health_check_interval=self._health_check_interval,
            )

            redis_client = redis_async.Redis(connection_pool=pool)

            # Verify connection works
            await redis_client.ping()

            # Store for this loop
            _loop_connections[loop_id] = (redis_client, pool)

            # Only log once to avoid spam
            if not _logged_connection:
                logger.info("[CACHE] Connected to Redis with connection pool")
                _logged_connection = True

            return redis_client

        except ImportError:
            raise RuntimeError(
                "Redis caching requires 'redis' package. "
                "Install with: pip install redis"
            )
        except Exception as e:
            logger.error(f"[CACHE] Failed to connect to Redis: {e}")
            raise

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

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching glob pattern (efficient for Redis)."""
        try:
            redis_client = await self._get_redis()
            full_pattern = self._make_key(pattern)

            # Use SCAN to find keys (safe for large datasets)
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=100,
                )
                if keys:
                    await redis_client.delete(*keys)
                    deleted += len(keys)
                    self._stats.deletes += deleted
                if cursor == 0:
                    break

            return deleted

        except Exception as e:
            logger.error(f"[CACHE] Redis delete_pattern error: {e}")
            return 0

    async def incr(self, key: str, amount: int = 1) -> int:
        """Atomically increment a counter and return new value."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            return await redis_client.incrby(redis_key, amount)
        except Exception as e:
            logger.error(f"[CACHE] Redis incr error: {e}")
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on a key."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            return await redis_client.expire(redis_key, seconds)
        except Exception as e:
            logger.error(f"[CACHE] Redis expire error: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """Get remaining TTL on a key (-1 if no expire, -2 if not exists)."""
        try:
            redis_client = await self._get_redis()
            redis_key = self._make_key(key)
            return await redis_client.ttl(redis_key)
        except Exception as e:
            logger.error(f"[CACHE] Redis ttl error: {e}")
            return -2

    async def close(self) -> None:
        """Close Redis connection for current event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            return

        if loop_id in _loop_connections:
            redis_client, pool = _loop_connections.pop(loop_id)
            try:
                await redis_client.close()
            except Exception:
                pass
            try:
                await pool.disconnect()
            except Exception:
                pass
