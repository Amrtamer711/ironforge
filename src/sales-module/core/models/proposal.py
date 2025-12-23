"""
Proposal data models.

Pydantic models for proposal generation and processing.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, validator


class ProposalLocation(BaseModel):
    """
    A location entry in a proposal.

    Represents a single location with its pricing and campaign details.
    """

    location: str = Field(description="Location key or display name")
    location_key: str | None = Field(default=None, description="Resolved location key")
    start_date: date | str = Field(description="Campaign start date")
    durations: list[int] = Field(description="Campaign durations in weeks")
    spots: int = Field(default=14, description="Number of spots per week")
    rate: Decimal | float | str = Field(description="Rate per unit")
    upload_fee: Decimal | float | str = Field(default=Decimal("0"), description="Upload fee")
    currency: str = Field(default="AED", description="Currency code")

    # Metadata
    display_name: str | None = Field(default=None, description="Location display name")
    display_type: str | None = Field(default=None, description="Display type")
    company_schema: str | None = Field(default=None, description="Company schema")

    class Config:
        """Pydantic config."""
        json_encoders = {
            Decimal: str,
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
        }

    @validator("start_date", pre=True)
    def parse_date(cls, v: Any) -> date:
        """Parse start date from various formats."""
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            # Try common formats
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Invalid date format: {v}")
        raise ValueError(f"Cannot parse date from: {v}")

    @validator("rate", "upload_fee", pre=True)
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse decimal from various formats."""
        from core.utils.currency_formatter import convert_to_decimal
        return convert_to_decimal(v)

    @validator("durations")
    def validate_durations(cls, v: list[int]) -> list[int]:
        """Validate durations list."""
        if not v:
            raise ValueError("Durations cannot be empty")
        for duration in v:
            if duration <= 0:
                raise ValueError(f"Duration must be positive: {duration}")
        return v

    @validator("spots")
    def validate_spots(cls, v: int) -> int:
        """Validate spots count."""
        if v <= 0:
            raise ValueError(f"Spots must be positive: {v}")
        return v


class Proposal(BaseModel):
    """
    Complete proposal data structure.

    Represents a full proposal request from the LLM or API.
    """

    # Required fields
    locations: list[ProposalLocation] = Field(description="List of proposal locations")
    client_name: str | None = Field(default=None, description="Client name")

    # Optional fields
    payment_terms: str | None = Field(default=None, description="Payment terms")
    currency: str = Field(default="AED", description="Default currency")
    user_id: int | None = Field(default=None, description="User ID")

    # Processing options
    package_mode: str = Field(default="separate", description="Mode: 'combined' or 'separate'")
    intro_slide_path: str | None = Field(default=None, description="Path to intro slide template")
    outro_slide_path: str | None = Field(default=None, description="Path to outro slide template")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic config."""
        json_encoders = {
            Decimal: str,
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
        }

    @validator("package_mode")
    def validate_package_mode(cls, v: str) -> str:
        """Validate package mode."""
        valid_modes = {"combined", "separate"}
        v_lower = v.lower()
        if v_lower not in valid_modes:
            raise ValueError(f"Package mode must be one of: {valid_modes}")
        return v_lower

    @validator("locations")
    def validate_locations_not_empty(cls, v: list[ProposalLocation]) -> list[ProposalLocation]:
        """Validate locations list is not empty."""
        if not v:
            raise ValueError("Proposal must have at least one location")
        return v

    def to_dict(self) -> dict[str, Any]:
        """
        Convert Proposal to dictionary.

        Returns:
            Dictionary representation suitable for processing
        """
        return {
            "locations": [loc.dict() for loc in self.locations],
            "client_name": self.client_name,
            "payment_terms": self.payment_terms,
            "currency": self.currency,
            "user_id": self.user_id,
            "package_mode": self.package_mode,
            "intro_slide_path": self.intro_slide_path,
            "outro_slide_path": self.outro_slide_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_llm_tool_call(cls, tool_data: dict[str, Any]) -> "Proposal":
        """
        Create Proposal from LLM tool call data.

        Args:
            tool_data: Raw tool call data from LLM

        Returns:
            Validated Proposal instance

        Example:
            >>> tool_data = {
            ...     "proposals": [
            ...         {
            ...             "location": "dubai_gateway",
            ...             "start_date": "2025-01-01",
            ...             "durations": [4, 8],
            ...             "rate": "1500.00",
            ...         }
            ...     ],
            ...     "client_name": "ABC Corp",
            ... }
            >>> proposal = Proposal.from_llm_tool_call(tool_data)
        """
        # Extract proposals array
        proposals_array = tool_data.get("proposals", [])
        if not proposals_array:
            raise ValueError("No proposals found in tool data")

        # Create ProposalLocation instances
        locations = [ProposalLocation(**loc) for loc in proposals_array]

        # Extract metadata
        return cls(
            locations=locations,
            client_name=tool_data.get("client_name"),
            payment_terms=tool_data.get("payment_terms"),
            currency=tool_data.get("currency", "AED"),
            package_mode=tool_data.get("package_mode", "separate"),
            intro_slide_path=tool_data.get("intro_slide_path"),
            outro_slide_path=tool_data.get("outro_slide_path"),
        )
