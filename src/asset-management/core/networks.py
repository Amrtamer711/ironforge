"""
Networks - Schemas and service logic.

Networks are sellable groupings of assets.

After migration 02_unify_standalone, ALL sellable entities are networks:
- Traditional networks (standalone=False): Have multiple assets, mockups at asset level
- Standalone networks (standalone=True): Have location fields directly, mockups at network level

IMPORTANT: The `standalone` flag is INTERNAL ONLY - never exposed to frontend.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.networks")


# =============================================================================
# SCHEMAS
# =============================================================================


class NetworkBase(BaseModel):
    """Base network fields."""

    network_key: str = Field(..., description="Unique key for the network")
    name: str = Field(..., description="Display name")
    description: str | None = Field(default=None, description="Description")

    # Network-level attributes (shared)
    series: str | None = Field(default=None, description="Series/category")
    sov_percent: Decimal | None = Field(default=None, description="Share of voice percentage")
    upload_fee: Decimal | None = Field(default=None, description="Upload fee")
    spot_duration: int | None = Field(default=None, description="Spot duration in seconds")
    loop_duration: int | None = Field(default=None, description="Loop duration in seconds")
    number_of_faces: int | None = Field(default=None, description="Number of faces")
    template_path: str | None = Field(default=None, description="Template path")

    # Location fields (used for standalone networks)
    display_type: str | None = Field(default=None, description="'digital' or 'static' (standalone only)")
    height: str | None = Field(default=None, description="Height (standalone only)")
    width: str | None = Field(default=None, description="Width (standalone only)")
    city: str | None = Field(default=None, description="City (standalone only)")
    area: str | None = Field(default=None, description="Area (standalone only)")
    country: str | None = Field(default=None, description="Country (standalone only)")
    address: str | None = Field(default=None, description="Address (standalone only)")
    gps_lat: Decimal | None = Field(default=None, description="GPS latitude (standalone only)")
    gps_lng: Decimal | None = Field(default=None, description="GPS longitude (standalone only)")


class NetworkCreate(NetworkBase):
    """Fields for creating a network."""

    # INTERNAL: standalone flag (not exposed to frontend)
    standalone: bool = Field(default=False, description="INTERNAL: True for standalone networks")


class NetworkUpdate(BaseModel):
    """Fields for updating a network (all optional)."""

    network_key: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None

    # Network-level attributes
    series: str | None = None
    sov_percent: Decimal | None = None
    upload_fee: Decimal | None = None
    spot_duration: int | None = None
    loop_duration: int | None = None
    number_of_faces: int | None = None
    template_path: str | None = None

    # Location fields (standalone only)
    display_type: str | None = None
    height: str | None = None
    width: str | None = None
    city: str | None = None
    area: str | None = None
    country: str | None = None
    address: str | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None


class AssetTypeSummary(BaseModel):
    """Summary of asset type for nesting in network."""

    id: int
    type_key: str
    name: str
    location_count: int = 0


class LocationSummary(BaseModel):
    """Summary of location for nesting."""

    id: int
    location_key: str
    display_name: str
    display_type: str


class Network(NetworkBase):
    """Full network model with database fields."""

    id: int
    company: str = Field(..., description="Company schema this network belongs to")
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    notes: str | None = None

    # INTERNAL: standalone flag (not exposed to frontend via API)
    # Used by backend to determine mockup storage location and behavior
    standalone: bool = Field(default=False, description="INTERNAL: True for standalone networks", exclude=True)

    # Optional nested data
    asset_types: list[AssetTypeSummary] | None = None
    locations: list[LocationSummary] | None = None
    location_count: int = 0

    class Config:
        from_attributes = True


# =============================================================================
# SERVICE
# =============================================================================


class NetworkService:
    """Business logic for network operations."""

    def list_networks(
        self,
        companies: list[str],
        active_only: bool = True,
    ) -> list[Network]:
        """List networks across companies."""
        results = db.list_networks(
            company_schemas=companies,
            include_inactive=not active_only,
        )
        return [self._dict_to_network(r) for r in results]

    def get_network(
        self,
        company: str,
        network_id: int,
        include_types: bool = True,
        include_locations: bool = False,
    ) -> Network | None:
        """Get a single network with optional nested data."""
        result = db.get_network(network_id, [company])
        if not result:
            return None

        network = self._dict_to_network(result)

        # Fetch asset types if requested
        if include_types:
            types = db.list_asset_types([company], network_id=network_id)
            network.asset_types = [
                AssetTypeSummary(
                    id=t["id"],
                    type_key=t["type_key"],
                    name=t["name"],
                    location_count=len(db.list_locations([company], type_id=t["id"])),
                )
                for t in types
            ]

        # Fetch locations if requested
        if include_locations:
            locs = db.list_locations([company], network_id=network_id)
            network.locations = [
                LocationSummary(
                    id=loc["id"],
                    location_key=loc["location_key"],
                    display_name=loc["display_name"],
                    display_type=loc["display_type"],
                )
                for loc in locs
            ]

        # Set location count
        network.location_count = len(db.list_locations([company], network_id=network_id))

        return network

    def create_network(
        self,
        company: str,
        data: NetworkCreate,
        created_by: str | None = None,
    ) -> Network:
        """Create a new network."""
        logger.info(f"Creating network '{data.name}' in {company} (standalone={data.standalone})")

        # Build kwargs for optional fields
        kwargs = {}
        optional_fields = [
            "series", "sov_percent", "upload_fee", "spot_duration", "loop_duration",
            "number_of_faces", "template_path", "display_type", "height", "width",
            "city", "area", "country", "address", "gps_lat", "gps_lng"
        ]
        for field in optional_fields:
            value = getattr(data, field, None)
            if value is not None:
                # Convert Decimal to float for database
                if isinstance(value, Decimal):
                    value = float(value)
                kwargs[field] = value

        result = db.create_network(
            network_key=data.network_key,
            name=data.name,
            company_schema=company,
            description=data.description,
            standalone=data.standalone,
            created_by=created_by,
            **kwargs,
        )

        if not result:
            raise ValueError(f"Failed to create network: {data.network_key}")

        return self._dict_to_network(result)

    def update_network(
        self,
        company: str,
        network_id: int,
        data: NetworkUpdate,
    ) -> Network | None:
        """Update an existing network."""
        logger.info(f"Updating network {network_id} in {company}")

        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if not updates:
            return self.get_network(company, network_id, include_types=False)

        # Convert Decimal to float for database
        for key, value in updates.items():
            if isinstance(value, Decimal):
                updates[key] = float(value)

        result = db.update_network(network_id, company, updates)
        if not result:
            return None

        return self._dict_to_network(result)

    def delete_network(
        self,
        company: str,
        network_id: int,
    ) -> bool:
        """Soft delete a network."""
        logger.info(f"Deleting network {network_id} in {company}")
        return db.delete_network(network_id, company)

    def _dict_to_network(self, data: dict[str, Any]) -> Network:
        """Convert a database dict to a Network model."""
        return Network(
            id=data["id"],
            network_key=data["network_key"],
            name=data["name"],
            description=data.get("description"),
            company=data.get("company_schema", data.get("company", "")),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            created_by=data.get("created_by"),
            notes=data.get("notes"),
            # INTERNAL: standalone flag
            standalone=data.get("standalone", False),
            # Network-level attributes
            series=data.get("series"),
            sov_percent=data.get("sov_percent"),
            upload_fee=data.get("upload_fee"),
            spot_duration=data.get("spot_duration"),
            loop_duration=data.get("loop_duration"),
            number_of_faces=data.get("number_of_faces"),
            template_path=data.get("template_path"),
            # Location fields (standalone only)
            display_type=data.get("display_type"),
            height=data.get("height"),
            width=data.get("width"),
            city=data.get("city"),
            area=data.get("area"),
            country=data.get("country"),
            address=data.get("address"),
            gps_lat=data.get("gps_lat"),
            gps_lng=data.get("gps_lng"),
        )
