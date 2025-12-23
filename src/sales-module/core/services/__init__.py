"""
Service layer for Sales-Module.

Services provide business logic and abstractions over data access and external APIs.
"""

from core.services.asset_service import AssetService
from core.services.eligibility_service import (
    EligibilityService,
    LocationEligibilityResult,
    MockupVariant,
    NetworkEligibilityResult,
    check_location_eligibility,
    check_network_eligibility,
)
from core.services.template_service import (
    TemplateService,
    download_template,
    get_template_mapping,
    get_template_service,
    template_exists,
)

__all__ = [
    "AssetService",
    "EligibilityService",
    "LocationEligibilityResult",
    "MockupVariant",
    "NetworkEligibilityResult",
    "TemplateService",
    "check_location_eligibility",
    "check_network_eligibility",
    "download_template",
    "get_template_mapping",
    "get_template_service",
    "template_exists",
]
