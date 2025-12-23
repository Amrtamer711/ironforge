"""
Location data models.

Pydantic models for location and pricing information.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, validator


class PricingInfo(BaseModel):
    """Pricing information for a location."""

    base_rate: Decimal = Field(description="Base rate per unit")
    upload_fee: Decimal = Field(default=Decimal("0"), description="One-time upload fee")
    currency: str = Field(default="AED", description="Currency code (AED, USD, etc.)")
    unit: str = Field(default="slot", description="Pricing unit (slot, spot, etc.)")

    class Config:
        """Pydantic config."""
        json_encoders = {Decimal: str}

    @validator("currency")
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code."""
        from core.utils.currency_formatter import validate_currency_code

        if not validate_currency_code(v):
            raise ValueError(f"Unsupported currency: {v}")
        return v.upper()

    @validator("base_rate", "upload_fee")
    def validate_positive(cls, v: Decimal) -> Decimal:
        """Validate that amounts are non-negative."""
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return v


class Location(BaseModel):
    """
    Location data model.

    Represents a billboard/advertising location with all its metadata.
    """

    location_key: str = Field(description="Unique location identifier")
    display_name: str = Field(description="Human-readable location name")
    display_type: str = Field(description="Type: 'digital' or 'static'")
    company_schema: str = Field(description="Company schema name")

    # Optional metadata
    series: str | None = Field(default=None, description="Location series/group")
    city: str | None = Field(default=None, description="City")
    area: str | None = Field(default=None, description="Area within city")

    # Status
    is_active: bool = Field(default=True, description="Whether location is active")

    # Eligibility (Phase 2)
    eligible_for_proposals: bool = Field(default=True, description="Eligible for proposals")
    eligible_for_mockups: bool = Field(default=True, description="Eligible for mockups")

    # Pricing (optional)
    pricing: PricingInfo | None = Field(default=None, description="Pricing information")

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic config."""
        json_encoders = {Decimal: str}

    @validator("display_type")
    def validate_display_type(cls, v: str) -> str:
        """Validate display type."""
        valid_types = {"digital", "static"}
        v_lower = v.lower()
        if v_lower not in valid_types:
            raise ValueError(f"Display type must be one of: {valid_types}")
        return v_lower

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Location":
        """
        Create Location from dictionary (database row).

        Args:
            data: Dictionary with location data

        Returns:
            Location instance

        Example:
            >>> loc_data = {
            ...     "location_key": "dubai_gateway",
            ...     "display_name": "The Gateway",
            ...     "display_type": "digital",
            ...     "company_schema": "backlite_dubai",
            ... }
            >>> location = Location.from_dict(loc_data)
        """
        return cls(
            location_key=data.get("location_key", ""),
            display_name=data.get("display_name", data.get("location_key", "")),
            display_type=data.get("display_type", "unknown"),
            company_schema=data.get("company_schema", "unknown"),
            series=data.get("series"),
            city=data.get("city"),
            area=data.get("area"),
            is_active=data.get("is_active", True),
            eligible_for_proposals=data.get("eligible_for_proposals", True),
            eligible_for_mockups=data.get("eligible_for_mockups", True),
            pricing=None,  # Will be populated separately if needed
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert Location to dictionary.

        Returns:
            Dictionary representation

        Example:
            >>> location = Location(location_key="dubai_gateway", ...)
            >>> data = location.to_dict()
        """
        result = {
            "location_key": self.location_key,
            "display_name": self.display_name,
            "display_type": self.display_type,
            "company_schema": self.company_schema,
            "is_active": self.is_active,
            "eligible_for_proposals": self.eligible_for_proposals,
            "eligible_for_mockups": self.eligible_for_mockups,
        }

        # Add optional fields if present
        if self.series:
            result["series"] = self.series
        if self.city:
            result["city"] = self.city
        if self.area:
            result["area"] = self.area
        if self.pricing:
            result["pricing"] = self.pricing.dict()
        if self.metadata:
            result["metadata"] = self.metadata

        return result
