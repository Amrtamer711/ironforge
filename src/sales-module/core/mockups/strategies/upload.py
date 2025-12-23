"""
Upload Mockup Strategy.

Handles mockup generation from uploaded creative images.
"""

import os
from pathlib import Path
from typing import Any, Callable

import config
from db.cache import get_location_frame_count, store_mockup_history
from core.utils.memory import cleanup_memory

from .base import MockupStrategy


class UploadMockupStrategy(MockupStrategy):
    """
    Strategy for generating mockups from uploaded images.

    Workflow:
    1. Validate creative count matches frame count
    2. Generate mockup from uploaded image(s)
    3. Store creatives in history for follow-up requests
    4. Clean up temporary files
    """

    def __init__(
        self,
        validator: Any,  # MockupValidator
        generate_mockup_func: Callable
    ):
        """
        Initialize upload strategy.

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
            True if uploaded_creatives is provided and not empty
        """
        uploaded_creatives = kwargs.get("uploaded_creatives", [])
        return len(uploaded_creatives) > 0

    def get_mode_name(self) -> str:
        """Get mode name for metadata."""
        return "uploaded"

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
        Execute upload mockup generation.

        Args:
            location_key: Canonical location key
            location_name: Display name
            time_of_day: Time filter
            finish: Finish filter
            user_id: User identifier
            user_companies: User's accessible companies
            **kwargs: Must include 'uploaded_creatives' (list[Path])

        Returns:
            Tuple of (result_path, creative_paths, metadata)

        Raises:
            ValueError: If creative count doesn't match frame count
            Exception: If mockup generation fails
        """
        uploaded_creatives = kwargs.get("uploaded_creatives", [])
        if not uploaded_creatives:
            raise ValueError("No uploaded creatives provided")

        self.logger.info(f"[UPLOAD_STRATEGY] Processing {len(uploaded_creatives)} uploaded image(s)")

        # Validate creative count
        is_valid, frame_count, error_msg = self.validator.validate_creative_count(
            location_key,
            len(uploaded_creatives),
            time_of_day,
            finish
        )

        if not is_valid:
            raise ValueError(error_msg)

        result_path = None
        try:
            # Generate mockup
            result_path, _ = await self.generate_mockup_func(
                location_key,
                uploaded_creatives,
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
                "num_frames": frame_count or 1
            }

            # Store in history for follow-ups
            store_mockup_history(user_id, uploaded_creatives, metadata)
            self.logger.info(f"[UPLOAD_STRATEGY] Stored {len(uploaded_creatives)} creative(s) in history")

            return result_path, uploaded_creatives, metadata

        except Exception as e:
            self.logger.error(f"[UPLOAD_STRATEGY] Error generating mockup: {e}", exc_info=True)
            # Cleanup uploaded files on error
            for creative_file in uploaded_creatives:
                try:
                    os.unlink(creative_file)
                except OSError as cleanup_err:
                    self.logger.debug(f"[UPLOAD_STRATEGY] Failed to cleanup creative: {cleanup_err}")
            raise

        finally:
            # Memory cleanup
            cleanup_memory(context="mockup_upload", aggressive=False, log_stats=False)
