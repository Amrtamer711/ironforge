"""
Location matching utilities for Sales-Module.

Provides consistent location key matching and validation across proposals and mockups.
Uses database or Asset-Management provided locations (caller's responsibility).
"""

from typing import Any


def match_location_key(
    location_input: str,
    available_locations: list[dict[str, Any]],
) -> str | None:
    """
    Match a location input (display name or partial match) to its canonical location_key.

    Matching strategy:
    1. Exact location_key match
    2. Exact display_name match (case-insensitive)
    3. Fuzzy substring matching (legacy compatibility)

    Args:
        location_input: User-provided location string (can be display name, partial name, or key)
        available_locations: List of location dicts from database/Asset-Management.
                           Each dict should have: location_key, display_name (optional)

    Returns:
        Canonical location_key if found, None otherwise

    Examples:
        >>> locations = [
        ...     {"location_key": "dubai_gateway", "display_name": "The Gateway"},
        ...     {"location_key": "dubai_jawhara", "display_name": "Jawhara Mall"}
        ... ]
        >>> match_location_key("The Gateway", locations)
        'dubai_gateway'
        >>> match_location_key("gateway", locations)
        'dubai_gateway'
        >>> match_location_key("nonexistent", locations)
        None
    """
    if not location_input or not available_locations:
        return None

    location_normalized = location_input.strip().lower()

    # Strategy 1: Exact location_key match
    for loc in available_locations:
        key = loc.get("location_key", "")
        if key.lower() == location_normalized:
            return key

    # Strategy 2: Exact display_name match (case-insensitive)
    for loc in available_locations:
        display_name = loc.get("display_name", "")
        if display_name and display_name.lower() == location_normalized:
            return loc.get("location_key")

    # Strategy 3: Fuzzy substring matching (legacy compatibility)
    # Check if input is substring of key or display_name
    for loc in available_locations:
        key = loc.get("location_key", "").lower()
        display_name = loc.get("display_name", "").lower()

        # Check if input matches key
        if key and (location_normalized in key or key in location_normalized):
            return loc.get("location_key")

        # Check if input matches display name
        if display_name and (location_normalized in display_name or display_name in location_normalized):
            return loc.get("location_key")

    return None


def validate_location_exists(
    location_key: str,
    available_locations: list[dict[str, Any]],
) -> bool:
    """
    Validate that a location_key exists in the available locations.

    Args:
        location_key: The location key to validate
        available_locations: List of location dicts from database/Asset-Management

    Returns:
        True if location exists, False otherwise

    Example:
        >>> locations = [{"location_key": "dubai_gateway", "display_name": "The Gateway"}]
        >>> validate_location_exists("dubai_gateway", locations)
        True
        >>> validate_location_exists("nonexistent", locations)
        False
    """
    if not location_key or not available_locations:
        return False

    location_key_lower = location_key.lower()

    for loc in available_locations:
        key = loc.get("location_key", "")
        if key.lower() == location_key_lower:
            return True

    return False


def get_location_display_name(
    location_key: str,
    available_locations: list[dict[str, Any]],
) -> str:
    """
    Get the human-readable display name for a location key.

    Args:
        location_key: The location key (e.g., 'dubai_gateway')
        available_locations: List of location dicts from database/Asset-Management

    Returns:
        Display name if found, otherwise returns the key itself (title-cased)

    Example:
        >>> locations = [{"location_key": "dubai_gateway", "display_name": "The Gateway"}]
        >>> get_location_display_name("dubai_gateway", locations)
        "The Gateway"
        >>> get_location_display_name("unknown_key", locations)
        "Unknown Key"
    """
    if not location_key:
        return ""

    if not available_locations:
        return location_key.replace("_", " ").title()

    location_key_lower = location_key.lower()

    for loc in available_locations:
        key = loc.get("location_key", "")
        if key.lower() == location_key_lower:
            display_name = loc.get("display_name")
            return display_name or key.replace("_", " ").title()

    # Fall back to title-cased key if not found
    return location_key.replace("_", " ").title()


def match_and_validate(
    location_input: str,
    available_locations: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """
    Match and validate a location input, returning both the key and any error message.

    Convenience function that combines matching and validation with descriptive errors.

    Args:
        location_input: User-provided location string
        available_locations: List of location dicts from database/Asset-Management

    Returns:
        Tuple of (matched_key, error_message)
        - If successful: (location_key, None)
        - If failed: (None, error_message)

    Example:
        >>> locations = [{"location_key": "dubai_gateway", "display_name": "The Gateway"}]
        >>> match_and_validate("Gateway", locations)
        ("dubai_gateway", None)
        >>> match_and_validate("invalid", locations)
        (None, "Unknown location 'invalid'")
    """
    if not location_input:
        return None, "Location name is required"

    if not available_locations:
        return None, "No locations available for your company access"

    matched_key = match_location_key(location_input, available_locations)

    if not matched_key:
        return None, f"Unknown location '{location_input}'"

    # Double-check validation (should always pass if match succeeded)
    if not validate_location_exists(matched_key, available_locations):
        return None, f"Location '{matched_key}' not found in available locations"

    return matched_key, None


def get_location_metadata(
    location_key: str,
    available_locations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Get full metadata dictionary for a location.

    Args:
        location_key: The location key to look up
        available_locations: List of location dicts from database/Asset-Management

    Returns:
        Full location metadata dict if found, empty dict otherwise

    Example:
        >>> locations = [{"location_key": "dubai_gateway", "display_name": "The Gateway", "type": "digital"}]
        >>> get_location_metadata("dubai_gateway", locations)
        {"location_key": "dubai_gateway", "display_name": "The Gateway", "type": "digital"}
    """
    if not location_key or not available_locations:
        return {}

    location_key_lower = location_key.lower()

    for loc in available_locations:
        key = loc.get("location_key", "")
        if key.lower() == location_key_lower:
            return loc

    return {}
