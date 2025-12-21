"""
Rate Limiting Service.

Handles request rate limiting using Security Supabase as backend.
"""

import logging
import time
from typing import Any

from config import settings
from db import db
from models.rate_limit import RateLimitInfo, RateLimitState

logger = logging.getLogger("security-service")


class RateLimitService:
    """
    Rate limiting service using Security Supabase.

    Implements sliding window rate limiting with configurable limits.
    Falls back to allowing requests if database is unavailable.
    """

    def __init__(self):
        self._default_limit = settings.RATE_LIMIT_DEFAULT
        self._default_window = settings.RATE_LIMIT_WINDOW_SECONDS

    # =========================================================================
    # RATE LIMIT CHECKING
    # =========================================================================

    def check_rate_limit(
        self,
        key: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        """
        Check if a request is allowed and update the rate limit counter.

        Args:
            key: Rate limit key (e.g., "user:123:endpoint:/api/proposals")
            limit: Max requests per window (defaults to config)
            window_seconds: Window size in seconds (defaults to config)

        Returns:
            {
                "allowed": bool,
                "remaining": int,
                "limit": int,
                "reset_at": int (unix timestamp),
                "retry_after": int | None (seconds until reset, if denied)
            }
        """
        limit = limit or self._default_limit
        window_seconds = window_seconds or self._default_window

        # Get current count
        current_count = db.get_rate_limit_count(key, window_seconds)

        # Check if allowed
        allowed = current_count < limit

        if allowed:
            # Increment counter
            new_count = db.increment_rate_limit(key, window_seconds)
            remaining = max(0, limit - new_count)
        else:
            remaining = 0

        # Calculate reset time
        now = int(time.time())
        reset_at = now + window_seconds

        result = {
            "allowed": allowed,
            "remaining": remaining,
            "limit": limit,
            "reset_at": reset_at,
        }

        if not allowed:
            result["retry_after"] = window_seconds
            logger.warning(f"[RATE_LIMIT] Exceeded for key: {key}")

        return result

    def check_only(
        self,
        key: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        """
        Check rate limit status without incrementing.

        Useful for displaying rate limit info to users.
        """
        limit = limit or self._default_limit
        window_seconds = window_seconds or self._default_window

        current_count = db.get_rate_limit_count(key, window_seconds)
        remaining = max(0, limit - current_count)
        allowed = remaining > 0

        now = int(time.time())
        reset_at = now + window_seconds

        return {
            "allowed": allowed,
            "remaining": remaining,
            "limit": limit,
            "reset_at": reset_at,
            "current": current_count,
        }

    # =========================================================================
    # KEY BUILDERS
    # =========================================================================

    @staticmethod
    def build_user_key(user_id: str, endpoint: str | None = None) -> str:
        """Build rate limit key for a user."""
        if endpoint:
            return f"user:{user_id}:endpoint:{endpoint}"
        return f"user:{user_id}:global"

    @staticmethod
    def build_ip_key(ip_address: str, endpoint: str | None = None) -> str:
        """Build rate limit key for an IP address."""
        if endpoint:
            return f"ip:{ip_address}:endpoint:{endpoint}"
        return f"ip:{ip_address}:global"

    @staticmethod
    def build_api_key_key(key_id: str, endpoint: str | None = None) -> str:
        """Build rate limit key for an API key."""
        if endpoint:
            return f"apikey:{key_id}:endpoint:{endpoint}"
        return f"apikey:{key_id}:global"

    @staticmethod
    def build_service_key(service: str, endpoint: str | None = None) -> str:
        """Build rate limit key for a service."""
        if endpoint:
            return f"service:{service}:endpoint:{endpoint}"
        return f"service:{service}:global"

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def check_user_rate_limit(
        self,
        user_id: str,
        endpoint: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Check rate limit for a user."""
        key = self.build_user_key(user_id, endpoint)
        return self.check_rate_limit(key, limit)

    def check_ip_rate_limit(
        self,
        ip_address: str,
        endpoint: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Check rate limit for an IP address."""
        key = self.build_ip_key(ip_address, endpoint)
        return self.check_rate_limit(key, limit)

    def check_api_key_rate_limit(
        self,
        key_id: str,
        limit_per_minute: int,
        endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Check rate limit for an API key."""
        key = self.build_api_key_key(key_id, endpoint)
        return self.check_rate_limit(key, limit_per_minute, window_seconds=60)

    # =========================================================================
    # MAINTENANCE
    # =========================================================================

    def cleanup_expired(self) -> int:
        """
        Clean up expired rate limit windows.

        Should be called periodically (e.g., every 5 minutes).

        Returns:
            Number of expired windows removed
        """
        count = db.cleanup_rate_limits()
        if count > 0:
            logger.info(f"[RATE_LIMIT] Cleaned up {count} expired windows")
        return count

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self, key: str) -> RateLimitState:
        """Get current rate limit state for a key."""
        current = db.get_rate_limit_count(key, self._default_window)
        now = int(time.time())

        return RateLimitState(
            key=key,
            request_count=current,
            window_start=now - self._default_window,
            window_seconds=self._default_window,
        )


# Singleton instance
rate_limit_service = RateLimitService()
