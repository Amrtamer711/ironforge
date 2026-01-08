"""
Mockup Strategy Base Class.

Abstract base class for mockup generation strategies.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MockupStrategy(ABC):
    """
    Abstract base class for mockup generation strategies.

    Defines the interface for different mockup generation modes:
    - Upload: User uploads creative image(s)
    - AI: Generate creative(s) from AI prompt(s)
    - Followup: Reuse previous creative(s) for new location

    Each strategy handles:
    - Input validation
    - Creative preparation
    - Mockup generation
    - History storage
    - Cleanup
    """

    @abstractmethod
    async def execute(
        self,
        location_key: str,
        location_name: str,
        time_of_day: str,
        side: str,
        user_id: str,
        user_companies: list[str],
        **kwargs
    ) -> tuple[Path | None, list[Path], dict[str, Any]]:
        """
        Execute mockup generation strategy.

        Args:
            location_key: Canonical location key
            location_name: Display name of location
            time_of_day: Time of day filter ("day", "night", "all")
            side: Side filter ("gold", "silver", "all")
            user_id: User identifier
            user_companies: List of company schemas user can access
            **kwargs: Strategy-specific parameters

        Returns:
            Tuple of (result_path, creative_paths, metadata)
            - result_path: Path to final mockup image (or None if failed)
            - creative_paths: List of creative image paths used
            - metadata: Dict with generation metadata (location, mode, num_frames, etc.)

        Raises:
            Exception: If mockup generation fails

        Example:
            >>> strategy = UploadMockupStrategy(...)
            >>> result_path, creatives, meta = await strategy.execute(
            ...     location_key="dubai_gateway",
            ...     location_name="Dubai Gateway",
            ...     time_of_day="all",
            ...     side="all",
            ...     user_id="user123",
            ...     user_companies=["backlite_dubai"],
            ...     uploaded_creatives=[Path("creative.jpg")]
            ... )
        """
        pass

    @abstractmethod
    def can_handle(self, **kwargs) -> bool:
        """
        Check if this strategy can handle the request.

        Args:
            **kwargs: Request parameters

        Returns:
            True if strategy can handle the request

        Example:
            >>> upload_strategy.can_handle(uploaded_creatives=[Path("file.jpg")])
            True
            >>> upload_strategy.can_handle(ai_prompts=["generate ad"])
            False
        """
        pass

    @abstractmethod
    def get_mode_name(self) -> str:
        """
        Get strategy mode name for logging/metadata.

        Returns:
            Mode name string ("uploaded", "ai_generated", "followup")
        """
        pass
