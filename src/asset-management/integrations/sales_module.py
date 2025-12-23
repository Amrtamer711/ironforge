"""
Sales Module Client.

Client for calling Sales-Module internal endpoints for eligibility checks.
Uses inter-service JWT authentication via crm_security.ServiceAuthClient.
"""

from typing import Any

import httpx
from pydantic import BaseModel, Field

import config
from crm_security import ServiceAuthClient

logger = config.get_logger("integrations.sales_module")


# =============================================================================
# RESPONSE MODELS (match Sales-Module's eligibility_service.py)
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
# CLIENT
# =============================================================================


class SalesModuleClient:
    """
    Client for calling Sales-Module internal eligibility endpoints.

    Uses inter-service JWT authentication via ServiceAuthClient.

    Usage:
        client = SalesModuleClient()
        result = await client.check_location_eligibility("dubai_mall", ["backlite_dubai"])
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the Sales-Module client.

        Args:
            base_url: Sales-Module base URL (defaults to config.SALES_MODULE_URL)
            timeout: Request timeout in seconds
        """
        self.base_url = (base_url or config.SALES_MODULE_URL).rstrip("/")
        self.timeout = timeout
        self.auth_client = ServiceAuthClient(config.SERVICE_NAME)
        logger.info(f"[SALES_MODULE_CLIENT] Initialized with base_url={self.base_url}")

    def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers for inter-service requests."""
        return self.auth_client.get_auth_headers()

    async def check_location_eligibility(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> LocationEligibilityResult | None:
        """
        Check eligibility for a location.

        Args:
            location_key: Location identifier
            company_schemas: Company schemas to search

        Returns:
            LocationEligibilityResult or None if request failed
        """
        url = f"{self.base_url}/internal/eligibility/location/{location_key}"
        params = {"company_schemas": company_schemas}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return LocationEligibilityResult(**response.json())
                else:
                    logger.warning(
                        f"[SALES_MODULE_CLIENT] Location eligibility check failed: "
                        f"{response.status_code} - {response.text}"
                    )
                    return None

        except httpx.RequestError as e:
            logger.error(f"[SALES_MODULE_CLIENT] Request error: {e}")
            return None

    async def check_network_eligibility(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> NetworkEligibilityResult | None:
        """
        Check eligibility for a network.

        Args:
            network_key: Network identifier
            company_schemas: Company schemas to search

        Returns:
            NetworkEligibilityResult or None if request failed
        """
        url = f"{self.base_url}/internal/eligibility/network/{network_key}"
        params = {"company_schemas": company_schemas}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return NetworkEligibilityResult(**response.json())
                else:
                    logger.warning(
                        f"[SALES_MODULE_CLIENT] Network eligibility check failed: "
                        f"{response.status_code} - {response.text}"
                    )
                    return None

        except httpx.RequestError as e:
            logger.error(f"[SALES_MODULE_CLIENT] Request error: {e}")
            return None

    async def check_template_exists(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> bool:
        """
        Check if template exists for a location.

        Args:
            location_key: Location identifier
            company_schemas: Company schemas to search

        Returns:
            True if template exists
        """
        url = f"{self.base_url}/internal/eligibility/template/{location_key}"
        params = {"company_schemas": company_schemas}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("template_exists", False)
                else:
                    logger.warning(
                        f"[SALES_MODULE_CLIENT] Template check failed: "
                        f"{response.status_code}"
                    )
                    return False

        except httpx.RequestError as e:
            logger.error(f"[SALES_MODULE_CLIENT] Request error: {e}")
            return False

    async def get_mockup_variants(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> list[MockupVariant]:
        """
        Get available mockup variants for a location.

        Args:
            location_key: Location identifier
            company_schemas: Company schemas to search

        Returns:
            List of available MockupVariant
        """
        url = f"{self.base_url}/internal/eligibility/mockup-variants/{location_key}"
        params = {"company_schemas": company_schemas}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    return [MockupVariant(**v) for v in data]
                else:
                    logger.warning(
                        f"[SALES_MODULE_CLIENT] Mockup variants check failed: "
                        f"{response.status_code}"
                    )
                    return []

        except httpx.RequestError as e:
            logger.error(f"[SALES_MODULE_CLIENT] Request error: {e}")
            return []

    async def bulk_check_eligibility(
        self,
        location_keys: list[str],
        company_schemas: list[str],
    ) -> list[LocationEligibilityResult]:
        """
        Bulk check eligibility for multiple locations.

        Args:
            location_keys: List of location identifiers
            company_schemas: Company schemas to search

        Returns:
            List of LocationEligibilityResult
        """
        url = f"{self.base_url}/internal/eligibility/bulk"
        params = {
            "location_keys": location_keys,
            "company_schemas": company_schemas,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    return [LocationEligibilityResult(**r) for r in data]
                else:
                    logger.warning(
                        f"[SALES_MODULE_CLIENT] Bulk eligibility check failed: "
                        f"{response.status_code}"
                    )
                    return []

        except httpx.RequestError as e:
            logger.error(f"[SALES_MODULE_CLIENT] Request error: {e}")
            return []


# =============================================================================
# SINGLETON
# =============================================================================

_client: SalesModuleClient | None = None


def get_sales_module_client() -> SalesModuleClient:
    """Get or create the singleton SalesModuleClient."""
    global _client
    if _client is None:
        _client = SalesModuleClient()
    return _client
