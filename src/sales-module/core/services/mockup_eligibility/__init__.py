"""
Mockup Eligibility Service - Mode-specific eligibility filtering for mockup operations.

Provides eligibility checking for:
- Setup mode: Networks only (no packages)
- Generate mode (Form-based): Networks + Packages with frames
- Generate mode (LLM): Post-parse validation with user-friendly feedback

Usage:
    from core.services.mockup_eligibility import (
        SetupEligibilityService,
        GenerateFormEligibilityService,
        GenerateLLMEligibilityService,
    )

    # Setup mode - get networks only
    setup_service = SetupEligibilityService(user_companies)
    locations = await setup_service.get_eligible_locations()

    # Generate mode - get networks + packages with frames
    generate_service = GenerateFormEligibilityService(user_companies)
    locations = await generate_service.get_eligible_locations()
    templates = await generate_service.get_templates_for_location("dubai_gateway")

    # LLM mode - check after parsing user request
    llm_service = GenerateLLMEligibilityService(user_companies)
    result = await llm_service.check_eligibility("dubai_gateway")
    if not result.eligible:
        # Return result.reason to user in chat
        pass
"""

from .base import (
    EligibilityMode,
    EligibilityResult,
    LocationOption,
    BaseEligibilityService,
)
from .setup import SetupEligibilityService
from .generate_form import GenerateFormEligibilityService
from .generate_llm import GenerateLLMEligibilityService

__all__ = [
    "EligibilityMode",
    "EligibilityResult",
    "LocationOption",
    "BaseEligibilityService",
    "SetupEligibilityService",
    "GenerateFormEligibilityService",
    "GenerateLLMEligibilityService",
]
