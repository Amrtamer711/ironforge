"""
API Request/Response Schemas.

Centralized Pydantic models for API input validation.
All POST/PUT endpoints should use these models for type-safe validation.
"""

import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS
# =============================================================================


class TimeOfDay(str, Enum):
    """Valid time of day options for mockups."""
    DAY = "day"
    NIGHT = "night"
    ALL = "all"


class FinishType(str, Enum):
    """Valid finish types for mockups."""
    GOLD = "gold"
    SILVER = "silver"
    ALL = "all"


class CallType(str, Enum):
    """Valid AI call types for cost tracking."""
    CLASSIFICATION = "classification"
    PARSING = "parsing"
    COORDINATOR_THREAD = "coordinator_thread"
    MAIN_LLM = "main_llm"
    IMAGE_GENERATION = "image_generation"
    VISION = "vision"


class Workflow(str, Enum):
    """Valid workflow types for cost tracking."""
    MOCKUP_UPLOAD = "mockup_upload"
    MOCKUP_AI = "mockup_ai"
    BO_PARSING = "bo_parsing"
    BO_EDITING = "bo_editing"
    BO_REVISION = "bo_revision"
    PROPOSAL_GENERATION = "proposal_generation"
    GENERAL_CHAT = "general_chat"
    LOCATION_MANAGEMENT = "location_management"


# =============================================================================
# MOCKUP SCHEMAS
# =============================================================================


class FramePoint(BaseModel):
    """A single coordinate point [x, y]."""
    x: float = Field(..., ge=0, description="X coordinate")
    y: float = Field(..., ge=0, description="Y coordinate")

    @classmethod
    def from_list(cls, coords: List[float]) -> "FramePoint":
        """Create from [x, y] list."""
        if len(coords) != 2:
            raise ValueError("Point must have exactly 2 coordinates [x, y]")
        return cls(x=coords[0], y=coords[1])


class FrameConfig(BaseModel):
    """Configuration for frame effects."""
    edge_blend: Optional[float] = Field(None, ge=0, le=1, description="Edge blend amount 0-1")
    depth_enabled: Optional[bool] = Field(None, description="Enable depth effect")
    vignette_amount: Optional[float] = Field(None, ge=0, le=1, description="Vignette amount 0-1")
    shadow_opacity: Optional[float] = Field(None, ge=0, le=1, description="Shadow opacity 0-1")
    brightness: Optional[float] = Field(None, ge=0, le=2, description="Brightness adjustment 0-2")
    contrast: Optional[float] = Field(None, ge=0, le=2, description="Contrast adjustment 0-2")
    saturation: Optional[float] = Field(None, ge=0, le=2, description="Saturation adjustment 0-2")
    blur_amount: Optional[float] = Field(None, ge=0, le=20, description="Blur amount in pixels")
    sharpen_amount: Optional[float] = Field(None, ge=0, le=5, description="Sharpen amount")

    class Config:
        extra = "allow"  # Allow additional config options


class FrameData(BaseModel):
    """A single frame with points and optional config."""
    points: List[List[float]] = Field(..., min_length=4, max_length=4, description="4 corner points")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Frame-specific config")

    @field_validator("points")
    @classmethod
    def validate_points(cls, v):
        """Validate that each point is [x, y] format."""
        for i, point in enumerate(v):
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"Point {i} must be [x, y] format, got {point}")
            if not all(isinstance(coord, (int, float)) for coord in point):
                raise ValueError(f"Point {i} coordinates must be numbers")
            if any(coord < 0 for coord in point):
                raise ValueError(f"Point {i} coordinates cannot be negative")
        return v


