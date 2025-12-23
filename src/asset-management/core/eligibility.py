"""
Eligibility - Schemas and service logic.

Eligibility determines which locations/networks can appear in specific services.

Proposal and mockup eligibility is now determined by calling Sales-Module's
internal eligibility endpoints. This is because the rate_cards and mockup_frames
tables are in Sales-Module's database, not Asset-Management's.
"""

from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db
from integrations.sales_module import SalesModuleClient, get_sales_module_client

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
    """
    Business logic for eligibility operations.

    Uses Sales-Module's internal API for proposal and mockup eligibility,
    since rate_cards and mockup_frames are stored in Sales-Module's database.
    """

    def __init__(self, sales_module_client: SalesModuleClient | None = None):
        self.sales_client = sales_module_client or get_sales_module_client()

    def get_requirements(self, service: str) -> dict | None:
        """Get requirements for a service."""
        return SERVICE_REQUIREMENTS.get(service)

    async def check_location_eligibility(
        self,
        company: str,
        location_id: int,
        service: str | None = None,
    ) -> EligibilityCheck | None:
        """
        Check eligibility for a location.

        Calls Sales-Module for proposal/mockup eligibility since those require
        data from Sales-Module's database (rate_cards, mockup_frames).
        """
        # Get location data from local database
        location = db.get_location(location_id, [company])
        if not location:
            return None

        location_key = location.get("location_key", "")
        display_name = location.get("display_name", "")

        # Call Sales-Module for proposal/mockup eligibility
        sales_result = await self.sales_client.check_location_eligibility(
            location_key, [company]
        )

        details = []

        # Proposal generator eligibility (from Sales-Module)
        if sales_result:
            proposal_eligible = sales_result.proposal_eligible
            proposal_missing = sales_result.proposal_missing_fields.copy()
            if not sales_result.template_exists:
                proposal_missing.append("template")
        else:
            proposal_eligible = False
            proposal_missing = ["sales_module_unavailable"]

        details.append(EligibilityReason(
            service="proposal_generator",
            eligible=proposal_eligible,
            missing_fields=proposal_missing,
            warnings=[],
        ))

        # Mockup generator eligibility (from Sales-Module)
        if sales_result:
            mockup_eligible = sales_result.mockup_eligible
            mockup_missing = [] if mockup_eligible else ["mockup_frame"]
        else:
            mockup_eligible = False
            mockup_missing = ["sales_module_unavailable"]

        details.append(EligibilityReason(
            service="mockup_generator",
            eligible=mockup_eligible,
            missing_fields=mockup_missing,
            warnings=[],
        ))

        # Availability calendar eligibility (local check)
        calendar_missing = []
        if not display_name:
            calendar_missing.append("display_name")

        details.append(EligibilityReason(
            service="availability_calendar",
            eligible=len(calendar_missing) == 0,
            missing_fields=calendar_missing,
            warnings=[],
        ))

        # Filter by specific service if requested
        if service:
            details = [d for d in details if d.service == service]

        eligibility = ServiceEligibility(
            proposal_generator=details[0].eligible if len(details) > 0 else False,
            mockup_generator=details[1].eligible if len(details) > 1 else False,
            availability_calendar=details[2].eligible if len(details) > 2 else False,
        )

        return EligibilityCheck(
            item_type="location",
            item_id=location_id,
            company=company,
            name=display_name,
            service_eligibility=eligibility,
            details=details,
        )

    async def check_network_eligibility(
        self,
        company: str,
        network_id: int,
        service: str | None = None,
    ) -> EligibilityCheck | None:
        """
        Check eligibility for a network.

        Calls Sales-Module for proposal/mockup eligibility.
        """
        # Get network data from local database
        network = db.get_network(network_id, [company])
        if not network:
            return None

        network_key = network.get("network_key", "")
        network_name = network.get("name", "")

        # Call Sales-Module for proposal/mockup eligibility
        sales_result = await self.sales_client.check_network_eligibility(
            network_key, [company]
        )

        details = []

        # Proposal generator eligibility (from Sales-Module)
        if sales_result:
            proposal_eligible = sales_result.proposal_eligible
            proposal_missing = [] if proposal_eligible else ["template"]
        else:
            proposal_eligible = False
            proposal_missing = ["sales_module_unavailable"]

        details.append(EligibilityReason(
            service="proposal_generator",
            eligible=proposal_eligible,
            missing_fields=proposal_missing,
            warnings=[],
        ))

        # Mockup generator eligibility (from Sales-Module)
        if sales_result:
            mockup_eligible = sales_result.mockup_eligible
            mockup_missing = [] if mockup_eligible else ["mockup_frame"]
        else:
            mockup_eligible = False
            mockup_missing = ["sales_module_unavailable"]

        details.append(EligibilityReason(
            service="mockup_generator",
            eligible=mockup_eligible,
            missing_fields=mockup_missing,
            warnings=[],
        ))

        # Availability calendar eligibility (local check)
        calendar_missing = []
        if not network_name:
            calendar_missing.append("name")

        details.append(EligibilityReason(
            service="availability_calendar",
            eligible=len(calendar_missing) == 0,
            missing_fields=calendar_missing,
            warnings=[],
        ))

        # Filter by specific service if requested
        if service:
            details = [d for d in details if d.service == service]

        eligibility = ServiceEligibility(
            proposal_generator=details[0].eligible if len(details) > 0 else False,
            mockup_generator=details[1].eligible if len(details) > 1 else False,
            availability_calendar=details[2].eligible if len(details) > 2 else False,
        )

        # Get location counts (local database)
        network_locations = db.list_locations([company], network_id=network_id)
        total_locations = len(network_locations)
        eligible_locations = 0  # Would need async bulk check, simplified for now

        return EligibilityCheck(
            item_type="network",
            item_id=network_id,
            company=company,
            name=network_name,
            service_eligibility=eligibility,
            details=details,
            eligible_location_count=eligible_locations,
            total_location_count=total_locations,
        )

    async def bulk_check_eligibility(
        self,
        items: list[BulkEligibilityItem],
        service: str,
    ) -> list[EligibilityCheck]:
        """Bulk check eligibility for multiple items."""
        results = []

        for item in items:
            if item.type == "location":
                result = await self.check_location_eligibility(
                    company=item.company,
                    location_id=item.id,
                    service=service,
                )
            elif item.type == "network":
                result = await self.check_network_eligibility(
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
