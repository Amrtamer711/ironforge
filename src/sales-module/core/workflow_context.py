"""
WorkflowContext for request-scoped caching.

This module provides a context object that can be passed through workflows
(chat -> tool_router -> proposals/mockups) to avoid redundant database queries.

Key optimizations:
- Locations are loaded once at workflow start and reused
- Frames are cached per-location within the workflow
- O(1) lookups instead of database queries
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowContext:
    """
    Request-scoped context for workflow optimization.

    Contains pre-loaded data that can be reused throughout a workflow,
    avoiding redundant database queries.

    Usage:
        # At workflow start (e.g., in llm.py)
        ctx = WorkflowContext.create(user_id, user_companies, db)

        # In tool_router - O(1) lookup instead of DB query
        location = ctx.get_location(location_key)

        # Pass context through
        await process_proposals(ctx, proposals_data, ...)
    """

    user_id: str
    user_companies: list[str]
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)
    _frames_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _networks_cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        user_id: str,
        user_companies: list[str],
        locations_list: list[dict[str, Any]] | None = None,
    ) -> "WorkflowContext":
        """
        Create a new workflow context.

        Args:
            user_id: The user's ID
            user_companies: List of company schemas the user can access
            locations_list: Optional pre-loaded locations list

        Returns:
            WorkflowContext instance with indexed locations
        """
        # Index locations by key for O(1) lookup
        locations_dict = {}
        if locations_list:
            for loc in locations_list:
                key = loc.get("location_key", "").lower()
                if key:
                    locations_dict[key] = loc

        return cls(
            user_id=user_id,
            user_companies=user_companies,
            locations=locations_dict,
        )

    def get_location(self, location_key: str) -> dict[str, Any] | None:
        """
        Get a location by key (O(1) lookup).

        Args:
            location_key: The location key to look up

        Returns:
            Location dict if found, None otherwise
        """
        if not location_key:
            return None
        return self.locations.get(location_key.lower().strip())

    def has_location(self, location_key: str) -> bool:
        """Check if a location exists in the context."""
        if not location_key:
            return False
        return location_key.lower().strip() in self.locations

    def get_locations_list(self) -> list[dict[str, Any]]:
        """Get all locations as a list."""
        return list(self.locations.values())

    def get_frames(self, location_key: str) -> list[dict[str, Any]] | None:
        """
        Get cached frames for a location.

        Returns None if not cached (caller should fetch and cache).
        """
        return self._frames_cache.get(location_key.lower())

    def set_frames(self, location_key: str, frames: list[dict[str, Any]]) -> None:
        """Cache frames for a location."""
        self._frames_cache[location_key.lower()] = frames

    def get_company_hint(self, location_key: str | None = None) -> str | None:
        """
        Get company hint for O(1) asset lookups.

        If location_key is provided, returns the company that owns that location.
        Otherwise, returns the first company in user_companies as a reasonable default.

        Args:
            location_key: Optional location to get company from

        Returns:
            Company schema string or None
        """
        if location_key:
            loc = self.get_location(location_key)
            if loc:
                return loc.get("company_schema") or loc.get("company")

        # Default to first company
        return self.user_companies[0] if self.user_companies else None

    def get_frames_with_company(
        self, location_key: str
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """
        Get cached frames and company hint for a location.

        This combines get_frames() and get_company_hint() for convenience.

        Returns:
            Tuple of (frames or None, company_hint)
        """
        frames = self.get_frames(location_key)
        company_hint = self.get_company_hint(location_key)
        return frames, company_hint

    def get_network(self, network_id: int | str) -> dict[str, Any] | None:
        """Get cached network by ID."""
        return self._networks_cache.get(str(network_id))

    def set_network(self, network_id: int | str, network: dict[str, Any]) -> None:
        """Cache a network."""
        self._networks_cache[str(network_id)] = network

    def validate_locations(
        self,
        location_keys: list[str],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Validate multiple locations against context.

        Args:
            location_keys: List of location keys to validate

        Returns:
            Tuple of (valid_locations, invalid_keys)
        """
        valid = []
        invalid = []

        for key in location_keys:
            loc = self.get_location(key)
            if loc:
                valid.append(loc)
            else:
                invalid.append(key)

        return valid, invalid

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for logging/debugging."""
        return {
            "user_id": self.user_id,
            "user_companies": self.user_companies,
            "locations_count": len(self.locations),
            "cached_frames_count": len(self._frames_cache),
            "cached_networks_count": len(self._networks_cache),
        }
