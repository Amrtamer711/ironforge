"""
Eligibility - Schemas and service logic.

Eligibility determines which locations/networks can appear in specific services.
"""

from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.eligibility")


# =============================================================================
# SCHEMAS
# =============================================================================


class ServiceEligibility(BaseModel):
    """Defines which services a location/network can appear in."""

    proposal_generator: bool = False
    mockup_generator: bool = False
    availability_calendar: bool = False


class EligibilityReason(BaseModel):
    """Detailed eligibility information for a specific service."""

    service: str = Field(..., description="Service name")
    eligible: bool = Field(..., description="Whether eligible for this service")
    missing_fields: list[str] = Field(default_factory=list, description="Required fields that are missing")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings")


class EligibilityCheck(BaseModel):
    """Full eligibility check result."""

    item_type: str = Field(..., description="'location' or 'network'")
    item_id: int
    company: str
    name: str = Field(..., description="Display name of the item")

    # Overall eligibility per service
    service_eligibility: ServiceEligibility

    # Detailed reasons per service
    details: list[EligibilityReason] = Field(default_factory=list)

    # For networks: count of eligible/total locations
    eligible_location_count: int | None = None
    total_location_count: int | None = None


class BulkEligibilityItem(BaseModel):
    """Item for bulk eligibility check."""

    type: str = Field(..., description="'location' or 'network'")
    company: str
    id: int


# Service requirements configuration
SERVICE_REQUIREMENTS = {
    "proposal_generator": {
        "location": {
            "required_fields": ["display_name", "display_type"],
            "required_relations": ["rate_card"],  # Must have active rate card
            "description": "Requires display name, type, and active rate card",
        },
        "network": {
            "required_fields": ["name"],
            "min_eligible_locations": 1,
            "description": "Requires name and at least 1 location with rate card",
        },
    },
    "mockup_generator": {
        "location": {
            "required_fields": ["display_name", "template_path"],
            "required_relations": ["mockup_frame"],  # Must have mockup frame
            "description": "Requires display name, template, and mockup frame",
        },
        "network": {
            "eligible": False,  # Networks don't have mockups
            "description": "Networks are not eligible for mockup generator",
        },
    },
    "availability_calendar": {
        "location": {
            "required_fields": ["display_name"],
            "description": "Requires display name",
        },
        "network": {
            "required_fields": ["name"],
            "min_eligible_locations": 1,
            "description": "Requires name and at least 1 active location",
        },
    },
}


# =============================================================================
# SERVICE
# =============================================================================


class EligibilityService:
    """Business logic for eligibility operations."""

    def get_requirements(self, service: str) -> dict | None:
        """Get requirements for a service."""
        return SERVICE_REQUIREMENTS.get(service)

    def check_location_eligibility(
        self,
        company: str,
        location_id: int,
        service: str | None = None,
    ) -> EligibilityCheck | None:
        """Check eligibility for a location."""
        result = db.check_location_eligibility(location_id, [company])

        if result.get("error"):
            return None

        # Convert to EligibilityCheck model
        eligibility = ServiceEligibility(
            proposal_generator=result["service_eligibility"].get("proposal_generator", False),
            mockup_generator=result["service_eligibility"].get("mockup_generator", False),
            availability_calendar=result["service_eligibility"].get("availability_calendar", False),
        )

        details = [
            EligibilityReason(
                service=d["service"],
                eligible=d["eligible"],
                missing_fields=d.get("missing_fields", []),
                warnings=d.get("warnings", []),
            )
            for d in result.get("details", [])
        ]

        # Filter by specific service if requested
        if service:
            details = [d for d in details if d.service == service]

        return EligibilityCheck(
            item_type="location",
            item_id=location_id,
            company=company,
            name=result.get("name", ""),
            service_eligibility=eligibility,
            details=details,
        )

    def check_network_eligibility(
        self,
        company: str,
        network_id: int,
        service: str | None = None,
    ) -> EligibilityCheck | None:
        """Check eligibility for a network."""
        result = db.check_network_eligibility(network_id, [company])

        if result.get("error"):
            return None

        eligibility = ServiceEligibility(
            proposal_generator=result["service_eligibility"].get("proposal_generator", False),
            mockup_generator=result["service_eligibility"].get("mockup_generator", False),
            availability_calendar=result["service_eligibility"].get("availability_calendar", False),
        )

        details = [
            EligibilityReason(
                service=d["service"],
                eligible=d["eligible"],
                missing_fields=d.get("missing_fields", []),
                warnings=d.get("warnings", []),
            )
            for d in result.get("details", [])
        ]

        # Filter by specific service if requested
        if service:
            details = [d for d in details if d.service == service]

        return EligibilityCheck(
            item_type="network",
            item_id=network_id,
            company=company,
            name=result.get("name", ""),
            service_eligibility=eligibility,
            details=details,
            eligible_location_count=result.get("eligible_location_count"),
            total_location_count=result.get("total_location_count"),
        )

    def bulk_check_eligibility(
        self,
        items: list[BulkEligibilityItem],
        service: str,
    ) -> list[EligibilityCheck]:
        """Bulk check eligibility for multiple items."""
        results = []

        for item in items:
            if item.type == "location":
                result = self.check_location_eligibility(
                    company=item.company,
                    location_id=item.id,
                    service=service,
                )
            elif item.type == "network":
                result = self.check_network_eligibility(
                    company=item.company,
                    network_id=item.id,
                    service=service,
                )
            else:
                continue

            if result:
                results.append(result)

        return results

    def get_eligible_locations(
        self,
        service: str,
        companies: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get all locations eligible for a service."""
        return db.get_eligible_locations(service, companies, limit, offset)

    def get_eligible_networks(
        self,
        service: str,
        companies: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get networks eligible for a service."""
        return db.get_eligible_networks(service, companies, limit, offset)
