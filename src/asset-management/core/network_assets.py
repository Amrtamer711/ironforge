"""
Network Assets - Schemas and service logic.

Network assets are individual billboards/screens within a network.
They are NOT directly sellable (networks are sold as complete units).
These endpoints are for admin/management features.

Environment field determines mockup directory structure:
- 'indoor': Simple list of mockups ({key}/indoor/)
- 'outdoor': Full variations ({key}/outdoor/day/gold/, .../silver/, .../night/gold/, .../silver/)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.network_assets")


# =============================================================================
# SCHEMAS
# =============================================================================


class NetworkAssetBase(BaseModel):
    """Base network asset fields."""

    asset_key: str = Field(..., description="Unique key for the asset")
    display_name: str = Field(..., description="Display name")
    display_type: str = Field(..., description="Type of display (LED, Digital, etc.)")

    # Required associations
    network_id: int = Field(..., description="Parent network ID")
    type_id: int = Field(..., description="Asset type ID")

    # Environment (indoor/outdoor) - determines mockup directory structure
    environment: str = Field(
        default="outdoor",
        description="'indoor' or 'outdoor' - determines mockup directory structure"
    )

    # Physical specs
    series: str | None = Field(default=None, description="Billboard series")
    height: str | None = Field(default=None, description="Height specification")
    width: str | None = Field(default=None, description="Width specification")

    # Display specs
    number_of_faces: int | None = Field(default=None, description="Number of faces")
    spot_duration: int | None = Field(default=None, description="Spot duration in seconds")
    loop_duration: int | None = Field(default=None, description="Loop duration in seconds")
    sov_percent: float | None = Field(default=None, description="Share of voice percentage")
    upload_fee: float | None = Field(default=None, description="Upload fee")

    # Location details
    city: str | None = Field(default=None, description="City")
    area: str | None = Field(default=None, description="Area/district")
    country: str | None = Field(default=None, description="Country")
    address: str | None = Field(default=None, description="Full address")
    gps_lat: float | None = Field(default=None, description="GPS latitude")
    gps_lng: float | None = Field(default=None, description="GPS longitude")

    # Mockup configuration
    template_path: str | None = Field(default=None, description="Mockup template path")

    # Notes
    notes: str | None = Field(default=None, description="Additional notes")


class NetworkAssetCreate(NetworkAssetBase):
    """Fields for creating a network asset."""
    pass


class NetworkAssetUpdate(BaseModel):
    """Fields for updating a network asset (all optional)."""

    asset_key: str | None = None
    display_name: str | None = None
    display_type: str | None = None
    network_id: int | None = None
    type_id: int | None = None
    environment: str | None = None  # 'indoor' or 'outdoor'
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
    is_active: bool | None = None
    notes: str | None = None


class NetworkAsset(NetworkAssetBase):
    """Full network asset model with database fields."""

    id: int
    company: str = Field(..., description="Company schema")
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    # Enriched data
    network_name: str | None = None
    type_name: str | None = None

    class Config:
        from_attributes = True


# =============================================================================
# SERVICE
# =============================================================================


class NetworkAssetService:
    """Business logic for network asset operations."""

    def list_network_assets(
        self,
        companies: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        active_only: bool = True,
    ) -> list[NetworkAsset]:
        """List network assets with optional filters."""
        results = db.list_network_assets(
            company_schemas=companies,
            network_id=network_id,
            type_id=type_id,
            include_inactive=not active_only,
        )
        return [self._dict_to_network_asset(r) for r in results]

    def get_network_asset(
        self,
        company: str,
        asset_id: int,
    ) -> NetworkAsset | None:
        """Get a single network asset."""
        result = db.get_network_asset(asset_id, [company])
        if not result:
            return None
        return self._dict_to_network_asset(result)

    def get_network_asset_by_key(
        self,
        asset_key: str,
        companies: list[str],
    ) -> NetworkAsset | None:
        """Get a network asset by its key."""
        result = db.get_network_asset_by_key(asset_key, companies)
        if not result:
            return None
        return self._dict_to_network_asset(result)

    def create_network_asset(
        self,
        company: str,
        data: NetworkAssetCreate,
        created_by: str | None = None,
    ) -> NetworkAsset:
        """Create a new network asset."""
        logger.info(f"Creating network asset '{data.display_name}' in {company}")

        # Prepare data dict
        asset_data = data.model_dump(exclude_none=True)

        result = db.create_network_asset(
            company_schema=company,
            created_by=created_by,
            **asset_data,
        )

        if not result:
            raise ValueError(f"Failed to create network asset: {data.asset_key}")

        return self._dict_to_network_asset(result)

    def update_network_asset(
        self,
        company: str,
        asset_id: int,
        data: NetworkAssetUpdate,
    ) -> NetworkAsset | None:
        """Update an existing network asset."""
        logger.info(f"Updating network asset {asset_id} in {company}")

        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if not updates:
            return self.get_network_asset(company, asset_id)

        result = db.update_network_asset(asset_id, company, updates)
        if not result:
            return None

        return self._dict_to_network_asset(result)

    def delete_network_asset(
        self,
        company: str,
        asset_id: int,
    ) -> bool:
        """Soft delete a network asset."""
        logger.info(f"Deleting network asset {asset_id} in {company}")
        return db.delete_network_asset(asset_id, company)

    def _dict_to_network_asset(self, data: dict[str, Any]) -> NetworkAsset:
        """Convert a database dict to a NetworkAsset model."""
        return NetworkAsset(
            id=data["id"],
            asset_key=data["asset_key"],
            display_name=data["display_name"],
            display_type=data["display_type"],
            network_id=data["network_id"],
            type_id=data["type_id"],
            environment=data.get("environment", "outdoor"),
            series=data.get("series"),
            height=data.get("height"),
            width=data.get("width"),
            number_of_faces=data.get("number_of_faces"),
            spot_duration=data.get("spot_duration"),
            loop_duration=data.get("loop_duration"),
            sov_percent=data.get("sov_percent"),
            upload_fee=data.get("upload_fee"),
            city=data.get("city"),
            area=data.get("area"),
            country=data.get("country"),
            address=data.get("address"),
            gps_lat=data.get("gps_lat"),
            gps_lng=data.get("gps_lng"),
            template_path=data.get("template_path"),
            notes=data.get("notes"),
            company=data.get("company_schema", data.get("company", "")),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            created_by=data.get("created_by"),
            network_name=data.get("network_name"),
            type_name=data.get("type_name"),
        )
