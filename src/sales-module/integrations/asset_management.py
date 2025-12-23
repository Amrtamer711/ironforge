"""
Async HTTP client for Asset-Management service.

Uses short-lived JWT tokens for service-to-service authentication.

Usage:
    from integrations import asset_mgmt_client

    # Get locations for companies (async)
    locations = await asset_mgmt_client.get_locations(["backlite_dubai", "backlite_abudhabi"])

    # Get a specific location
    location = await asset_mgmt_client.get_location_by_key("dubai_gateway", ["backlite_dubai"])

    # Check eligibility
    eligibility = await asset_mgmt_client.check_location_eligibility("backlite_dubai", 123)
"""

import logging
from typing import Any

import httpx

from app_settings import settings

logger = logging.getLogger(__name__)


class AssetManagementClient:
    """
    Async HTTP client for asset-management service with JWT auth.

    Provides async methods to query networks, locations, packages, and eligibility
    from the centralized asset-management service.

    All methods are async and should be awaited.
    """

    def __init__(
        self,
        base_url: str | None = None,
        service_name: str = "sales-module",
        timeout: float = 30.0,
    ):
        """
        Initialize the asset management client.

        Args:
            base_url: Override the asset-management service URL
            service_name: Name of this service for JWT claims
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.asset_mgmt_url or "http://localhost:8001"
        self.service_name = service_name
        self.timeout = timeout
        self._auth_client = None
        self._http_client: httpx.AsyncClient | None = None

    def _get_auth_client(self):
        """Lazy-load the auth client."""
        if self._auth_client is None:
            try:
                from crm_security import ServiceAuthClient
                self._auth_client = ServiceAuthClient(self.service_name)
            except ImportError:
                logger.warning(
                    "[ASSET CLIENT] crm_security not available, "
                    "inter-service auth will be disabled"
                )
        return self._auth_client

    def _get_headers(self) -> dict[str, str]:
        """Get headers for authenticated inter-service request."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": self.service_name,
        }

        auth_client = self._get_auth_client()
        if auth_client:
            try:
                auth_headers = auth_client.get_auth_headers()
                headers.update(auth_headers)
            except Exception as e:
                logger.warning(f"[ASSET CLIENT] Failed to get auth headers: {e}")

        return headers

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client. Call when done using the client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any] | list[dict] | None:
        """
        Make authenticated async request to asset-management.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/api/v1/locations")
            **kwargs: Additional arguments to pass to httpx

        Returns:
            JSON response data, or None if 404

        Raises:
            ConnectionError: If unable to connect to asset-management
            httpx.HTTPStatusError: For non-404 error responses
        """
        headers = kwargs.pop("headers", {})
        headers.update(self._get_headers())

        client = await self._get_http_client()

        try:
            response = await client.request(
                method,
                endpoint,
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(
                f"[ASSET CLIENT] HTTP error {e.response.status_code} "
                f"for {method} {endpoint}: {e.response.text}"
            )
            raise

        except httpx.ConnectError as e:
            logger.error(f"[ASSET CLIENT] Connection failed to {self.base_url}{endpoint}: {e}")
            raise ConnectionError(f"Failed to connect to asset-management: {e}")

        except httpx.RequestError as e:
            logger.error(f"[ASSET CLIENT] Request error for {endpoint}: {e}")
            raise ConnectionError(f"Request to asset-management failed: {e}")

    # =========================================================================
    # NETWORKS
    # =========================================================================

    async def get_networks(
        self,
        companies: list[str],
        active_only: bool = True,
    ) -> list[dict]:
        """
        Get networks for given companies.

        Args:
            companies: List of company schemas to query
            active_only: Only return active networks

        Returns:
            List of network objects
        """
        params = {
            "companies": companies,
            "active_only": active_only,
        }
        return await self._request("GET", "/api/v1/networks", params=params) or []

    async def get_network(self, company: str, network_id: int) -> dict | None:
        """
        Get a specific network by ID.

        Args:
            company: Company schema
            network_id: Network ID

        Returns:
            Network object or None if not found
        """
        return await self._request("GET", f"/api/v1/networks/{company}/{network_id}")

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    async def get_locations(
        self,
        companies: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        active_only: bool = True,
        include_eligibility: bool = False,
    ) -> list[dict]:
        """
        Get locations for given companies.

        Args:
            companies: List of company schemas to query
            network_id: Optional filter by network
            type_id: Optional filter by asset type
            active_only: Only return active locations
            include_eligibility: Include eligibility info in response

        Returns:
            List of location objects
        """
        params: dict[str, Any] = {
            "companies": companies,
            "active_only": active_only,
            "include_eligibility": include_eligibility,
        }
        if network_id is not None:
            params["network_id"] = network_id
        if type_id is not None:
            params["type_id"] = type_id

        return await self._request("GET", "/api/v1/locations", params=params) or []

    async def get_location(
        self,
        company: str,
        location_id: int,
        include_eligibility: bool = True,
    ) -> dict | None:
        """
        Get a specific location by ID.

        Args:
            company: Company schema
            location_id: Location ID
            include_eligibility: Include eligibility info

        Returns:
            Location object or None if not found
        """
        params = {"include_eligibility": include_eligibility}
        return await self._request(
            "GET",
            f"/api/v1/locations/{company}/{location_id}",
            params=params,
        )

    async def get_location_by_key(
        self,
        location_key: str,
        companies: list[str],
    ) -> dict | None:
        """
        Get a location by its unique key.

        Args:
            location_key: Location key (e.g., "DXB-LED-001")
            companies: Companies to search in

        Returns:
            Location object or None if not found
        """
        return await self._request(
            "GET",
            f"/api/v1/locations/by-key/{location_key}",
            params={"companies": companies},
        )

    async def expand_to_locations(self, items: list[dict]) -> list[dict]:
        """
        Expand packages/networks to flat list of locations.

        Args:
            items: List of items with type (network/package/location) and id

        Returns:
            Flat list of location objects
        """
        return await self._request("POST", "/api/v1/locations/expand", json=items) or []

    # =========================================================================
    # PACKAGES
    # =========================================================================

    async def get_packages(
        self,
        companies: list[str],
        active_only: bool = True,
    ) -> list[dict]:
        """
        Get packages for given companies.

        Args:
            companies: List of company schemas to query
            active_only: Only return active packages

        Returns:
            List of package objects
        """
        params = {
            "companies": companies,
            "active_only": active_only,
        }
        return await self._request("GET", "/api/v1/packages", params=params) or []

    async def get_package(
        self,
        company: str,
        package_id: int,
        include_items: bool = True,
    ) -> dict | None:
        """
        Get a specific package by ID.

        Args:
            company: Company schema
            package_id: Package ID
            include_items: Include package items (networks/locations)

        Returns:
            Package object or None if not found
        """
        params = {"include_items": include_items}
        return await self._request(
            "GET",
            f"/api/v1/packages/{company}/{package_id}",
            params=params,
        )

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    async def check_location_eligibility(
        self,
        company: str,
        location_id: int,
        service: str | None = None,
    ) -> dict:
        """
        Check if a location is eligible for a service.

        Args:
            company: Company schema
            location_id: Location ID
            service: Optional specific service to check

        Returns:
            Eligibility result with eligible flag and reasons
        """
        params = {}
        if service:
            params["service"] = service

        result = await self._request(
            "GET",
            f"/api/v1/eligibility/check/{company}/{location_id}",
            params=params,
        )
        return result or {"eligible": False, "error": "Location not found"}

    async def get_eligible_locations(
        self,
        service: str,
        companies: list[str],
    ) -> list[dict]:
        """
        Get all locations eligible for a specific service.

        Args:
            service: Service to check eligibility for
            companies: Companies to search in

        Returns:
            List of eligible location objects
        """
        return await self._request(
            "GET",
            "/api/v1/eligibility/eligible-locations",
            params={"service": service, "companies": companies},
        ) or []

    # =========================================================================
    # ASSET TYPES
    # =========================================================================

    async def get_asset_types(
        self,
        companies: list[str],
        network_id: int | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """
        Get asset types for given companies.

        Args:
            companies: List of company schemas to query
            network_id: Optional filter by network
            active_only: Only return active types

        Returns:
            List of asset type objects
        """
        params: dict[str, Any] = {
            "companies": companies,
            "active_only": active_only,
        }
        if network_id is not None:
            params["network_id"] = network_id

        return await self._request("GET", "/api/v1/asset-types", params=params) or []


# Singleton instance for convenience
asset_mgmt_client = AssetManagementClient()
