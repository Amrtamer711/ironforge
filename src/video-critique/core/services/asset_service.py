"""
Asset Service - Central abstraction for asset/location data.

All location data comes from Asset-Management API. Follows the same pattern
as sales-module for consistent platform architecture.

Video-critique's AssetService is simpler since it doesn't need template/mockup
caching - it primarily needs location lookups for task assignment and workflows.
"""

import logging
from typing import Any

from cachetools import TTLCache

import config
from integrations.asset_management import AssetManagementClient, get_asset_client

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL = 300  # 5 minutes
CACHE_MAX_SIZE = 1000


class AssetService:
    """
    Async service for asset and location data access.

    All data is fetched from Asset-Management API with per-company caching.

    Features:
    - Async methods (non-blocking)
    - In-memory caching with TTL
    - Per-company cache sharing (User A caches company_a, User B reuses it)

    Usage:
        service = get_asset_service()
        locations = await service.get_locations_for_companies(["backlite_dubai"])
    """

    def __init__(
        self,
        client: AssetManagementClient | None = None,
        cache_ttl: int = CACHE_TTL,
        cache_max_size: int = CACHE_MAX_SIZE,
    ):
        """
        Initialize AssetService.

        Args:
            client: Optional AssetManagementClient instance
            cache_ttl: Cache TTL in seconds (default: 300)
            cache_max_size: Maximum cache entries (default: 1000)
        """
        self._client = client or get_asset_client()
        self._cache: TTLCache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl)
        logger.info(
            f"[ASSET SERVICE] Initialized (url={config.ASSET_MGMT_URL or 'http://localhost:8001'})"
        )

    def _cache_key(self, prefix: str, *args) -> str:
        """Generate a cache key."""
        return f"{prefix}:{':'.join(str(a) for a in args)}"

    # =========================================================================
    # LOCATION OPERATIONS
    # =========================================================================

    async def get_locations_for_companies(
        self,
        companies: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all locations accessible to given companies.

        Uses per-company caching for maximum cache sharing across users.
        If User A caches company_a, User B with [company_a, company_b] reuses that cache.

        Returns locations in format:
        [
            {
                "location_key": "dubai_gateway",
                "display_name": "The Gateway",
                "display_type": "digital",
                "company_schema": "backlite_dubai",
                ...
            },
            ...
        ]

        Args:
            companies: List of company schema names (e.g., ["backlite_dubai", "viola"])

        Returns:
            List of location dictionaries

        Raises:
            ConnectionError: If Asset-Management API is unreachable
        """
        if not companies:
            return []

        all_locations = []
        companies_to_fetch = []

        # Check which companies are already cached (per-company caching)
        for company in companies:
            cache_key = self._cache_key("locations_co", company)
            if cache_key in self._cache:
                logger.debug(f"[ASSET SERVICE] Cache hit for company: {company}")
                all_locations.extend(self._cache[cache_key])
            else:
                companies_to_fetch.append(company)

        # Fetch missing companies from API (batch call)
        if companies_to_fetch:
            logger.debug(f"[ASSET SERVICE] Fetching locations for: {companies_to_fetch}")
            fetched = await self._client.get_locations(companies_to_fetch)

            # Group by company and cache individually
            by_company: dict[str, list[dict[str, Any]]] = {c: [] for c in companies_to_fetch}
            for loc in fetched:
                company = loc.get("company_schema") or loc.get("company")
                if company in by_company:
                    by_company[company].append(loc)

            # Cache each company separately
            for company, locs in by_company.items():
                cache_key = self._cache_key("locations_co", company)
                self._cache[cache_key] = locs
                all_locations.extend(locs)
                logger.debug(f"[ASSET SERVICE] Cached {len(locs)} locations for {company}")

        return all_locations

    async def get_location_by_key(
        self,
        location_key: str,
        companies: list[str],
    ) -> dict[str, Any] | None:
        """
        Get a single location by its key.

        Args:
            location_key: The location key (e.g., "dubai_gateway")
            companies: List of company schemas user has access to

        Returns:
            Location dict if found and user has access, None otherwise

        Raises:
            ConnectionError: If Asset-Management API is unreachable
        """
        if not location_key or not companies:
            return None

        # Check cache
        cache_key = self._cache_key("location", location_key, *sorted(companies))
        if cache_key in self._cache:
            logger.debug(f"[ASSET SERVICE] Cache hit for location: {location_key}")
            return self._cache[cache_key]

        # Fetch from Asset-Management API
        location = await self._client.get_location_by_key(location_key, companies)
        if location:
            self._cache[cache_key] = location
        return location

    def filter_locations(
        self,
        locations: list[dict[str, Any]],
        display_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Filter locations by criteria. (Sync - operates on in-memory data)

        Args:
            locations: List of location dicts to filter
            display_type: Filter by "digital" or "static" (None = no filter)
            active_only: Only return active locations (default: True)

        Returns:
            Filtered list of locations
        """
        filtered = locations

        if display_type:
            display_type_lower = display_type.lower()
            filtered = [
                loc for loc in filtered
                if loc.get("display_type", "").lower() == display_type_lower
            ]

        if active_only:
            filtered = [
                loc for loc in filtered
                if loc.get("is_active", True)
            ]

        return filtered

    # =========================================================================
    # VALIDATION OPERATIONS
    # =========================================================================

    async def validate_location_access(
        self,
        location_key: str,
        user_companies: list[str],
    ) -> tuple[bool, str | None]:
        """
        Validate that user has access to a location.

        Args:
            location_key: The location key to validate
            user_companies: Companies user has access to

        Returns:
            Tuple of (has_access, error_message)
            - If valid: (True, None)
            - If invalid: (False, "error message")
        """
        if not user_companies:
            return False, "No company access configured"

        location = await self.get_location_by_key(location_key, user_companies)

        if not location:
            return False, f"Location '{location_key}' not found or not accessible"

        return True, None

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    def clear_cache(self):
        """Clear the entire cache."""
        self._cache.clear()
        logger.info("[ASSET SERVICE] Cache cleared")

    def invalidate_location(self, location_key: str):
        """Invalidate cache entries for a specific location."""
        keys_to_remove = [k for k in self._cache.keys() if location_key in k]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"[ASSET SERVICE] Invalidated {len(keys_to_remove)} cache entries for {location_key}")

    def invalidate_company(self, company: str):
        """Invalidate all cache entries for a specific company."""
        cache_key = self._cache_key("locations_co", company)
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.debug(f"[ASSET SERVICE] Invalidated cache for company: {company}")


# Singleton instance
_asset_service: AssetService | None = None


def get_asset_service() -> AssetService:
    """
    Get the singleton AssetService instance.

    Returns:
        AssetService instance
    """
    global _asset_service
    if _asset_service is None:
        _asset_service = AssetService()
    return _asset_service
