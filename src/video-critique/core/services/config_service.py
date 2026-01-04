"""
Config Service - Central abstraction for video-critique configuration data.

Loads videographers, sales_people, locations, reviewers from the video_config table
with TTL caching for efficiency.

Follows the same singleton pattern as AssetService for consistency.
"""

import logging
from typing import Any

from cachetools import TTLCache

from db.database import db
from db.models import ConfigType

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL = 300  # 5 minutes
CACHE_MAX_SIZE = 100  # Config data is small


class ConfigService:
    """
    Service for loading and caching video-critique configuration data.

    Loads from video_config Supabase table with per-type caching.

    Features:
    - In-memory caching with TTL (5 min)
    - Lazy loading (only fetches when requested)
    - Cache invalidation support

    Usage:
        service = get_config_service()
        videographers = service.get_videographers()
        email = service.resolve_email_from_slack_id("U12345678")
    """

    def __init__(
        self,
        cache_ttl: int = CACHE_TTL,
        cache_max_size: int = CACHE_MAX_SIZE,
    ):
        """
        Initialize ConfigService.

        Args:
            cache_ttl: Cache TTL in seconds (default: 300)
            cache_max_size: Maximum cache entries (default: 100)
        """
        self._cache: TTLCache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl)
        logger.info("[CONFIG SERVICE] Initialized")

    def _load_config_type(self, config_type: str) -> dict[str, dict[str, Any]]:
        """
        Load all configs of a type from database.

        Args:
            config_type: ConfigType enum value (e.g., "videographer")

        Returns:
            Dict mapping config_key to config_data
        """
        configs = db.get_all_configs(config_type)
        return {c.config_key: c.config_data for c in configs}

    # =========================================================================
    # CONFIG GETTERS
    # =========================================================================

    def get_videographers(self) -> dict[str, dict[str, Any]]:
        """
        Get videographers config.

        Returns:
            Dict mapping email/name to config data:
            {
                "videographer@example.com": {
                    "name": "John Doe",
                    "slack_id": "U12345678"
                },
                ...
            }
        """
        cache_key = "videographers"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.VIDEOGRAPHER.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} videographers")
        return self._cache[cache_key]

    def get_sales_people(self) -> dict[str, dict[str, Any]]:
        """
        Get sales people config.

        Returns:
            Dict mapping name to config data:
            {
                "John Smith": {
                    "email": "john@example.com",
                    "slack_id": "U12345678"
                },
                ...
            }
        """
        cache_key = "sales_people"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.SALESPERSON.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} sales people")
        return self._cache[cache_key]

    def get_locations(self) -> dict[str, dict[str, Any]]:
        """
        Get location mappings config.

        Returns:
            Dict mapping location_key to config data:
            {
                "TTC Dubai": {
                    "canonical": "ttc_dubai",
                    "aliases": ["TTC", "Dubai Mall TTC"]
                },
                ...
            }
        """
        cache_key = "locations"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.LOCATION.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} locations")
        return self._cache[cache_key]

    def get_reviewers(self) -> dict[str, dict[str, Any]]:
        """
        Get reviewer config.

        Returns:
            Dict mapping email to config data
        """
        cache_key = "reviewers"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.REVIEWER.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} reviewers")
        return self._cache[cache_key]

    def get_head_of_sales(self) -> dict[str, dict[str, Any]]:
        """
        Get head of sales config.

        Returns:
            Dict mapping email to config data
        """
        cache_key = "head_of_sales"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.HEAD_OF_SALES.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} head of sales")
        return self._cache[cache_key]

    def get_head_of_dept(self) -> dict[str, dict[str, Any]]:
        """
        Get head of department config.

        Returns:
            Dict mapping email to config data
        """
        cache_key = "head_of_dept"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_config_type(ConfigType.HEAD_OF_DEPT.value)
            logger.debug(f"[CONFIG SERVICE] Loaded {len(self._cache[cache_key])} head of dept")
        return self._cache[cache_key]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def resolve_email_from_slack_id(self, slack_user_id: str) -> str | None:
        """
        Resolve email from Slack user ID by checking all config types.

        Searches through videographers, sales_people, reviewers, head_of_sales
        to find a matching slack_id.

        Args:
            slack_user_id: Slack user ID (e.g., "U12345678")

        Returns:
            Email address if found, None otherwise
        """
        if not slack_user_id:
            return None

        # Check videographers (key is email)
        for email, data in self.get_videographers().items():
            if data.get("slack_id") == slack_user_id:
                return email

        # Check sales people (key is name, email in data)
        for name, data in self.get_sales_people().items():
            if data.get("slack_id") == slack_user_id:
                return data.get("email")

        # Check reviewers (key is email)
        for email, data in self.get_reviewers().items():
            if data.get("slack_id") == slack_user_id:
                return email

        # Check head of sales (key is email)
        for email, data in self.get_head_of_sales().items():
            if data.get("slack_id") == slack_user_id:
                return email

        # Check head of dept (key is email)
        for email, data in self.get_head_of_dept().items():
            if data.get("slack_id") == slack_user_id:
                return email

        return None

    def get_videographer_names(self) -> list[str]:
        """Get list of videographer names/keys for validation."""
        return list(self.get_videographers().keys())

    def get_sales_people_names(self) -> list[str]:
        """Get list of sales people names for validation."""
        return list(self.get_sales_people().keys())

    def get_location_names(self) -> list[str]:
        """Get list of location keys for validation."""
        return list(self.get_locations().keys())

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    def invalidate_cache(self, config_type: str | None = None) -> None:
        """
        Invalidate cache for a config type or all.

        Args:
            config_type: ConfigType value to invalidate, or None for all
        """
        if config_type:
            key_map = {
                ConfigType.VIDEOGRAPHER.value: "videographers",
                ConfigType.SALESPERSON.value: "sales_people",
                ConfigType.LOCATION.value: "locations",
                ConfigType.REVIEWER.value: "reviewers",
                ConfigType.HEAD_OF_SALES.value: "head_of_sales",
                ConfigType.HEAD_OF_DEPT.value: "head_of_dept",
            }
            cache_key = key_map.get(config_type)
            if cache_key and cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"[CONFIG SERVICE] Invalidated cache for {config_type}")
        else:
            self._cache.clear()
            logger.info("[CONFIG SERVICE] Cache cleared")

    def clear_cache(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()
        logger.info("[CONFIG SERVICE] Cache cleared")


# Singleton instance
_config_service: ConfigService | None = None


def get_config_service() -> ConfigService:
    """
    Get the singleton ConfigService instance.

    Returns:
        ConfigService instance
    """
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
