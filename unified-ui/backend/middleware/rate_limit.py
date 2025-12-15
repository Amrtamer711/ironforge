"""
Rate limiting middleware for unified-ui.

[VERIFIED] Mirrors server.js lines 64-102:
- In-memory rate limiter with sliding window
- Configurable max requests per window
- IP + path based key generation
- Periodic cleanup of expired entries
"""

import logging
import threading
import time
from typing import Dict, Optional

from fastapi import HTTPException, Request

from backend.config import get_settings

logger = logging.getLogger("unified-ui")


# =============================================================================
# RATE LIMIT STORE - server.js:67
# =============================================================================

# Format: {key: {"window_start": timestamp, "count": int}}
_rate_limit_store: Dict[str, Dict[str, float]] = {}
_store_lock = threading.Lock()


# =============================================================================
# CLEANUP TASK - server.js:94-102
# =============================================================================

def _cleanup_expired_entries() -> None:
    """
    Clean up expired rate limit entries.
    Mirrors server.js:94-102 setInterval cleanup.
    """
    settings = get_settings()
    window_ms = settings.RATE_LIMIT_WINDOW_MS
    cleanup_threshold = window_ms * 2 / 1000  # Convert to seconds

    while True:
        time.sleep(window_ms / 1000)  # Run every window period

        now = time.time()
        keys_to_delete = []

        with _store_lock:
            for key, record in _rate_limit_store.items():
                if now - record["window_start"] > cleanup_threshold:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del _rate_limit_store[key]

            if keys_to_delete:
                logger.debug(f"[Rate Limit] Cleaned up {len(keys_to_delete)} expired entries")


# Start cleanup thread
_cleanup_thread: Optional[threading.Thread] = None


def start_rate_limit_cleanup() -> None:
    """Start the background cleanup thread."""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_thread = threading.Thread(target=_cleanup_expired_entries, daemon=True)
        _cleanup_thread.start()
        logger.info("[Rate Limit] Started cleanup thread")


# =============================================================================
# RATE LIMITER - server.js:71-92
# =============================================================================

def rate_limiter(max_requests: Optional[int] = None):
    """
    Create a rate limiting dependency.

    Mirrors server.js:71-92 (rateLimiter function)

    Usage:
        @router.post("/login")
        async def login(request: Request, _: None = Depends(rate_limiter(5))):
            ...

    Args:
        max_requests: Maximum requests per window. Defaults to config value.
    """
    settings = get_settings()
    limit = max_requests if max_requests is not None else settings.RATE_LIMIT_MAX_REQUESTS
    window_seconds = settings.RATE_LIMIT_WINDOW_MS / 1000

    async def check_rate_limit(request: Request) -> None:
        """Check if request should be rate limited."""
        # server.js:73-74 - Get IP and build key
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.client.host if request.client else "unknown"
        )
        key = f"{ip}:{request.url.path}"
        now = time.time()

        with _store_lock:
            # server.js:77-80 - Get or create record
            record = _rate_limit_store.get(key)
            if not record or now - record["window_start"] > window_seconds:
                record = {"window_start": now, "count": 0}

            # server.js:82-83 - Increment count
            record["count"] += 1
            _rate_limit_store[key] = record

            # server.js:85-88 - Check if over limit
            if record["count"] > limit:
                logger.warning(f"[Rate Limit] Blocked {ip} on {request.url.path}")
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests, please try again later"
                )

    return check_rate_limit
