"""
Mockup data models.

Pydantic models for mockup generation and processing.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, validator


class FrameCoordinates(BaseModel):
    """
    Frame coordinates for image placement in mockup.

    Defines the rectangular area where the creative image should be placed.
    """

    x: int = Field(description="X coordinate (left)")
    y: int = Field(description="Y coordinate (top)")
    width: int = Field(description="Frame width in pixels")
    height: int = Field(description="Frame height in pixels")

    @validator("x", "y", "width", "height")
    def validate_positive(cls, v: int, field: Any) -> int:
        """Validate that coordinates are non-negative."""
        if v < 0:
            raise ValueError(f"{field.name} cannot be negative: {v}")
        if field.name in ("width", "height") and v == 0:
            raise ValueError(f"{field.name} must be greater than 0: {v}")
        return v

    def to_tuple(self) -> tuple[int, int, int, int]:
        """
        Convert to tuple format (x, y, width, height).

        Returns:
            Tuple of coordinates

        Example:
            >>> coords = FrameCoordinates(x=100, y=200, width=800, height=600)
            >>> coords.to_tuple()
            (100, 200, 800, 600)
        """
        return (self.x, self.y, self.width, self.height)

    def to_dict(self) -> dict[str, int]:
        """
        Convert to dictionary.

        Returns:
            Dictionary with x, y, width, height
        """
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_tuple(cls, coords: tuple[int, int, int, int]) -> "FrameCoordinates":
        """
        Create from tuple (x, y, width, height).

        Args:
            coords: Tuple of (x, y, width, height)

        Returns:
            FrameCoordinates instance
        """
        if len(coords) != 4:
            raise ValueError(f"Expected 4 coordinates, got {len(coords)}")
        return cls(x=coords[0], y=coords[1], width=coords[2], height=coords[3])


class MockupConfig(BaseModel):
    """
    Complete mockup configuration.

    Contains all information needed to generate a mockup.
    """

    # Required fields
    location_key: str = Field(description="Location key")
    creative_path: str | Path = Field(description="Path to creative image file")
    background_path: str | Path = Field(description="Path to background/mockup template")
    frame_coordinates: FrameCoordinates = Field(description="Where to place creative")

    # Output configuration
    output_path: str | Path | None = Field(default=None, description="Output file path")
    output_format: str = Field(default="PNG", description="Output format (PNG, JPEG)")

    # Processing options
    resize_creative: bool = Field(default=True, description="Auto-resize creative to fit frame")
    maintain_aspect_ratio: bool = Field(default=True, description="Maintain aspect ratio when resizing")
    quality: int = Field(default=95, description="Output quality (1-100)")

    # Metadata
    user_id: int | None = Field(default=None, description="User ID")
    display_name: str | None = Field(default=None, description="Location display name")
    company_schema: str | None = Field(default=None, description="Company schema")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True

    @validator("creative_path", "background_path", "output_path", pre=True)
    def validate_path(cls, v: Any, field: Any) -> Path:
        """Convert string paths to Path objects and validate."""
        if v is None and field.name == "output_path":
            return None
        if isinstance(v, str):
            v = Path(v)
        if not isinstance(v, Path):
            raise ValueError(f"{field.name} must be a valid path")
        return v

    @validator("output_format")
    def validate_output_format(cls, v: str) -> str:
        """Validate output format."""
        valid_formats = {"PNG", "JPEG", "JPG"}
        v_upper = v.upper()
        if v_upper not in valid_formats:
            raise ValueError(f"Output format must be one of: {valid_formats}")
        # Normalize JPG to JPEG
        return "JPEG" if v_upper == "JPG" else v_upper

    @validator("quality")
    def validate_quality(cls, v: int) -> int:
        """Validate quality is between 1-100."""
        if not 1 <= v <= 100:
            raise ValueError(f"Quality must be between 1-100, got {v}")
        return v

    @validator("frame_coordinates", pre=True)
    def parse_frame_coordinates(cls, v: Any) -> FrameCoordinates:
        """Parse frame coordinates from various formats."""
        if isinstance(v, FrameCoordinates):
            return v
        if isinstance(v, dict):
            return FrameCoordinates(**v)
        if isinstance(v, (list, tuple)) and len(v) == 4:
            return FrameCoordinates.from_tuple(tuple(v))
        raise ValueError(f"Invalid frame coordinates format: {v}")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "location_key": self.location_key,
            "creative_path": str(self.creative_path),
            "background_path": str(self.background_path),
            "frame_coordinates": self.frame_coordinates.to_dict(),
            "output_path": str(self.output_path) if self.output_path else None,
            "output_format": self.output_format,
            "resize_creative": self.resize_creative,
            "maintain_aspect_ratio": self.maintain_aspect_ratio,
            "quality": self.quality,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "company_schema": self.company_schema,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockupConfig":
        """
        Create MockupConfig from dictionary.

        Args:
            data: Dictionary with mockup configuration

        Returns:
            MockupConfig instance
        """
        return cls(**data)
