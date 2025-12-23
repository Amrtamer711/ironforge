"""
Eligibility Service - Checks eligibility for proposals and mockups.

Provides internal API for Asset-Management to query eligibility status
of locations for different services (proposal generator, mockup generator).
"""

from typing import Any

from pydantic import BaseModel, Field

from core.services.mockup_frame_service import MockupFrameService
from core.services.template_service import TemplateService
from db.database import db

# Lazy import to avoid circular dependency
_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        import config
        _logger = config.get_logger("core.services.eligibility_service")
    return _logger


# =============================================================================
# SCHEMAS
# =============================================================================


class MockupVariant(BaseModel):
    """A single mockup variant (time_of_day + finish combo)."""

    time_of_day: str = Field(..., description="'day' or 'night'")
    finish: str = Field(..., description="'gold', 'silver', or 'black'")


class LocationEligibilityResult(BaseModel):
    """Result of checking eligibility for a location."""

    location_key: str
    company: str | None = None

    # Proposal eligibility
    proposal_eligible: bool = False
    proposal_missing_fields: list[str] = Field(default_factory=list)
    template_exists: bool = False

    # Mockup eligibility
    mockup_eligible: bool = False
    mockup_variants: list[MockupVariant] = Field(default_factory=list)
    mockup_frame_count: int = 0


class NetworkEligibilityResult(BaseModel):
    """Result of checking eligibility for a network."""

    network_key: str
    network_name: str | None = None
    company: str | None = None

    # Proposal eligibility
    proposal_eligible: bool = False
    template_exists: bool = False

    # Mockup eligibility
    mockup_eligible: bool = False
    mockup_frame_count: int = 0


# =============================================================================
# REQUIRED FIELDS FOR PROPOSAL ELIGIBILITY
# =============================================================================

# Required fields for a location to be eligible for proposals
PROPOSAL_REQUIRED_FIELDS = [
    "display_name",
    "display_type",
    "series",
    "height",
    "width",
    "number_of_faces",
]

# Additional fields required for digital displays
DIGITAL_REQUIRED_FIELDS = [
    "spot_duration",
    "loop_duration",
    "sov_percent",
    "upload_fee",
]


# =============================================================================
# SERVICE
# =============================================================================


