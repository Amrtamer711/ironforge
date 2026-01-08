"""
Mockups Module - Public API.

Provides backwards-compatible API for mockup generation.
Uses Strategy pattern internally for better extensibility and testability.

Usage:
    from core.mockups import generate_mockup

    # Upload mode
    result_path, creatives, meta, error = await generate_mockup(
        location_name="Dubai Gateway",
        time_of_day="all",
        side="all",
        user_id="user123",
        user_companies=["backlite_dubai"],
        uploaded_creatives=[Path("creative.jpg")],
        generate_mockup_func=...,
        generate_ai_mockup_func=...
    )

    # AI mode
    result_path, creatives, meta, error = await generate_mockup(
        location_name="Dubai Gateway",
        ai_prompts=["luxury watch ad"],
        user_id="user123",
        user_companies=["backlite_dubai"],
        generate_mockup_func=...,
        generate_ai_mockup_func=...
    )

    # Followup mode (reuse previous creatives)
    result_path, creatives, meta, error = await generate_mockup(
        location_name="Dubai Gateway",
        user_id="user123",  # Must have previous mockup history
        user_companies=["backlite_dubai"],
        generate_mockup_func=...,
        generate_ai_mockup_func=...
    )
"""

from pathlib import Path
from typing import Any, Callable

from .coordinator import MockupCoordinator
from .handler import handle_mockup_generation
from .strategies import AIMockupStrategy, FollowupMockupStrategy, MockupStrategy, UploadMockupStrategy
from .validator import MockupValidator

__all__ = [
    "MockupValidator",
    "MockupStrategy",
    "UploadMockupStrategy",
    "AIMockupStrategy",
    "FollowupMockupStrategy",
    "MockupCoordinator",
    "handle_mockup_generation",
    "generate_mockup",
]


async def generate_mockup(
    location_name: str,
    time_of_day: str = "all",
    side: str = "all",
    user_id: str = None,
    user_companies: list[str] = None,
    uploaded_creatives: list[Path] = None,
    ai_prompts: list[str] = None,
    generate_mockup_func: Callable = None,
    generate_ai_mockup_func: Callable = None,
) -> tuple[Path | None, list[Path], dict[str, Any], str | None]:
    """
    Generate mockup using appropriate strategy (backwards-compatible API).

    Strategy selection (priority):
    1. Upload: If uploaded_creatives provided
    2. AI: If ai_prompts provided
    3. Followup: If user has mockup history
    4. Error: None of the above

    Args:
        location_name: Display name or key of location
        time_of_day: Time filter ("day", "night", "all")
        side: Side filter ("gold", "silver", "all")
        user_id: User identifier (required for followup mode)
        user_companies: List of company schemas user can access
        uploaded_creatives: List of uploaded creative paths (for upload mode)
        ai_prompts: List of AI prompts (for AI mode)
        generate_mockup_func: Function to generate mockup from creatives
        generate_ai_mockup_func: Function to generate AI creative and mockup

    Returns:
        Tuple of (result_path, creative_paths, metadata, error_message)
        - result_path: Path to generated mockup (None if failed)
        - creative_paths: List of creative paths used
        - metadata: Generation metadata dict
        - error_message: Error message if failed, None otherwise

    Example:
        >>> # Upload mode
        >>> result, creatives, meta, error = await generate_mockup(
        ...     location_name="Dubai Gateway",
        ...     user_companies=["backlite_dubai"],
        ...     uploaded_creatives=[Path("creative.jpg")],
        ...     generate_mockup_func=gen_func,
        ...     generate_ai_mockup_func=ai_func
        ... )
        >>> if error:
        ...     print(f"Error: {error}")
        >>> else:
        ...     print(f"Mockup: {result}")

        >>> # AI mode
        >>> result, creatives, meta, error = await generate_mockup(
        ...     location_name="Dubai Gateway",
        ...     user_id="user123",
        ...     user_companies=["backlite_dubai"],
        ...     ai_prompts=["luxury watch ad"],
        ...     generate_mockup_func=gen_func,
        ...     generate_ai_mockup_func=ai_func
        ... )

        >>> # Followup mode
        >>> result, creatives, meta, error = await generate_mockup(
        ...     location_name="Dubai Gateway",
        ...     user_id="user123",
        ...     user_companies=["backlite_dubai"],
        ...     generate_mockup_func=gen_func,
        ...     generate_ai_mockup_func=ai_func
        ... )
    """
    if not user_companies:
        user_companies = []

    if not generate_mockup_func or not generate_ai_mockup_func:
        error_msg = "Both generate_mockup_func and generate_ai_mockup_func are required"
        return None, [], {}, error_msg

    # Create coordinator
    coordinator = MockupCoordinator(
        user_companies=user_companies,
        generate_mockup_func=generate_mockup_func,
        generate_ai_mockup_func=generate_ai_mockup_func
    )

    # Generate mockup
    return await coordinator.generate_mockup(
        location_name=location_name,
        time_of_day=time_of_day,
        side=side,
        user_id=user_id,
        uploaded_creatives=uploaded_creatives,
        ai_prompts=ai_prompts,
    )
