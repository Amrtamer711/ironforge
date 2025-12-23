"""
Followup Mockup Strategy.

Handles mockup generation by reusing previous creatives.
"""

from pathlib import Path
from typing import Any, Callable

import config
from db.cache import get_mockup_history, mockup_history
from core.utils.memory import cleanup_memory

from .base import MockupStrategy


class FollowupMockupStrategy(MockupStrategy):
    """
    Strategy for generating mockups from previous creatives.

    Workflow:
    1. Retrieve user's mockup history
    2. Validate history is still valid (files exist)
    3. Validate creative count matches new location frame count
    4. Generate mockup from stored creatives
    5. Update history with new location info
    6. Clean up temporary files
    """

    def __init__(
        self,
        validator: Any,  # MockupValidator
        generate_mockup_func: Callable
    ):
        """
        Initialize followup strategy.

        Args:
            validator: MockupValidator instance
            generate_mockup_func: Function to generate mockup from creatives
        """
        self.validator = validator
        self.generate_mockup_func = generate_mockup_func
        self.logger = config.logger

    def can_handle(self, **kwargs) -> bool:
        """
        Check if strategy can handle request.

        Returns:
            True if mockup_history exists for user
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return False

        history = get_mockup_history(user_id)
        return history is not None

    def get_mode_name(self) -> str:
        """Get mode name for metadata."""
        return "followup"

    async def execute(
        self,
        location_key: str,
        location_name: str,
        time_of_day: str,
        finish: str,
        user_id: str,
        user_companies: list[str],
        **kwargs
    ) -> tuple[Path | None, list[Path], dict[str, Any]]:
        """
        Execute followup mockup generation.

        Args:
            location_key: Canonical location key
            location_name: Display name
            time_of_day: Time filter
            finish: Finish filter
            user_id: User identifier
            user_companies: User's accessible companies
            **kwargs: No additional parameters needed

        Returns:
            Tuple of (result_path, creative_paths, metadata)

        Raises:
            ValueError: If history is invalid or count mismatch
            Exception: If mockup generation fails
        """
        # Retrieve mockup history
        mockup_user_hist = get_mockup_history(user_id)
        if not mockup_user_hist:
            raise ValueError("No mockup history found for user")

        # Validate history
        is_valid, error_msg = await self.validator.validate_mockup_history(
            mockup_user_hist,
            location_key,
            time_of_day,
            finish
        )

        if not is_valid:
            # Clean up corrupted history
            if user_id in mockup_history:
                del mockup_history[user_id]
            raise ValueError(error_msg)

        # Get stored creative paths
        stored_creative_paths = mockup_user_hist.get("creative_paths", [])
        stored_location = mockup_user_hist.get("metadata", {}).get("location_name", "unknown")
        stored_frames = mockup_user_hist.get("metadata", {}).get("num_frames", 1)

        self.logger.info(
            f"[FOLLOWUP_STRATEGY] Reusing {len(stored_creative_paths)} creative(s) "
            f"from '{stored_location}'"
        )

        result_path = None
        try:
            # Generate mockup with stored creatives
            result_path, _ = await self.generate_mockup_func(
                location_key,
                stored_creative_paths,
                time_of_day=time_of_day,
                finish=finish,
                company_schemas=user_companies,
            )

            if not result_path:
                raise Exception("Mockup generation returned None")

            # Prepare metadata
            metadata = {
                "location_key": location_key,
                "location_name": location_name,
                "time_of_day": time_of_day,
                "finish": finish,
                "mode": self.get_mode_name(),
                "num_frames": stored_frames,
                "previous_location": stored_location
            }

            # Update history with new location (in-place update)
            mockup_user_hist["metadata"]["location_key"] = location_key
            mockup_user_hist["metadata"]["location_name"] = location_name
            mockup_user_hist["metadata"]["time_of_day"] = time_of_day
            mockup_user_hist["metadata"]["finish"] = finish

            self.logger.info(
                f"[FOLLOWUP_STRATEGY] Updated history with new location: {location_name}"
            )

            return result_path, stored_creative_paths, metadata

        except Exception as e:
            self.logger.error(f"[FOLLOWUP_STRATEGY] Error generating followup mockup: {e}", exc_info=True)
            raise

        finally:
            # Memory cleanup
            cleanup_memory(context="mockup_followup", aggressive=False, log_stats=False)