class EligibilityService:
    """
    Service for checking location/network eligibility.

    This service is called by Asset-Management to determine which
    locations/networks are eligible for proposal and mockup generation.

    Usage:
        service = EligibilityService()
        result = await service.check_location_eligibility("dubai_mall", ["backlite_dubai"])
    """

    def __init__(
        self,
        company_schemas: list[str],
        template_service: TemplateService | None = None,
    ):
        if not company_schemas:
            raise ValueError("At least one company schema must be provided")

        self.logger = _get_logger()
        self.company_schemas = company_schemas
        self.template_service = template_service or TemplateService(companies=company_schemas)
        self.mockup_frame_service = MockupFrameService(companies=company_schemas)

    async def check_location_eligibility(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> LocationEligibilityResult:
        """
        Check eligibility for a location.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")
            company_schemas: Company schemas to search for the location

        Returns:
            LocationEligibilityResult with eligibility status and details
        """
        self.logger.info(f"[ELIGIBILITY] Checking location: {location_key}")

        result = LocationEligibilityResult(location_key=location_key)

        # Find location data
        location_data = self._get_location_data(location_key, company_schemas)
        if not location_data:
            self.logger.warning(f"[ELIGIBILITY] Location not found: {location_key}")
            return result

        result.company = location_data.get("_company_schema")

        # Check proposal eligibility
        missing_fields = self._check_proposal_fields(location_data)
        result.proposal_missing_fields = missing_fields

        # Check template exists
        template_exists, _ = await self.template_service.exists(location_key)
        result.template_exists = template_exists

        # Location is proposal eligible if all fields present AND template exists
        result.proposal_eligible = (
            len(missing_fields) == 0 and template_exists
        )

        # Check mockup eligibility (via Asset-Management)
        mockup_variations = await self.mockup_frame_service.list_variations(location_key)
        result.mockup_variants = self._build_mockup_variants(mockup_variations)
        result.mockup_frame_count = len(result.mockup_variants)
        result.mockup_eligible = result.mockup_frame_count > 0

        self.logger.info(
            f"[ELIGIBILITY] Location {location_key}: "
            f"proposal={result.proposal_eligible}, mockup={result.mockup_eligible}"
        )

        return result

    async def check_network_eligibility(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> NetworkEligibilityResult:
        """
        Check eligibility for a network.

        Args:
            network_key: Network identifier
            company_schemas: Company schemas to search

        Returns:
            NetworkEligibilityResult with eligibility status
        """
        self.logger.info(f"[ELIGIBILITY] Checking network: {network_key}")

        result = NetworkEligibilityResult(network_key=network_key)

        # Find network data
        network_data = self._get_network_data(network_key, company_schemas)
        if not network_data:
            self.logger.warning(f"[ELIGIBILITY] Network not found: {network_key}")
            return result

        result.network_name = network_data.get("name")
        result.company = network_data.get("_company_schema")

        # For networks, proposal eligibility just requires:
        # - Network name exists
        # - Template exists for the network
        template_exists, _ = await self.template_service.exists(network_key)
        result.template_exists = template_exists
        result.proposal_eligible = (
            bool(result.network_name) and template_exists
        )

        # For mockup eligibility, check if any mockup frames exist (via Asset-Management)
        mockup_variations = await self.mockup_frame_service.list_variations(network_key)
        result.mockup_frame_count = sum(
            len(finishes) for finishes in mockup_variations.values()
        )
        result.mockup_eligible = result.mockup_frame_count > 0

        self.logger.info(
            f"[ELIGIBILITY] Network {network_key}: "
            f"proposal={result.proposal_eligible}, mockup={result.mockup_eligible}"
        )

        return result

    async def check_template_exists(self, location_key: str) -> bool:
        """
        Check if template exists in storage for a location.

        Args:
            location_key: Location identifier

        Returns:
            True if template exists
        """
        exists, _ = await self.template_service.exists(location_key)
        return exists

    async def get_mockup_variants(
        self,
        location_key: str,
    ) -> list[MockupVariant]:
        """
        Get available mockup variants for a location.

        Args:
            location_key: Location identifier

        Returns:
            List of available MockupVariant combinations
        """
        mockup_variations = await self.mockup_frame_service.list_variations(location_key)
        return self._build_mockup_variants(mockup_variations)

    def _get_location_data(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get location data from database."""
        normalized_key = location_key.lower().strip()

        for schema in company_schemas:
            try:
                # Use the database to get location
                client = db._backend._get_client()
                response = (
                    client.schema(schema)
                    .table("locations")
                    .select("*")
                    .eq("location_key", normalized_key)
                    .limit(1)
                    .execute()
                )

                if response.data:
                    data = response.data[0]
                    data["_company_schema"] = schema
                    return data
            except Exception as e:
                self.logger.debug(f"[ELIGIBILITY] Error querying {schema}: {e}")
                continue

        return None

    def _get_network_data(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get network data from database."""
        normalized_key = network_key.lower().strip()

        for schema in company_schemas:
            try:
                client = db._backend._get_client()
                response = (
                    client.schema(schema)
                    .table("networks")
                    .select("*")
                    .eq("network_key", normalized_key)
                    .limit(1)
                    .execute()
                )

                if response.data:
                    data = response.data[0]
                    data["_company_schema"] = schema
                    return data
            except Exception as e:
                self.logger.debug(f"[ELIGIBILITY] Error querying {schema}: {e}")
                continue

        return None

    def _check_proposal_fields(self, location_data: dict[str, Any]) -> list[str]:
        """
        Check which required fields are missing for proposal eligibility.

        Args:
            location_data: Location data dict

        Returns:
            List of missing field names
        """
        missing = []

        # Check base required fields
        for field in PROPOSAL_REQUIRED_FIELDS:
            value = location_data.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)

        # Check digital-specific fields
        display_type = location_data.get("display_type", "").lower()
        if display_type == "digital":
            for field in DIGITAL_REQUIRED_FIELDS:
                value = location_data.get(field)
                if value is None:
                    missing.append(field)

        return missing

    def _build_mockup_variants(
        self,
        variations: dict[str, list[str]],
    ) -> list[MockupVariant]:
        """
        Build list of MockupVariant from variations dict.

        Args:
            variations: Dict of time_of_day -> list of finishes

        Returns:
            List of MockupVariant
        """
        variants = []
        for time_of_day, finishes in variations.items():
            for finish in finishes:
                variants.append(MockupVariant(time_of_day=time_of_day, finish=finish))
        return variants


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def check_location_eligibility(
    location_key: str,
    company_schemas: list[str],
) -> LocationEligibilityResult:
    """Check eligibility for a location."""
    service = EligibilityService(company_schemas=company_schemas)
    return await service.check_location_eligibility(location_key, company_schemas)


async def check_network_eligibility(
    network_key: str,
    company_schemas: list[str],
) -> NetworkEligibilityResult:
    """Check eligibility for a network."""
    service = EligibilityService(company_schemas=company_schemas)
    return await service.check_network_eligibility(network_key, company_schemas)