class MockupGenerateRequest(BaseModel):
    """Request for mockup generation."""
    location_key: str = Field(..., min_length=1, max_length=100, description="Location identifier")
    time_of_day: TimeOfDay = Field(default=TimeOfDay.ALL, description="Time of day variant")
    finish: FinishType = Field(default=FinishType.ALL, description="Finish type variant")
    ai_prompt: Optional[str] = Field(None, max_length=2000, description="AI prompt for generation")
    specific_photo: Optional[str] = Field(None, max_length=255, description="Specific photo filename")
    frame_config: Optional[Dict[str, Any]] = Field(None, description="Override frame config")

    @field_validator("ai_prompt")
    @classmethod
    def sanitize_prompt(cls, v):
        """Basic sanitization of AI prompt."""
        if v:
            # Remove any control characters
            v = "".join(char for char in v if ord(char) >= 32 or char in "\n\t")
        return v


class SaveFrameRequest(BaseModel):
    """Request to save a mockup frame."""
    location_key: str = Field(..., min_length=1, max_length=100)
    time_of_day: TimeOfDay = Field(default=TimeOfDay.DAY)
    finish: FinishType = Field(default=FinishType.GOLD)
    frames: List[FrameData] = Field(..., min_length=1, description="List of frames with points")
    config: Optional[Dict[str, Any]] = Field(None, description="Global config for all frames")


# =============================================================================
# COSTS SCHEMAS
# =============================================================================


class CostsFilterRequest(BaseModel):
    """Query parameters for costs endpoint."""
    start_date: Optional[str] = Field(None, description="Start date (ISO format YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (ISO format YYYY-MM-DD)")
    call_type: Optional[CallType] = Field(None, description="Filter by call type")
    workflow: Optional[Workflow] = Field(None, description="Filter by workflow")
    filter_user_id: Optional[str] = Field(None, max_length=100, description="Filter by user ID")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v):
        """Validate ISO date format."""
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format")
        return v


# =============================================================================
# SLACK SCHEMAS (for internal use, Slack payloads are verified by signature)
# =============================================================================


class SlackEventPayload(BaseModel):
    """Slack Events API payload."""
    type: str
    token: Optional[str] = None
    challenge: Optional[str] = None
    team_id: Optional[str] = None
    event: Optional[Dict[str, Any]] = None
    event_id: Optional[str] = None
    event_time: Optional[int] = None

    class Config:
        extra = "allow"


class SlackInteractivePayload(BaseModel):
    """Slack interactive component payload."""
    type: str
    user: Dict[str, Any]
    trigger_id: Optional[str] = None
    response_url: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    view: Optional[Dict[str, Any]] = None
    container: Optional[Dict[str, Any]] = None
    channel: Optional[Dict[str, Any]] = None
    message: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


# =============================================================================
# FILE UPLOAD VALIDATION
# =============================================================================

# Maximum file sizes in bytes
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024  # 100MB

# Allowed MIME types
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
}

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
}


def validate_image_upload(content_type: Optional[str], file_size: int) -> None:
    """
    Validate an uploaded image file.

    Raises:
        ValueError: If validation fails
    """
    if content_type and content_type.lower() not in ALLOWED_IMAGE_TYPES:
        raise ValueError(
            f"Invalid image type: {content_type}. "
            f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

    if file_size > MAX_IMAGE_SIZE:
        raise ValueError(
            f"Image too large: {file_size / 1024 / 1024:.1f}MB. "
            f"Maximum: {MAX_IMAGE_SIZE / 1024 / 1024:.0f}MB"
        )


def validate_document_upload(content_type: Optional[str], file_size: int) -> None:
    """
    Validate an uploaded document file.

    Raises:
        ValueError: If validation fails
    """
    if content_type and content_type.lower() not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError(
            f"Invalid document type: {content_type}. "
            f"Allowed: {', '.join(ALLOWED_DOCUMENT_TYPES)}"
        )

    if file_size > MAX_DOCUMENT_SIZE:
        raise ValueError(
            f"Document too large: {file_size / 1024 / 1024:.1f}MB. "
            f"Maximum: {MAX_DOCUMENT_SIZE / 1024 / 1024:.0f}MB"
        )
