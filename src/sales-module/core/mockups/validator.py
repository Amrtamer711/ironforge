"""
Mockup Validation Module.

Validates mockup generation requests.
Uses Asset-Management API for mockup frame data.
"""

from pathlib import Path
from typing import Any

import config
from core.services.mockup_frame_service import MockupFrameService


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
        # Single service that searches all companies
        self._service = MockupFrameService(companies=user_companies)

    async def validate_location_has_mockups(
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
        variations = await self._service.list_variations(location_key)
        if variations:
            return True, None

        return False, f"No billboard photos configured for location '{location_key}'"

    async def validate_creative_count(
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
        frame_count = await self._get_location_frame_count(
            location_key,
            time_of_day,
            finish
        )

        if frame_count is None:
            return False, 0, f"No mockup frames found for location '{location_key}'"

        is_valid = (creative_count == 1) or (creative_count == frame_count)

        if not is_valid:
            error_msg = (
                f"Creative count mismatch: provided {creative_count}, "
                f"but location requires 1 or {frame_count} frame(s)"
            )
            return False, frame_count, error_msg

        return True, frame_count, None

    async def validate_mockup_history(
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
        missing_files = [
            str(p) for p in stored_creative_paths
            if not Path(p).exists()
        ]

        if missing_files:
            self.logger.error(f"[VALIDATOR] Creative files missing from history: {missing_files}")
            return False, "Previous creative files are no longer available"

        # Validate count matches new location
        frame_count = await self._get_location_frame_count(
            location_key,
            time_of_day,
            finish
        )

        if frame_count is None:
            return False, f"No mockup frames found for location '{location_key}'"

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

    async def _get_location_frame_count(
        self,
        location_key: str,
        time_of_day: str = "all",
        finish: str = "all",
    ) -> int | None:
        """Get the number of frames for a specific location configuration.

        Args:
            location_key: The location key to look up
            time_of_day: Filter by time of day ("day", "night", "all")
            finish: Filter by finish type ("gold", "matte", "all")

        Returns:
            Number of frames, or None if location not found or no mockups configured
        """
        variations = await self._service.list_variations(location_key)
        if not variations:
            return None

        # Get the first available variation that matches time_of_day/finish
        for tod, finish_list in variations.items():
            if time_of_day != "all" and tod != time_of_day:
                continue

            for fin in finish_list:
                if finish != "all" and fin != finish:
                    continue

                # Get photos for this time_of_day/finish combination
                photos = await self._service.list_photos(location_key, tod, fin)
                if photos:
                    # Get frames for first photo
                    frames_data = await self._service.get_frames(location_key, tod, fin, photos[0])
                    if frames_data:
                        return len(frames_data)

        return None
