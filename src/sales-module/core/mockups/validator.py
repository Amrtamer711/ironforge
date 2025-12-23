"""
Mockup Validation Module.

Validates mockup generation requests.
"""

from typing import Any

import config
from db.cache import get_location_frame_count
from db.database import db


class MockupValidator:
    """
    Validates mockup generation requests.

    Responsibilities:
    - Validate location has mockup photos configured
    - Validate creative/prompt count matches frame count
    - Validate mockup history for follow-up requests
    """

    def __init__(self, user_companies: list[str]):
        """
        Initialize validator with user's company access.

        Args:
            user_companies: List of company schemas user has access to
        """
        self.user_companies = user_companies
        self.logger = config.logger

    def validate_location_has_mockups(
        self,
        location_key: str
    ) -> tuple[bool, str | None]:
        """
        Validate location has mockup photos configured.

        Args:
            location_key: Canonical location key

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if location has mockups
            - error_message: Error message if invalid, None otherwise
        """
        variations = db.list_mockup_variations(location_key, self.user_companies)
        if not variations:
            return False, f"No billboard photos configured for location '{location_key}'"
        return True, None

    def validate_creative_count(
        self,
        location_key: str,
        creative_count: int,
        time_of_day: str = "all",
        finish: str = "all"
    ) -> tuple[bool, int, str | None]:
        """
        Validate creative count matches frame count.

        Valid scenarios:
        - 1 creative (will be tiled across all frames)
        - N creatives where N == frame count (one per frame)

        Args:
            location_key: Canonical location key
            creative_count: Number of creatives/prompts provided
            time_of_day: Time of day filter
            finish: Finish filter

        Returns:
            Tuple of (is_valid, required_frame_count, error_message)
            - is_valid: True if count is valid
            - required_frame_count: Expected frame count for location
            - error_message: Error message if invalid, None otherwise
        """
        frame_count = get_location_frame_count(
            location_key,
            self.user_companies,
            time_of_day,
            finish
        )

        is_valid = (creative_count == 1) or (creative_count == frame_count)

        if not is_valid:
            error_msg = (
                f"Creative count mismatch: provided {creative_count}, "
                f"but location requires 1 or {frame_count} frame(s)"
            )
            return False, frame_count, error_msg

        return True, frame_count, None

    def validate_mockup_history(
        self,
        mockup_history: dict[str, Any],
        location_key: str,
        time_of_day: str = "all",
        finish: str = "all"
    ) -> tuple[bool, str | None]:
        """
        Validate mockup history for follow-up requests.

        Args:
            mockup_history: User's mockup history dict
            location_key: Target location key
            time_of_day: Time of day filter
            finish: Finish filter

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if history is valid for reuse
            - error_message: Error message if invalid, None otherwise
        """
        if not mockup_history:
            return False, "No mockup history found"

        # Get stored creative paths
        stored_creative_paths = mockup_history.get("creative_paths", [])
        if not stored_creative_paths:
            return False, "No creatives found in history"

        # Verify all files still exist
        from pathlib import Path
        missing_files = [
            str(p) for p in stored_creative_paths
            if not Path(p).exists()
        ]

        if missing_files:
            self.logger.error(f"[VALIDATOR] Creative files missing from history: {missing_files}")
            return False, "Previous creative files are no longer available"

        # Validate count matches new location
        frame_count = get_location_frame_count(
            location_key,
            self.user_companies,
            time_of_day,
            finish
        )

        num_stored = len(stored_creative_paths)
        is_valid_count = (num_stored == 1) or (num_stored == frame_count)

        if not is_valid_count:
            stored_location = mockup_history.get("metadata", {}).get("location_name", "unknown")
            error_msg = (
                f"Have {num_stored} creative(s) from '{stored_location}', "
                f"but new location requires {frame_count} frame(s)"
            )
            return False, error_msg

        return True, None
