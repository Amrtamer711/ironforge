"""
Packages - Schemas and service logic.

Packages are company-specific bundles of networks and/or individual assets.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.packages")


# =============================================================================
# SCHEMAS
# =============================================================================


class PackageItemBase(BaseModel):
    """Base package item fields."""

    item_type: str = Field(..., description="'network' or 'asset'")
    network_id: int | None = Field(default=None, description="Network ID (if item_type='network')")
    location_id: int | None = Field(default=None, description="Location ID (if item_type='asset')")


class PackageItem(PackageItemBase):
    """Full package item model."""

    id: int
    package_id: int
    created_at: datetime | None = None

    # Optional expanded data
    network_name: str | None = None
    location_name: str | None = None
    location_count: int | None = None  # For networks

    class Config:
        from_attributes = True


class PackageBase(BaseModel):
    """Base package fields."""

    package_key: str = Field(..., description="Unique key for the package")
    name: str = Field(..., description="Display name")
    description: str | None = Field(default=None, description="Description")


class PackageCreate(PackageBase):
    """Fields for creating a package."""

    items: list[PackageItemBase] = Field(default_factory=list, description="Initial items")


class PackageUpdate(BaseModel):
    """Fields for updating a package (all optional)."""

    package_key: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class LocationSummary(BaseModel):
    """Summary of location for expansion."""

    id: int
    location_key: str
    display_name: str
    display_type: str
    company: str


class Package(PackageBase):
    """Full package model with database fields."""

    id: int
    company: str = Field(..., description="Company schema")
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    # Package contents
    items: list[PackageItem] = Field(default_factory=list)

    # Computed
    total_location_count: int = 0

    # Optional expanded locations (when expand=True)
    expanded_locations: list[LocationSummary] | None = None

    class Config:
        from_attributes = True


# =============================================================================
# SERVICE
# =============================================================================


class PackageService:
    """Business logic for package operations."""

    def list_packages(
        self,
        companies: list[str],
        active_only: bool = True,
    ) -> list[Package]:
        """List packages across companies."""
        results = db.list_packages(
            company_schemas=companies,
            include_inactive=not active_only,
        )
        return [self._dict_to_package(r) for r in results]

    def get_package(
        self,
        company: str,
        package_id: int,
        expand_locations: bool = False,
    ) -> Package | None:
        """Get a single package with items."""
        result = db.get_package(package_id, [company])
        if not result:
            return None

        package = self._dict_to_package(result)

        # Expand locations if requested
        if expand_locations:
            locs = db.get_package_locations(package_id, company)
            package.expanded_locations = [
                LocationSummary(
                    id=loc["id"],
                    location_key=loc["location_key"],
                    display_name=loc["display_name"],
                    display_type=loc["display_type"],
                    company=loc.get("company_schema", loc.get("company", company)),
                )
                for loc in locs
            ]
            package.total_location_count = len(locs)
        else:
            # Calculate total location count from items
            package.total_location_count = self._calculate_location_count(package, company)

        return package

    def create_package(
        self,
        company: str,
        data: PackageCreate,
        created_by: str | None = None,
    ) -> Package:
        """Create a new package with optional initial items."""
        logger.info(f"Creating package '{data.name}' in {company}")

        result = db.create_package(
            package_key=data.package_key,
            name=data.name,
            company_schema=company,
            description=data.description,
            created_by=created_by,
        )

        if not result:
            raise ValueError(f"Failed to create package: {data.package_key}")

        package = self._dict_to_package(result)

        # Add initial items
        for item_data in data.items:
            db.add_package_item(
                package_id=package.id,
                item_type=item_data.item_type,
                company_schema=company,
                network_id=item_data.network_id,
                location_id=item_data.location_id,
            )

        # Refresh package with items
        return self.get_package(company, package.id) or package

    def update_package(
        self,
        company: str,
        package_id: int,
        data: PackageUpdate,
    ) -> Package | None:
        """Update an existing package."""
        logger.info(f"Updating package {package_id} in {company}")

        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if not updates:
            return self.get_package(company, package_id)

        result = db.update_package(package_id, company, updates)
        if not result:
            return None

        return self._dict_to_package(result)

    def delete_package(
        self,
        company: str,
        package_id: int,
    ) -> bool:
        """Soft delete a package."""
        logger.info(f"Deleting package {package_id} in {company}")
        return db.delete_package(package_id, company)

    def add_item(
        self,
        company: str,
        package_id: int,
        item_type: str,
        network_id: int | None = None,
        location_id: int | None = None,
    ) -> PackageItem | None:
        """Add an item to a package."""
        logger.info(f"Adding {item_type} item to package {package_id}")

        result = db.add_package_item(
            package_id=package_id,
            item_type=item_type,
            company_schema=company,
            network_id=network_id,
            location_id=location_id,
        )

        if not result:
            return None

        return self._dict_to_package_item(result)

    def remove_item(
        self,
        company: str,
        item_id: int,
    ) -> bool:
        """Remove an item from a package."""
        logger.info(f"Removing item {item_id} from package")
        return db.remove_package_item(item_id, company)

    def get_package_locations(
        self,
        company: str,
        package_id: int,
    ) -> list[LocationSummary]:
        """Get all locations in a package (expanded)."""
        locs = db.get_package_locations(package_id, company)
        return [
            LocationSummary(
                id=loc["id"],
                location_key=loc["location_key"],
                display_name=loc["display_name"],
                display_type=loc["display_type"],
                company=loc.get("company_schema", loc.get("company", company)),
            )
            for loc in locs
        ]

    def _calculate_location_count(self, package: Package, company: str) -> int:
        """Calculate total location count from package items."""
        total = 0
        for item in package.items:
            if item.item_type == "asset":
                total += 1
            elif item.item_type == "network" and item.location_count:
                total += item.location_count
        return total

    def _dict_to_package(self, data: dict[str, Any]) -> Package:
        """Convert a database dict to a Package model."""
        items = [
            self._dict_to_package_item(item)
            for item in data.get("items", [])
        ]

        return Package(
            id=data["id"],
            package_key=data["package_key"],
            name=data["name"],
            description=data.get("description"),
            company=data.get("company_schema", data.get("company", "")),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            created_by=data.get("created_by"),
            items=items,
        )

    def _dict_to_package_item(self, data: dict[str, Any]) -> PackageItem:
        """Convert a database dict to a PackageItem model."""
        return PackageItem(
            id=data["id"],
            package_id=data["package_id"],
            item_type=data["item_type"],
            network_id=data.get("network_id"),
            location_id=data.get("location_id"),
            created_at=data.get("created_at"),
            network_name=data.get("network_name"),
            location_name=data.get("location_name"),
            location_count=data.get("location_count"),
        )
