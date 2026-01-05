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
            endpoint: API endpoint (e.g., "/api/locations")
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

        Uses internal endpoint for service-to-service communication.

        Args:
            companies: List of company schemas to query
            active_only: Only return active networks

        Returns:
            List of network objects
        """
        params = {
            "companies": companies,
        }
        return await self._request("GET", "/api/internal/networks", params=params) or []

    async def get_network(self, company: str, network_id: int) -> dict | None:
        """
        Get a specific network by ID.

        Args:
            company: Company schema
            network_id: Network ID

        Returns:
            Network object or None if not found
        """
        return await self._request("GET", f"/api/networks/{company}/{network_id}")

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

        return await self._request("GET", "/api/internal/locations", params=params) or []

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
            f"/api/locations/{company}/{location_id}",
            params=params,
        )

    async def get_location_by_key(
        self,
        location_key: str,
        companies: list[str],
    ) -> dict | None:
        """
        Get a location by its unique key.

        Uses internal endpoint for service-to-service auth.

        Args:
            location_key: Location key (e.g., "DXB-LED-001")
            companies: Companies to search in

        Returns:
            Location object or None if not found
        """
        return await self._request(
            "GET",
            f"/api/internal/locations/by-key/{location_key}",
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
        return await self._request("POST", "/api/locations/expand", json=items) or []

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
        return await self._request("GET", "/api/packages", params=params) or []

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
            f"/api/packages/{company}/{package_id}",
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
            f"/api/eligibility/check/{company}/{location_id}",
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
            "/api/eligibility/eligible-locations",
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

        return await self._request("GET", "/api/asset-types", params=params) or []

    # =========================================================================
    # STORAGE - Templates & Mockups from Asset-Management
    # =========================================================================

    async def get_template(
        self,
        company: str,
        location_key: str,
    ) -> bytes | None:
        """
        Download template file from Asset-Management storage.

        Args:
            company: Company schema (e.g., "backlite_dubai")
            location_key: Location identifier (e.g., "dubai_mall")

        Returns:
            Template file bytes or None if not found
        """
        try:
            response = await self._request(
                "GET",
                f"/api/storage/templates/{company}/{location_key}",
            )
            if response and "data" in response:
                import base64
                return base64.b64decode(response["data"])
            return None
        except Exception as e:
            logger.error(f"[ASSET CLIENT] Failed to get template {location_key}: {e}")
            return None

    async def get_template_url(
        self,
        company: str,
        location_key: str,
        expires_in: int = 3600,
    ) -> str | None:
        """
        Get signed URL for template download.

        Args:
            company: Company schema
            location_key: Location identifier
            expires_in: URL expiry in seconds

        Returns:
            Signed URL or None if not found
        """
        result = await self._request(
            "GET",
            f"/api/storage/templates/{company}/{location_key}/url",
            params={"expires_in": expires_in},
        )
        return result.get("url") if result else None

    async def list_templates(self, company: str) -> list[dict]:
        """
        List all templates for a company.

        Args:
            company: Company schema

        Returns:
            List of template info dicts with location_key and storage_key
        """
        return await self._request("GET", f"/api/storage/templates/{company}") or []

    async def template_exists(self, company: str, location_key: str) -> bool:
        """
        Check if template exists for location.

        Args:
            company: Company schema
            location_key: Location identifier

        Returns:
            True if template exists
        """
        result = await self._request(
            "GET",
            f"/api/storage/templates/{company}/{location_key}/exists",
        )
        return result.get("exists", False) if result else False

    async def upload_template(
        self,
        company: str,
        location_key: str,
        file_data: bytes,
        filename: str | None = None,
    ) -> dict | None:
        """
        Upload template file to Asset-Management storage.

        Args:
            company: Company schema (e.g., "backlite_dubai")
            location_key: Location identifier (e.g., "dubai_mall")
            file_data: Template file bytes
            filename: Optional custom filename (defaults to {location_key}.pptx)

        Returns:
            Upload result dict with success, storage_key, message or None on error
        """
        import base64
        try:
            result = await self._request(
                "POST",
                f"/api/storage/templates/{company}",
                json={
                    "location_key": location_key,
                    "data": base64.b64encode(file_data).decode("utf-8"),
                    "filename": filename,
                },
            )
            return result
        except Exception as e:
            logger.error(f"[ASSET CLIENT] Failed to upload template {location_key}: {e}")
            return None

    async def delete_template(
        self,
        company: str,
        location_key: str,
    ) -> dict | None:
        """
        Delete template file from Asset-Management storage.

        Args:
            company: Company schema
            location_key: Location identifier

        Returns:
            Delete result dict with success, storage_key, message or None on error
        """
        try:
            result = await self._request(
                "DELETE",
                f"/api/storage/templates/{company}/{location_key}",
            )
            return result
        except Exception as e:
            logger.error(f"[ASSET CLIENT] Failed to delete template {location_key}: {e}")
            return None

    async def get_mockup_frames(
        self,
        company: str,
        location_key: str,
    ) -> list[dict]:
        """
        Get all mockup frames for a location.

        Args:
            company: Company schema
            location_key: Location identifier

        Returns:
            List of mockup frame dicts with time_of_day, finish, photo_filename, frames_data
        """
        return await self._request(
            "GET",
            f"/api/mockup-frames/{company}/{location_key}",
        ) or []

    async def get_mockup_frame(
        self,
        company: str,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
        photo_filename: str | None = None,
    ) -> dict | None:
        """
        Get specific mockup frame data.

        Args:
            company: Company schema
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Specific photo (optional, returns first match if None)

        Returns:
            Mockup frame data dict or None
        """
        params: dict[str, Any] = {"time_of_day": time_of_day, "finish": finish}
        if photo_filename:
            params["photo_filename"] = photo_filename

        return await self._request(
            "GET",
            f"/api/mockup-frames/{company}/{location_key}/frame",
            params=params,
        )

    async def delete_mockup_frame(
        self,
        company: str,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> bool:
        """
        Delete a mockup frame from Asset-Management.

        Args:
            company: Company schema
            location_key: Location identifier
            photo_filename: Photo filename to delete
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"

        Returns:
            True if deleted successfully
        """
        try:
            result = await self._request(
                "DELETE",
                f"/api/mockup-frames/{company}/{location_key}",
                params={
                    "photo_filename": photo_filename,
                    "time_of_day": time_of_day,
                    "finish": finish,
                },
            )
            return result.get("success", False) if result else False
        except Exception as e:
            logger.error(f"[ASSET CLIENT] Failed to delete mockup frame: {e}")
            return False

    async def get_mockup_photo(
        self,
        company: str,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_filename: str,
    ) -> bytes | None:
        """
        Download mockup background photo from Asset-Management storage.

        Args:
            company: Company schema
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Photo filename

        Returns:
            Photo bytes or None if not found
        """
        try:
            response = await self._request(
                "GET",
                f"/api/storage/mockups/{company}/{location_key}/{time_of_day}/{finish}/{photo_filename}",
            )
            if response and "data" in response:
                import base64
                return base64.b64decode(response["data"])
            return None
        except Exception as e:
            logger.error(f"[ASSET CLIENT] Failed to get mockup photo: {e}")
            return None

    async def get_mockup_photo_url(
        self,
        company: str,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_filename: str,
        expires_in: int = 3600,
    ) -> str | None:
        """
        Get signed URL for mockup photo.

        Args:
            company: Company schema
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Photo filename
            expires_in: URL expiry in seconds

        Returns:
            Signed URL or None if not found
        """
        result = await self._request(
            "GET",
            f"/api/storage/mockups/{company}/{location_key}/{time_of_day}/{finish}/{photo_filename}/url",
            params={"expires_in": expires_in},
        )
        return result.get("url") if result else None

    async def get_intro_outro_pdf(self, company: str, pdf_name: str) -> bytes | None:
        """
        Download intro/outro PDF from Asset-Management storage.

        Args:
            company: Company schema
            pdf_name: PDF name (e.g., "landmark_series", "rest")

        Returns:
            PDF bytes or None if not found
        """
        try:
            response = await self._request(
                "GET",
                f"/api/storage/intro-outro/{company}/{pdf_name}",
            )
            if response and "data" in response:
                import base64
                return base64.b64decode(response["data"])
            return None
        except Exception as e:
            logger.debug(f"[ASSET CLIENT] Intro/outro PDF not found: {pdf_name}")
            return None


# Singleton instance for convenience
asset_mgmt_client = AssetManagementClient()
