"""
Mockup Coordinator.

Orchestrates mockup generation using Strategy pattern.
"""

import os
from pathlib import Path
from typing import Any, Callable

import config
from core.services import AssetService
from core.utils import match_location_key

from .strategies.ai import AIMockupStrategy
from .strategies.followup import FollowupMockupStrategy
from .strategies.upload import UploadMockupStrategy
from .validator import MockupValidator


class MockupCoordinator:
    """
    Coordinates mockup generation workflow.

    Responsibilities:
    - Validate location access and configuration
    - Select appropriate generation strategy
    - Execute strategy and handle results
    - Provide unified interface for all mockup types

    Uses Strategy Pattern:
    - UploadMockupStrategy: User uploads image(s)
    - AIMockupStrategy: Generate from AI prompt(s)
    - FollowupMockupStrategy: Reuse previous creative(s)
    """

    def __init__(
        self,
        user_companies: list[str],
        generate_mockup_func: Callable,
        generate_ai_mockup_func: Callable
    ):
        """
        Initialize coordinator with dependencies.

        Args:
            user_companies: List of company schemas user can access
            generate_mockup_func: Function to generate mockup from creatives
            generate_ai_mockup_func: Function to generate AI creative and mockup
        """
        self.user_companies = user_companies
        self.generate_mockup_func = generate_mockup_func
        self.generate_ai_mockup_func = generate_ai_mockup_func
        self.logger = config.logger

        # Initialize components (lazy-load locations)
        self.asset_service = AssetService()
        self._available_locations: list[dict[str, Any]] | None = None
        self.validator = MockupValidator(user_companies)

        # Initialize strategies
        self.strategies = [
            UploadMockupStrategy(self.validator, generate_mockup_func),
            AIMockupStrategy(self.validator, generate_ai_mockup_func),
            FollowupMockupStrategy(self.validator, generate_mockup_func),
        ]

    async def _get_available_locations(self) -> list[dict[str, Any]]:
        """Lazy-load available locations (async)."""
        if self._available_locations is None:
            self._available_locations = await self.asset_service.get_locations_for_companies(
                self.user_companies
            )
        return self._available_locations

    async def resolve_location(
        self,
        location_name: str
    ) -> tuple[str | None, str | None]:
        """
        Resolve location name to canonical key.

        Args:
            location_name: Display name or key of location

        Returns:
            Tuple of (location_key, error_message)
            - location_key: Canonical key if found, None otherwise
            - error_message: Error message if not found, None otherwise
        """
        self.logger.info(f"[COORDINATOR] Resolving location '{location_name}'")

        available_locations = await self._get_available_locations()
        location_key = match_location_key(location_name, available_locations)

        if not location_key:
            error_msg = (
                f"Location '{location_name}' not found in accessible companies. "
                f"Available companies: {self.user_companies}"
            )
            return None, error_msg

        self.logger.info(f"[COORDINATOR] Matched '{location_name}' to '{location_key}'")
        return location_key, None

    async def validate_location_configuration(
        self,
        location_key: str
    ) -> tuple[bool, str | None]:
        """
        Validate location has mockup photos configured.

        Args:
            location_key: Canonical location key

        Returns:
            Tuple of (is_valid, error_message)
        """
        return await self.validator.validate_location_has_mockups(location_key)

    async def generate_mockup(
        self,
        location_name: str,
        time_of_day: str = "all",
        finish: str = "all",
        user_id: str = None,
        uploaded_creatives: list[Path] = None,
        ai_prompts: list[str] = None,
    ) -> tuple[Path | None, list[Path], dict[str, Any], str | None]:
        """
        Generate mockup using appropriate strategy.

        Strategy priority:
        1. Upload: If uploaded_creatives provided
        2. AI: If ai_prompts provided
        3. Followup: If user has mockup history
        4. Error: None of the above

        Args:
            location_name: Display name or key of location
            time_of_day: Time filter ("day", "night", "all")
            finish: Finish filter ("matte", "gloss", "all")
            user_id: User identifier
            uploaded_creatives: List of uploaded creative paths
            ai_prompts: List of AI prompts

        Returns:
            Tuple of (result_path, creative_paths, metadata, error_message)
            - result_path: Path to generated mockup (None if failed)
            - creative_paths: List of creative paths used
            - metadata: Generation metadata dict
            - error_message: Error message if failed, None otherwise

        Example:
            >>> coordinator = MockupCoordinator(
            ...     user_companies=["backlite_dubai"],
            ...     generate_mockup_func=...,
            ...     generate_ai_mockup_func=...
            ... )
            >>> result, creatives, meta, error = await coordinator.generate_mockup(
            ...     location_name="Dubai Gateway",
            ...     time_of_day="all",
            ...     finish="all",
            ...     user_id="user123",
            ...     uploaded_creatives=[Path("creative.jpg")]
            ... )
        """
        # Normalize parameters
        time_of_day = (time_of_day or "all").strip().lower()
        finish = (finish or "all").strip().lower()

        self.logger.info(f"[COORDINATOR] Generating mockup for {location_name}")
        self.logger.info(f"[COORDINATOR] Time: {time_of_day}, Finish: {finish}")

        # Resolve location (async)
        location_key, error_msg = await self.resolve_location(location_name)
        if not location_key:
            return None, [], {}, error_msg

        # Validate location configuration
        is_valid, error_msg = await self.validate_location_configuration(location_key)
        if not is_valid:
            mockup_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:3000") + "/mockup"
            error_msg = (
                f"{error_msg}\n\n"
                f"Ask an admin to set up mockup frames at {mockup_url}"
            )
            return None, [], {}, error_msg

        # Select strategy
        request_params = {
            "uploaded_creatives": uploaded_creatives or [],
            "ai_prompts": ai_prompts or [],
            "user_id": user_id
        }

        selected_strategy = None
        for strategy in self.strategies:
            if strategy.can_handle(**request_params):
                selected_strategy = strategy
                break

        if not selected_strategy:
            error_msg = (
                "No input provided. Please either:\n"
                "1️⃣ Upload an image\n"
                "2️⃣ Provide an AI prompt\n"
                "3️⃣ Generate a mockup first for follow-up requests"
            )
            return None, [], {}, error_msg

        self.logger.info(f"[COORDINATOR] Using strategy: {selected_strategy.get_mode_name()}")

        # Execute strategy
        try:
            result_path, creative_paths, metadata = await selected_strategy.execute(
                location_key=location_key,
                location_name=location_name,
                time_of_day=time_of_day,
                finish=finish,
                user_id=user_id,
                user_companies=self.user_companies,
                **request_params
            )

            self.logger.info(f"[COORDINATOR] Mockup generated successfully")
            return result_path, creative_paths, metadata, None

        except Exception as e:
            self.logger.error(f"[COORDINATOR] Mockup generation failed: {e}", exc_info=True)
            error_msg = f"Failed to generate mockup: {str(e)}"
            return None, [], {}, error_msg
