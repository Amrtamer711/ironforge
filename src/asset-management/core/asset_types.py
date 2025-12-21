"""
Asset Types - Schemas and service logic.

Asset Types are organizational categories within networks (NOT sellable).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.asset_types")


# =============================================================================
# SCHEMAS
# =============================================================================


class AssetTypeBase(BaseModel):
    """Base asset type fields."""

    type_key: str = Field(..., description="Unique key within the network")
    name: str = Field(..., description="Display name")
    description: str | None = Field(default=None, description="Description")
    specs: dict = Field(default_factory=dict, description="Specifications (dimensions, display_type, etc.)")


class AssetTypeCreate(AssetTypeBase):
    """Fields for creating an asset type."""

    network_id: int = Field(..., description="Parent network ID")


class AssetTypeUpdate(BaseModel):
    """Fields for updating an asset type (all optional)."""

    type_key: str | None = None
    name: str | None = None
    description: str | None = None
    specs: dict | None = None
    is_active: bool | None = None


class LocationSummary(BaseModel):
    """Summary of location for nesting."""

    id: int
    location_key: str
    display_name: str
    display_type: str


class AssetType(AssetTypeBase):
    """Full asset type model with database fields."""

    id: int
    network_id: int
    company: str = Field(..., description="Company schema")
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    # Optional nested data
    network_name: str | None = None
    locations: list[LocationSummary] | None = None
    location_count: int = 0

    class Config:
        from_attributes = True


# =============================================================================
# SERVICE
# =============================================================================


class AssetTypeService:
    """Business logic for asset type operations."""

    def list_asset_types(
        self,
        companies: list[str],
        network_id: int | None = None,
        active_only: bool = True,
    ) -> list[AssetType]:
        """List asset types across companies."""
        results = db.list_asset_types(
            company_schemas=companies,
            network_id=network_id,
            include_inactive=not active_only,
        )
        return [self._dict_to_asset_type(r) for r in results]

    def get_asset_type(
        self,
        company: str,
        type_id: int,
        include_locations: bool = False,
    ) -> AssetType | None:
        """Get a single asset type with optional nested data."""
        result = db.get_asset_type(type_id, [company])
        if not result:
            return None

        asset_type = self._dict_to_asset_type(result)

        # Fetch locations if requested
        if include_locations:
            locs = db.list_locations([company], type_id=type_id)
            asset_type.locations = [
                LocationSummary(
                    id=loc["id"],
                    location_key=loc["location_key"],
                    display_name=loc["display_name"],
                    display_type=loc["display_type"],
                )
                for loc in locs
            ]

        # Set location count
        asset_type.location_count = len(db.list_locations([company], type_id=type_id))

        return asset_type

    def create_asset_type(
        self,
        company: str,
        data: AssetTypeCreate,
        created_by: str | None = None,
    ) -> AssetType:
        """Create a new asset type."""
        logger.info(f"Creating asset type '{data.name}' in {company}")

        result = db.create_asset_type(
            type_key=data.type_key,
            name=data.name,
            network_id=data.network_id,
            company_schema=company,
            description=data.description,
            specs=data.specs,
            created_by=created_by,
        )

        if not result:
            raise ValueError(f"Failed to create asset type: {data.type_key}")

        return self._dict_to_asset_type(result)

    def update_asset_type(
        self,
        company: str,
        type_id: int,
        data: AssetTypeUpdate,
    ) -> AssetType | None:
        """Update an existing asset type."""
        logger.info(f"Updating asset type {type_id} in {company}")

        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if not updates:
            return self.get_asset_type(company, type_id)

        result = db.update_asset_type(type_id, company, updates)
        if not result:
            return None

        return self._dict_to_asset_type(result)

    def delete_asset_type(
        self,
        company: str,
        type_id: int,
    ) -> bool:
        """Soft delete an asset type."""
        logger.info(f"Deleting asset type {type_id} in {company}")
        return db.delete_asset_type(type_id, company)

    def _dict_to_asset_type(self, data: dict[str, Any]) -> AssetType:
        """Convert a database dict to an AssetType model."""
        return AssetType(
            id=data["id"],
            type_key=data["type_key"],
            name=data["name"],
            description=data.get("description"),
            specs=data.get("specs", {}),
            network_id=data["network_id"],
            company=data.get("company_schema", data.get("company", "")),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            created_by=data.get("created_by"),
            network_name=data.get("network_name"),
        )
