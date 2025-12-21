"""
Networks - Schemas and service logic.

Networks are sellable groupings of assets.
"""

from datetime import datetime
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


class NetworkCreate(NetworkBase):
    """Fields for creating a network."""

    pass


class NetworkUpdate(BaseModel):
    """Fields for updating a network (all optional)."""

    network_key: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


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
        logger.info(f"Creating network '{data.name}' in {company}")

        result = db.create_network(
            network_key=data.network_key,
            name=data.name,
            company_schema=company,
            description=data.description,
            created_by=created_by,
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
        )
