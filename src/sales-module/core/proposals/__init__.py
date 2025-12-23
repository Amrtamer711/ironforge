"""
Proposals Module - Public API.

Provides backwards-compatible API for proposal generation.
Uses class-based architecture internally for better testability and maintainability.

Usage:
    from core.proposals import process_proposals, process_combined_package

    # Separate proposals
    result = await process_proposals(
        proposals_data,
        submitted_by="user@example.com",
        client_name="ABC Corp",
        user_companies=["backlite_dubai"]
    )

    # Combined package
    result = await process_combined_package(
        proposals_data,
        combined_net_rate="50000",
        submitted_by="user@example.com",
        client_name="ABC Corp",
        user_companies=["backlite_dubai"]
    )
"""

from typing import Any

from .intro_outro import IntroOutroHandler
from .processor import ProposalProcessor
from .renderer import ProposalRenderer
from .validator import ProposalValidator

__all__ = [
    "ProposalValidator",
    "ProposalRenderer",
    "IntroOutroHandler",
    "ProposalProcessor",
    "process_proposals",
    "process_combined_package",
]


async def process_proposals(
    proposals_data: list[dict[str, Any]],
    package_type: str = "separate",
    combined_net_rate: str = None,
    submitted_by: str = "",
    client_name: str = "",
    payment_terms: str = "100% upfront",
    currency: str = None,
    user_companies: list[str] = None,
) -> dict[str, Any]:
    """
    Process proposal generation (backwards-compatible API).

    Args:
        proposals_data: List of proposal dicts with location, durations, rates, etc.
        package_type: "separate" or "combined"
        combined_net_rate: Net rate for combined packages
        submitted_by: User who submitted
        client_name: Client name
        payment_terms: Payment terms text
        currency: Target currency code (e.g., 'USD', 'EUR'). If None or 'AED', uses AED.
        user_companies: List of company schemas user has access to

    Returns:
        Dict with success status and file paths

    Example:
        >>> result = await process_proposals(
        ...     [{"location": "dubai_gateway", "durations": [4, 8], "net_rates": ["10000", "18000"]}],
        ...     submitted_by="user@example.com",
        ...     client_name="ABC Corp",
        ...     user_companies=["backlite_dubai"]
        ... )
        >>> if result["success"]:
        ...     print(f"PDF: {result['pdf_path']}")
    """
    if not proposals_data:
        return {"success": False, "error": "No proposals provided"}

    if not user_companies:
        user_companies = []

    # Create module instances
    validator = ProposalValidator(user_companies)
    renderer = ProposalRenderer()
    intro_outro = IntroOutroHandler(validator.available_locations)
    processor = ProposalProcessor(validator, renderer, intro_outro)

    # Route to appropriate processor method
    if package_type == "combined" and len(proposals_data) > 1:
        return await processor.process_combined(
            proposals_data,
            combined_net_rate,
            submitted_by,
            client_name,
            payment_terms,
            currency
        )
    else:
        return await processor.process_separate(
            proposals_data,
            submitted_by,
            client_name,
            currency
        )


async def process_combined_package(
    proposals_data: list[dict[str, Any]],
    combined_net_rate: str,
    submitted_by: str = "",
    client_name: str = "",
    payment_terms: str = "100% upfront",
    currency: str = None,
    user_companies: list[str] = None,
    available_locations: list[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Process combined package proposal (backwards-compatible API).

    Args:
        proposals_data: List of proposal dicts
        combined_net_rate: Combined net rate for package
        submitted_by: User who submitted
        client_name: Client name
        payment_terms: Payment terms text
        currency: Currency code
        user_companies: List of company schemas user has access to
        available_locations: Optional pre-fetched locations (for optimization)

    Returns:
        Dict with success status and file paths

    Example:
        >>> result = await process_combined_package(
        ...     proposals_data,
        ...     "50000",
        ...     submitted_by="user@example.com",
        ...     client_name="ABC Corp",
        ...     payment_terms="100% upfront",
        ...     user_companies=["backlite_dubai"]
        ... )
    """
    if not user_companies:
        user_companies = []

    # Create module instances
    validator = ProposalValidator(user_companies)
    renderer = ProposalRenderer()
    intro_outro = IntroOutroHandler(validator.available_locations)
    processor = ProposalProcessor(validator, renderer, intro_outro)

    return await processor.process_combined(
        proposals_data,
        combined_net_rate,
        submitted_by,
        client_name,
        payment_terms,
        currency
    )
