"""
Abstract base class for database backends.
Each backend implements their own storage-specific syntax.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NetworkRecord:
    """Network database record."""
    network_key: str
    name: str
    company: str
    id: int | None = None
    description: str | None = None
    # Unified architecture: standalone flag (INTERNAL ONLY - never exposed to frontend)
    standalone: bool = False
    # Location fields (for standalone networks)
    display_type: str | None = None  # 'digital' or 'static'
    series: str | None = None
    height: str | None = None
    width: str | None = None
    number_of_faces: int | None = None
    spot_duration: int | None = None
    loop_duration: int | None = None
    sov_percent: float | None = None
    upload_fee: float | None = None
    city: str | None = None
    area: str | None = None
    country: str | None = None
    address: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    template_path: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None


@dataclass
class AssetTypeRecord:
    """Asset type database record."""
    type_key: str
    name: str
    network_id: int
    company: str
    id: int | None = None
    description: str | None = None
    specs: dict = field(default_factory=dict)
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None


@dataclass
class LocationRecord:
    """Location database record."""
    location_key: str
    display_name: str
    display_type: str
    company: str
    id: int | None = None
    network_id: int | None = None
    type_id: int | None = None
    series: str | None = None
    height: str | None = None
    width: str | None = None
    number_of_faces: int = 1
    spot_duration: int | None = None
    loop_duration: int | None = None
    sov_percent: float | None = None
    upload_fee: float | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    template_path: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None


@dataclass
class PackageRecord:
    """Package database record."""
    package_key: str
    name: str
    company: str
    id: int | None = None
    description: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None


@dataclass
class PackageItemRecord:
    """Package item database record."""
    package_id: int
    item_type: str = "network"  # Always 'network' after unified architecture
    id: int | None = None
    network_id: int | None = None  # Required for unified architecture
    created_at: str | None = None


class DatabaseBackend(ABC):
    """
    Abstract base class for database backends.

    Each backend (SQLite, Supabase, etc.) implements this interface
    with their own storage-specific syntax.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g., 'sqlite', 'supabase')."""
        pass

    @abstractmethod
    def init_db(self) -> None:
        """Initialize database schema."""
        pass

    # =========================================================================
    # NETWORKS
    # =========================================================================

    @abstractmethod
    def create_network(
        self,
        network_key: str,
        name: str,
        company_schema: str,
        description: str | None = None,
        created_by: str | None = None,
        # Unified architecture fields
        standalone: bool = False,
        display_type: str | None = None,
        series: str | None = None,
        height: str | None = None,
        width: str | None = None,
        number_of_faces: int | None = None,
        spot_duration: int | None = None,
        loop_duration: int | None = None,
        sov_percent: float | None = None,
        upload_fee: float | None = None,
        city: str | None = None,
        area: str | None = None,
        country: str | None = None,
        address: str | None = None,
        gps_lat: float | None = None,
        gps_lng: float | None = None,
        template_path: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Create a new network.

        Args:
            network_key: Unique key for the network
            name: Display name
            company_schema: Company schema to create in
            description: Optional description
            created_by: User ID who created
            standalone: INTERNAL flag - True for standalone networks (no asset types)
            display_type: 'digital' or 'static' (for standalone networks)
            series: Series identifier
            height: Height specification
            width: Width specification
            number_of_faces: Number of display faces
            spot_duration: Spot duration in seconds
            loop_duration: Loop duration in seconds
            sov_percent: Share of voice percentage
            upload_fee: Upload fee
            city: City location
            area: Area within city
            country: Country
            address: Full address
            gps_lat: GPS latitude
            gps_lng: GPS longitude
            template_path: Path to template
            notes: Additional notes

        Returns:
            Created network record or None if failed
        """
        pass

    @abstractmethod
    def get_network(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """
        Get a network by ID.

        Args:
            network_id: Network ID
            company_schemas: List of accessible company schemas

        Returns:
            Network record with company_schema field or None
        """
        pass

    @abstractmethod
    def get_network_by_key(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """
        Get a network by key.

        Args:
            network_key: Network key
            company_schemas: List of accessible company schemas

        Returns:
            Network record with company_schema field or None
        """
        pass

    @abstractmethod
    def list_networks(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List networks for given company schemas.

        Args:
            company_schemas: List of company schemas to query
            include_inactive: Include inactive networks
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of network records with company_schema field
        """
        pass

    @abstractmethod
    def update_network(
        self,
        network_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update a network.

        Args:
            network_id: Network ID
            company_schema: Company schema where network exists
            updates: Dict of fields to update

        Returns:
            Updated network record or None if not found
        """
        pass

    @abstractmethod
    def delete_network(
        self,
        network_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a network (soft delete by default).

        Args:
            network_id: Network ID
            company_schema: Company schema where network exists
            hard_delete: If True, permanently delete

        Returns:
            True if deleted, False if not found
        """
        pass

    # =========================================================================
    # ASSET TYPES
    # =========================================================================

    @abstractmethod
    def create_asset_type(
        self,
        type_key: str,
        name: str,
        network_id: int,
        company_schema: str,
        description: str | None = None,
        specs: dict | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Create a new asset type.

        Args:
            type_key: Unique key within the network
            name: Display name
            network_id: Parent network ID
            company_schema: Company schema to create in
            description: Optional description
            specs: Optional specifications dict
            created_by: User ID who created

        Returns:
            Created asset type record or None if failed
        """
        pass

    @abstractmethod
    def get_asset_type(
        self,
        type_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get an asset type by ID."""
        pass

    @abstractmethod
    def list_asset_types(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List asset types.

        Args:
            company_schemas: List of company schemas to query
            network_id: Optional filter by network
            include_inactive: Include inactive types
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of asset type records
        """
        pass

    @abstractmethod
    def update_asset_type(
        self,
        type_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an asset type."""
        pass

    @abstractmethod
    def delete_asset_type(
        self,
        type_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete an asset type."""
        pass

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    @abstractmethod
    def create_location(
        self,
        location_key: str,
        display_name: str,
        display_type: str,
        company_schema: str,
        network_id: int | None = None,
        type_id: int | None = None,
        created_by: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """
        Create a new location.

        Args:
            location_key: Unique key for the location
            display_name: Display name
            display_type: 'digital' or 'static'
            company_schema: Company schema to create in
            network_id: Optional parent network
            type_id: Optional parent asset type
            created_by: User ID who created
            **kwargs: Additional location fields

        Returns:
            Created location record or None if failed
        """
        pass

    @abstractmethod
    def get_location(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a location by ID."""
        pass

    @abstractmethod
    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a location by key."""
        pass

    @abstractmethod
    def list_locations(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List locations.

        Args:
            company_schemas: List of company schemas to query
            network_id: Optional filter by network
            type_id: Optional filter by asset type
            include_inactive: Include inactive locations
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of location records
        """
        pass

    @abstractmethod
    def update_location(
        self,
        location_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a location."""
        pass

    @abstractmethod
    def delete_location(
        self,
        location_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete a location."""
        pass

    # =========================================================================
    # PACKAGES
    # =========================================================================

    @abstractmethod
    def create_package(
        self,
        package_key: str,
        name: str,
        company_schema: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a new package."""
        pass

    @abstractmethod
    def get_package(
        self,
        package_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a package by ID with items."""
        pass

    @abstractmethod
    def list_packages(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List packages."""
        pass

    @abstractmethod
    def update_package(
        self,
        package_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a package."""
        pass

    @abstractmethod
    def delete_package(
        self,
        package_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete a package."""
        pass

    # =========================================================================
    # PACKAGE ITEMS
    # =========================================================================

    @abstractmethod
    def add_package_item(
        self,
        package_id: int,
        company_schema: str,
        network_id: int,
    ) -> dict[str, Any] | None:
        """
        Add a network to a package.

        After unified architecture, all package items are networks.
        Both standalone and traditional networks are added the same way.

        Args:
            package_id: Package ID
            company_schema: Company schema
            network_id: Network ID (required)

        Returns:
            Created package item record or None
        """
        pass

    @abstractmethod
    def remove_package_item(
        self,
        item_id: int,
        company_schema: str,
    ) -> bool:
        """Remove an item from a package."""
        pass

    @abstractmethod
    def get_package_items(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """Get all items in a package."""
        pass

    @abstractmethod
    def get_package_locations(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """
        Get all locations in a package (expanded from networks and direct assets).

        Returns:
            List of location records
        """
        pass

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    @abstractmethod
    def check_location_eligibility(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        """
        Check eligibility of a location for each service.

        Returns:
            Dict with service_eligibility and detailed reasons
        """
        pass

    @abstractmethod
    def check_network_eligibility(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        """
        Check eligibility of a network for each service.

        Returns:
            Dict with service_eligibility and detailed reasons
        """
        pass

    @abstractmethod
    def get_eligible_locations(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get locations eligible for a specific service.

        Args:
            service: 'proposal_generator', 'mockup_generator', or 'availability_calendar'
            company_schemas: List of company schemas to query
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of eligible location records
        """
        pass

    @abstractmethod
    def get_eligible_networks(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get networks eligible for a specific service.

        Args:
            service: 'proposal_generator', 'mockup_generator', or 'availability_calendar'
            company_schemas: List of company schemas to query
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of eligible network records
        """
        pass

    # =========================================================================
    # CROSS-SERVICE LOOKUPS
    # =========================================================================

    @abstractmethod
    def has_mockup_frame(
        self,
        location_key: str,
        company_schema: str,
    ) -> bool:
        """Check if a location has a mockup frame (from sales-module)."""
        pass

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    @abstractmethod
    def list_mockup_frames(
        self,
        location_key: str,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """
        List all mockup frames for a location.

        Args:
            location_key: Location identifier
            company_schema: Company schema

        Returns:
            List of mockup frame records
        """
        pass

    @abstractmethod
    def get_locations_with_frames(
        self,
        company_schemas: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all distinct location_keys that have mockup frames across companies.

        This is a bulk query to avoid N+1 queries when checking eligibility.

        Args:
            company_schemas: List of company schemas to check

        Returns:
            List of dicts with location_key, company, frame_count
        """
        pass

    @abstractmethod
    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        company_schema: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
        created_by: str | None = None,
        config: dict | None = None,
    ) -> str:
        """
        Save mockup frame data. Returns the final auto-numbered filename.

        Args:
            location_key: Location identifier
            photo_filename: Original photo filename
            frames_data: List of frame coordinate dicts
            company_schema: Company schema
            environment: "indoor" or "outdoor"
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)
            created_by: User email who created this
            config: Optional config dict

        Returns:
            Final auto-numbered filename (e.g., "Dubai_Mall_1.jpg")
        """
        pass

    @abstractmethod
    def get_mockup_frame(
        self,
        location_key: str,
        company: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
        photo_filename: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get specific mockup frame data.

        Args:
            location_key: Location identifier
            company: Company schema
            environment: "indoor" or "outdoor"
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)
            photo_filename: Specific photo (optional, returns first if None)

        Returns:
            Mockup frame record or None
        """
        pass

    @abstractmethod
    def delete_mockup_frame(
        self,
        location_key: str,
        company: str,
        photo_filename: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
    ) -> bool:
        """
        Delete a mockup frame.

        Args:
            location_key: Location identifier
            company: Company schema
            photo_filename: Photo filename
            environment: "indoor" or "outdoor"
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)

        Returns:
            True if deleted successfully
        """
        pass

    # =========================================================================
    # COMPANIES
    # =========================================================================

    @abstractmethod
    def get_companies(
        self,
        active_only: bool = True,
        leaf_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get all companies from the database.

        Args:
            active_only: If True, only return active companies
            leaf_only: If True, only return leaf companies (not groups)

        Returns:
            List of company dicts with code, name, is_group, is_active, etc.
        """
        pass
