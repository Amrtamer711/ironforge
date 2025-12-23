"""
Asset Service - Central abstraction for asset/location data.

Phase 1: Database-backed implementation
Phase 2 (Future): Will add Asset-Management API integration with caching
"""

from typing import Any

from db.database import db


class AssetService:
    """
    Manages asset and location data access.

    Current Implementation (Phase 1):
    - Queries database directly via db.get_locations_for_companies()
    - Simple pass-through to database layer

    Future Enhancement (Phase 2):
    - Add caching layer (TTLCache + Redis)
    - Call Asset-Management API instead of database
    - Automatic cache invalidation on updates
    - Graceful degradation if Asset-Management is down
    """

    def __init__(self):
        """Initialize AssetService."""
        # Future: Will accept AssetManagementClient and cache configuration
        pass

    # =========================================================================
    # LOCATION OPERATIONS
    # =========================================================================

    def get_locations_for_companies(
        self,
        companies: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all locations accessible to given companies.

        Returns locations in format:
        [
            {
                "location_key": "dubai_gateway",
                "display_name": "The Gateway",
                "display_type": "digital",  # or "static"
                "company_schema": "backlite_dubai",
                ...
            },
            ...
        ]

        Args:
            companies: List of company schema names (e.g., ["backlite_dubai", "viola"])

        Returns:
            List of location dictionaries

        Example:
            >>> service = AssetService()
            >>> locations = service.get_locations_for_companies(["backlite_dubai"])
            >>> len(locations)
            42
        """
        if not companies:
            return []

        # Phase 1: Direct database query
        return db.get_locations_for_companies(companies)

    def get_location_by_key(
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

        Example:
            >>> service = AssetService()
            >>> loc = service.get_location_by_key("dubai_gateway", ["backlite_dubai"])
            >>> loc["display_name"]
            "The Gateway"
        """
        if not location_key or not companies:
            return None

        # Phase 1: Direct database query
        return db.get_location_by_key(location_key, companies)

    def filter_locations(
        self,
        locations: list[dict[str, Any]],
        display_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Filter locations by criteria.

        Args:
            locations: List of location dicts to filter
            display_type: Filter by "digital" or "static" (None = no filter)
            active_only: Only return active locations (default: True)

        Returns:
            Filtered list of locations

        Example:
            >>> service = AssetService()
            >>> all_locs = service.get_locations_for_companies(["backlite_dubai"])
            >>> digital_locs = service.filter_locations(all_locs, display_type="digital")
        """
        filtered = locations

        if display_type:
            display_type_lower = display_type.lower()
            filtered = [
                loc for loc in filtered
                if loc.get("display_type", "").lower() == display_type_lower
            ]

        if active_only:
            # Assume locations are active by default if field not present
            filtered = [
                loc for loc in filtered
                if loc.get("is_active", True)
            ]

        return filtered

    def get_digital_locations(
        self,
        companies: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all digital (LED) locations for companies.

        Args:
            companies: List of company schemas

        Returns:
            List of digital location dicts
        """
        all_locations = self.get_locations_for_companies(companies)
        return self.filter_locations(all_locations, display_type="digital")

    def get_static_locations(
        self,
        companies: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all static (print/physical) locations for companies.

        Args:
            companies: List of company schemas

        Returns:
            List of static location dicts
        """
        all_locations = self.get_locations_for_companies(companies)
        return self.filter_locations(all_locations, display_type="static")

    # =========================================================================
    # VALIDATION OPERATIONS
    # =========================================================================

    def validate_location_access(
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

        Example:
            >>> service = AssetService()
            >>> has_access, error = service.validate_location_access(
            ...     "dubai_gateway",
            ...     ["backlite_dubai"]
            ... )
            >>> has_access
            True
        """
        if not user_companies:
            return False, "No company access configured"

        location = self.get_location_by_key(location_key, user_companies)

        if not location:
            return False, f"Location '{location_key}' not found or not accessible"

        return True, None

    # =========================================================================
    # FUTURE ENHANCEMENTS (Phase 2) - Stubs for now
    # =========================================================================

    async def check_eligibility(
        self,
        location_key: str,
        service: str,  # "proposal_generator" | "mockup_generator"
        company: str,
    ) -> dict[str, Any]:
        """
        Check if location is eligible for a service.

        Phase 2: Will call Asset-Management eligibility API
        Phase 1: Returns True for all locations (no eligibility checks yet)

        Args:
            location_key: The location to check
            service: Service name ("proposal_generator" or "mockup_generator")
            company: Company schema

        Returns:
            {
                "eligible": bool,
                "details": list[str],  # Reasons if not eligible
            }
        """
        # Phase 1: Stub - assume all locations eligible
        return {
            "eligible": True,
            "details": [],
        }

    async def get_pricing(
        self,
        location_key: str,
        company: str,
    ) -> dict[str, Any]:
        """
        Get current pricing for a location.

        Phase 2: Will call Asset-Management pricing API
        Phase 1: Returns empty dict (pricing stored in proposals directly)

        Args:
            location_key: The location key
            company: Company schema

        Returns:
            {
                "base_rate": Decimal,
                "upload_fee": Decimal,
                "currency": str,
                ...
            }
        """
        # Phase 1: Stub - pricing not available yet from centralized source
        return {}

    async def expand_package(
        self,
        package_id: int,
        company: str,
    ) -> list[dict[str, Any]]:
        """
        Expand a package to its constituent locations.

        Phase 2: Will call Asset-Management package expansion API
        Phase 1: Not implemented yet

        Args:
            package_id: The package ID to expand
            company: Company schema

        Returns:
            List of location dicts
        """
        # Phase 1: Stub - package expansion not available yet
        return []
