"""
AI Mockup Strategy.

Handles mockup generation with AI-generated creatives.
"""

import os
from pathlib import Path
from typing import Any, Callable

import config
from db.cache import get_location_frame_count, store_mockup_history
from core.utils.memory import cleanup_memory

from .base import MockupStrategy


class AIMockupStrategy(MockupStrategy):
    """
    Strategy for generating mockups with AI-generated creatives.

    Workflow:
    1. Validate AI prompt count matches frame count
    2. Generate creative(s) from AI prompt(s)
    3. Generate mockup from AI creative(s)
    4. Store AI creatives in history for follow-up requests
    5. Clean up temporary files
    """

    def __init__(
        self,
        validator: Any,  # MockupValidator
        generate_ai_mockup_func: Callable
    ):
        """
        Initialize AI strategy.

        Args:
            validator: MockupValidator instance
            generate_ai_mockup_func: Function to generate AI creative and mockup
        """
        self.validator = validator
        self.generate_ai_mockup_func = generate_ai_mockup_func
        self.logger = config.logger

    def can_handle(self, **kwargs) -> bool:
        """
        Check if strategy can handle request.

        Returns:
            True if ai_prompts is provided and not empty
        """
        ai_prompts = kwargs.get("ai_prompts", [])
        return len(ai_prompts) > 0

    def get_mode_name(self) -> str:
        """Get mode name for metadata."""
        return "ai_generated"

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
        Execute AI mockup generation.

        Args:
            location_key: Canonical location key
            location_name: Display name
            time_of_day: Time filter
            finish: Finish filter
            user_id: User identifier
            user_companies: User's accessible companies
            **kwargs: Must include 'ai_prompts' (list[str])

        Returns:
            Tuple of (result_path, creative_paths, metadata)

        Raises:
            ValueError: If prompt count doesn't match frame count
            Exception: If AI generation or mockup fails
        """
        ai_prompts = kwargs.get("ai_prompts", [])
        if not ai_prompts:
            raise ValueError("No AI prompts provided")

        # Clean and validate prompts
        if not isinstance(ai_prompts, list):
            ai_prompts = [ai_prompts]
        ai_prompts = [str(p).strip() for p in ai_prompts if p]

        num_prompts = len(ai_prompts)
        self.logger.info(f"[AI_STRATEGY] Processing {num_prompts} AI prompt(s)")

        # Validate prompt count
        is_valid, frame_count, error_msg = self.validator.validate_creative_count(
            location_key,
            num_prompts,
            time_of_day,
            finish
        )

        if not is_valid:
            raise ValueError(error_msg)

        result_path = None
        ai_creative_paths = []

        try:
            # Generate AI creative(s) and mockup
            result_path, ai_creative_paths = await self.generate_ai_mockup_func(
                ai_prompts=ai_prompts,
                location_key=location_key,
                time_of_day=time_of_day,
                finish=finish,
                user_id=user_id,
                company_schemas=user_companies,
            )

            if not result_path:
                raise Exception("AI mockup generation returned None")

            # Prepare metadata
            metadata = {
                "location_key": location_key,
                "location_name": location_name,
                "time_of_day": time_of_day,
                "finish": finish,
                "mode": self.get_mode_name(),
                "num_frames": num_prompts
            }

            # Store AI creatives in history for follow-ups
            store_mockup_history(user_id, ai_creative_paths, metadata)
            self.logger.info(f"[AI_STRATEGY] Stored {len(ai_creative_paths)} AI creative(s) in history")

            return result_path, ai_creative_paths, metadata

        except Exception as e:
            self.logger.error(f"[AI_STRATEGY] Error generating AI mockup: {e}", exc_info=True)
            # Cleanup AI creatives on error
            for creative_path in ai_creative_paths:
                if creative_path and Path(creative_path).exists():
                    try:
                        os.unlink(creative_path)
                    except OSError as cleanup_err:
                        self.logger.debug(f"[AI_STRATEGY] Failed to cleanup AI creative: {cleanup_err}")
            raise

        finally:
            # Memory cleanup
            cleanup_memory(context="mockup_ai", aggressive=False, log_stats=False)
