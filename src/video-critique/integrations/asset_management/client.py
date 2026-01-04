"""
Asset Management Client for Video Critique.

Service-to-service client for communicating with asset-management
to link filmed video locations to the asset library.
"""

import logging
from typing import Any

import httpx
from crm_security import ServiceAuthClient

import config

logger = logging.getLogger(__name__)


class AssetManagementClient:
    """
    Async HTTP client for asset-management service with JWT auth.

    Provides methods to query locations and link filmed video content
    to the centralized asset library.
    """

    def __init__(
        self,
        base_url: str | None = None,
        service_name: str = "video-critique",
        timeout: float = 30.0,
    ):
        """
        Initialize the asset management client.

        Args:
            base_url: Override the asset-management service URL
            service_name: Name of this service for JWT claims
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or getattr(config, "ASSET_MGMT_URL", "http://localhost:8001")
        self.service_name = service_name
        self.timeout = timeout
        self._auth_client = ServiceAuthClient(service_name)
        self._http_client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for authenticated inter-service request."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": self.service_name,
        }
        auth_headers = self._auth_client.get_auth_headers()
        headers.update(auth_headers)
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
            endpoint: API endpoint (e.g., "/api/internal/locations")
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
                f"[AssetClient] HTTP error {e.response.status_code} "
                f"for {method} {endpoint}: {e.response.text}"
            )
            raise

        except httpx.ConnectError as e:
            logger.error(f"[AssetClient] Connection failed to {self.base_url}{endpoint}: {e}")
            raise ConnectionError(f"Failed to connect to asset-management: {e}")

        except httpx.RequestError as e:
            logger.error(f"[AssetClient] Request error for {endpoint}: {e}")
            raise ConnectionError(f"Request to asset-management failed: {e}")

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    async def get_locations(
        self,
        companies: list[str] | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """
        Get all locations from asset-management.

        Uses internal endpoint for service-to-service communication.

        Args:
            companies: Optional list of company schemas to filter
            active_only: Only return active locations

        Returns:
            List of location objects
        """
        params: dict[str, Any] = {"active_only": active_only}
        if companies:
            params["companies"] = companies

        return await self._request("GET", "/api/internal/locations", params=params) or []

    async def get_location_by_key(
        self,
        location_key: str,
        companies: list[str] | None = None,
    ) -> dict | None:
        """
        Get a location by its unique key.

        Args:
            location_key: Location key (e.g., "dubai_mall")
            companies: Optional companies to search in

        Returns:
            Location object or None if not found
        """
        params = {}
        if companies:
            params["companies"] = companies

        return await self._request(
            "GET",
            f"/api/locations/by-key/{location_key}",
            params=params,
        )

    async def search_locations_by_name(
        self,
        name: str,
        companies: list[str] | None = None,
    ) -> list[dict]:
        """
        Search for locations by display name (case-insensitive partial match).

        Args:
            name: Location name to search for
            companies: Optional companies to filter

        Returns:
            List of matching location objects
        """
        all_locations = await self.get_locations(companies=companies)

        # Filter by name (case-insensitive partial match)
        name_lower = name.lower()
        return [
            loc for loc in all_locations
            if name_lower in loc.get("display_name", "").lower()
            or name_lower in loc.get("location_key", "").lower()
        ]

    # =========================================================================
    # VIDEO CONTENT LINKING
    # =========================================================================

    async def link_video_to_location(
        self,
        task_number: int,
        location_id: int,
        company: str,
        metadata: dict[str, Any],
    ) -> bool:
        """
        Notify asset-management about filmed video content at a location.

        This creates a record linking the video-critique task to the
        asset-management location, enabling the asset library to know
        what video content exists for each location.

        Args:
            task_number: Video-critique task number
            location_id: Asset-management location ID
            company: Company schema
            metadata: Video metadata (brand, campaign dates, dropbox path, etc.)

        Returns:
            True if linked successfully
        """
        payload = {
            "source": "video-critique",
            "source_id": str(task_number),
            "location_id": location_id,
            "company": company,
            "metadata": metadata,
        }

        try:
            # Note: This endpoint may need to be created in asset-management
            # For now, we log the intent
            logger.info(
                f"[AssetClient] Linking video task {task_number} to "
                f"location {location_id} in {company}"
            )

            # Attempt to call the endpoint if it exists
            result = await self._request(
                "POST",
                f"/api/internal/locations/{company}/{location_id}/content",
                json=payload,
            )
            return result is not None and result.get("success", False)

        except Exception as e:
            logger.warning(
                f"[AssetClient] Could not link video to location "
                f"(endpoint may not exist yet): {e}"
            )
            return False


# Singleton instance
_client: AssetManagementClient | None = None


def get_asset_client() -> AssetManagementClient:
    """Get the singleton asset management client."""
    global _client
    if _client is None:
        _client = AssetManagementClient()
    return _client
