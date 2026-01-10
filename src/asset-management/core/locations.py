"""
Locations - Schemas and service logic.

Locations are sellable entities shown in the locations VIEW.

After migration 02_unify_standalone, all sellable entities are networks,
so the locations VIEW simply exposes networks in a flat format.
This provides a unified interface for the frontend.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

import config
from db.database import db

logger = config.get_logger("core.locations")


# =============================================================================
# SCHEMAS
# =============================================================================


class LocationBase(BaseModel):
    """Base location fields.

    After unification, all locations are networks (standalone or traditional).
    The VIEW exposes them in a flat format for the frontend.
    """

    location_key: str = Field(..., description="Unique key for the location (network_key)")
    display_name: str = Field(..., description="Display name")
    display_type: str = Field(..., description="'digital' or 'static'")

    # Network reference (points to self in unified VIEW)
    network_id: int | None = Field(default=None, description="Network ID")
    type_id: int | None = Field(default=None, description="Asset type ID (NULL in VIEW)")

    # Specifications
    series: str | None = None
    height: str | None = None
    width: str | None = None
    number_of_faces: int = 1
    spot_duration: int | None = None
    loop_duration: int | None = None
    sov_percent: Decimal | None = None
    upload_fee: Decimal | None = None

    # Location info
    address: str | None = None
    city: str | None = None
    area: str | None = None
    country: str | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None

    # Template
    template_path: str | None = None

    # Notes
    notes: str | None = None


class LocationCreate(LocationBase):
    """Fields for creating a location."""

    pass


class LocationUpdate(BaseModel):
    """Fields for updating a location (all optional)."""

    location_key: str | None = None
    display_name: str | None = None
    display_type: str | None = None
    network_id: int | None = None
    type_id: int | None = None
    series: str | None = None
    height: str | None = None
    width: str | None = None
    number_of_faces: int | None = None
    spot_duration: int | None = None
    loop_duration: int | None = None
    sov_percent: Decimal | None = None
    upload_fee: Decimal | None = None
    address: str | None = None
    city: str | None = None
    area: str | None = None
    country: str | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None
    template_path: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class Location(LocationBase):
    """Full location model with database fields."""

    id: int
    company: str = Field(..., description="Company schema")
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    # Optional nested/computed data
    network_name: str | None = None
    type_name: str | None = None

    # Eligibility (computed based on field completion)
    service_eligibility: dict[str, bool] | None = None

    class Config:
        from_attributes = True


# =============================================================================
# SERVICE
# =============================================================================


class LocationService:
    """Business logic for location operations."""

    def list_locations(
        self,
        companies: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        active_only: bool = True,
        include_eligibility: bool = False,
    ) -> list[Location]:
        """List locations across companies."""
        results = db.list_locations(
            company_schemas=companies,
            network_id=network_id,
            type_id=type_id,
            include_inactive=not active_only,
        )

        locations = [self._dict_to_location(r) for r in results]

        # Add eligibility if requested
        if include_eligibility:
            for loc in locations:
                eligibility = db.check_location_eligibility(loc.id, [loc.company])
                loc.service_eligibility = eligibility.get("service_eligibility", {})

        return locations

    def get_location(
        self,
        company: str,
        location_id: int,
        include_eligibility: bool = True,
    ) -> Location | None:
        """Get a single location."""
        result = db.get_location(location_id, [company])
        if not result:
            return None

        location = self._dict_to_location(result)

        # Add eligibility
        if include_eligibility:
            eligibility = db.check_location_eligibility(location_id, [company])
            location.service_eligibility = eligibility.get("service_eligibility", {})

        return location

    def get_location_by_key(
        self,
        location_key: str,
        companies: list[str],
        include_eligibility: bool = True,
    ) -> Location | None:
        """Get a location by its key."""
        result = db.get_location_by_key(location_key, companies)
        if not result:
            return None

        location = self._dict_to_location(result)

        if include_eligibility:
            company = result.get("company_schema", result.get("company", ""))
            eligibility = db.check_location_eligibility(location.id, [company])
            location.service_eligibility = eligibility.get("service_eligibility", {})

        return location

    def create_location(
        self,
        company: str,
        data: LocationCreate,
        created_by: str | None = None,
    ) -> Location:
        """Create a new location."""
        logger.info(f"Creating location '{data.display_name}' in {company}")

        # Prepare kwargs for optional fields
        kwargs = {}
        optional_fields = [
            "series", "height", "width", "number_of_faces", "spot_duration",
            "loop_duration", "sov_percent", "upload_fee", "address", "city",
            "area", "country", "gps_lat", "gps_lng", "template_path", "notes"
        ]
        for field in optional_fields:
            value = getattr(data, field, None)
            if value is not None:
                # Convert Decimal to float for database
                if isinstance(value, Decimal):
                    value = float(value)
                kwargs[field] = value

        result = db.create_location(
            location_key=data.location_key,
            display_name=data.display_name,
            display_type=data.display_type,
            company_schema=company,
            network_id=data.network_id,
            type_id=data.type_id,
            created_by=created_by,
            **kwargs,
        )

        if not result:
            raise ValueError(f"Failed to create location: {data.location_key}")

        return self._dict_to_location(result)

    def update_location(
        self,
        company: str,
        location_id: int,
        data: LocationUpdate,
    ) -> Location | None:
        """Update an existing location."""
        logger.info(f"Updating location {location_id} in {company}")

        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if not updates:
            return self.get_location(company, location_id, include_eligibility=False)

        # Convert Decimal to float for database
        for key, value in updates.items():
            if isinstance(value, Decimal):
                updates[key] = float(value)

        result = db.update_location(location_id, company, updates)
        if not result:
            return None

        return self._dict_to_location(result)

    def delete_location(
        self,
        company: str,
        location_id: int,
    ) -> bool:
        """Soft delete a location."""
        logger.info(f"Deleting location {location_id} in {company}")
        return db.delete_location(location_id, company)

    def _dict_to_location(self, data: dict[str, Any]) -> Location:
        """Convert a database dict to a Location model."""
        return Location(
            id=data["id"],
            location_key=data["location_key"],
            display_name=data["display_name"],
            display_type=data["display_type"],
            network_id=data.get("network_id"),
            type_id=data.get("type_id"),
            series=data.get("series"),
            height=data.get("height"),
            width=data.get("width"),
            number_of_faces=data.get("number_of_faces") or 1,
            spot_duration=data.get("spot_duration"),
            loop_duration=data.get("loop_duration"),
            sov_percent=data.get("sov_percent"),
            upload_fee=data.get("upload_fee"),
            address=data.get("address"),
            city=data.get("city"),
            area=data.get("area"),
            country=data.get("country"),
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
