"""
WorkflowContext for request-scoped context passing.

This module provides a context object that can be passed through workflows
(chat -> tool_router -> services) to maintain consistent context and avoid
redundant lookups.

Follows the same pattern as sales-module for platform alignment:
- User identity (ID, email, display name)
- User companies for RBAC-based multi-tenancy
- Location caching with O(1) lookups

Note: Config data (videographers, sales people, etc.) is now loaded via
ConfigService with TTL caching, not passed through WorkflowContext.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowContext:
    """
    Request-scoped context for video-critique workflows.

    Contains user identity, company access, and location data that can be
    reused throughout a workflow, providing consistent context and O(1)
    lookups to all components.

    Usage:
        # At workflow start (e.g., in llm.py)
        ctx = WorkflowContext.create(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            user_companies=user_companies,
            locations_list=locations,
        )

        # In tool_router - O(1) lookup instead of DB query
        location = ctx.get_location(location_key)

        # Access user info
        display_name = ctx.get_display_name()
    """

    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_companies: list[str] = field(default_factory=list)
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Light caching for repeated lookups
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        user_id: str,
        user_email: str | None = None,
        user_name: str | None = None,
        user_companies: list[str] | None = None,
        locations_list: list[dict[str, Any]] | None = None,
    ) -> "WorkflowContext":
        """
        Create a new workflow context.

        Args:
            user_id: The user's ID (Slack ID or platform ID)
            user_email: User's email address (primary identifier per platform pattern)
            user_name: User's display name
            user_companies: List of company schemas the user can access
            locations_list: Pre-loaded locations list (indexed for O(1) lookup)

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
            user_email=user_email,
            user_name=user_name,
            user_companies=user_companies or [],
            locations=locations_dict,
        )

    def get_display_name(self) -> str:
        """
        Get user's display name for messages.

        Falls back through: user_name -> email prefix -> "there"
        """
        if self.user_name:
            return self.user_name
        if self.user_email:
            return self.user_email.split("@")[0].replace(".", " ").title()
        return "there"

    def get_tracking_name(self) -> str:
        """
        Get user's name for cost tracking.

        Uses display name or email for human-readable tracking.
        """
        if self.user_name:
            return self.user_name
        if self.user_email:
            return self.user_email
        return self.user_id

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

    def get_cached(self, key: str) -> Any | None:
        """Get a cached value."""
        return self._cache.get(key)

    def set_cached(self, key: str, value: Any) -> None:
        """Set a cached value."""
        self._cache[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for logging/debugging."""
        return {
            "user_id": self.user_id,
            "user_email": self.user_email,
            "user_name": self.user_name,
            "user_companies": self.user_companies,
            "locations_count": len(self.locations),
            "cache_keys": list(self._cache.keys()),
        }

    def __repr__(self) -> str:
        return (
            f"WorkflowContext(user_id={self.user_id!r}, "
            f"user_email={self.user_email!r}, "
            f"user_name={self.user_name!r})"
        )
