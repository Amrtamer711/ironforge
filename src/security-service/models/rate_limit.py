"""
Rate Limiting Models.

Adapted from shared/security/rate_limit.py.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field


# =============================================================================
# DATACLASS MODELS (Internal use)
# =============================================================================

@dataclass
class RateLimitInfo:
    """Rate limit status information."""
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None  # Seconds until reset (if exceeded)


@dataclass
class RateLimitState:
    """Internal rate limit state."""
    key: str
    window_start: datetime
    request_count: int


# =============================================================================
# PYDANTIC MODELS (API Request/Response)
# =============================================================================

class RateLimitCheckRequest(BaseModel):
    """Request to check rate limit status."""
    key: str  # Rate limit key (e.g., "user:123", "ip:1.2.3.4")
    limit: int = Field(default=100, ge=1)
    window_seconds: int = Field(default=60, ge=1)


class RateLimitCheckResponse(BaseModel):
    """Response from rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None  # Seconds until reset (if exceeded)


class RateLimitIncrementRequest(BaseModel):
    """Request to increment rate limit counter."""
    key: str
    limit_per_minute: int = Field(default=100, ge=1)
    increment: int = Field(default=1, ge=1)


class RateLimitIncrementResponse(BaseModel):
    """Response from rate limit increment."""
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_at: int


class RateLimitStatusResponse(BaseModel):
    """Overall rate limit status for a key."""
    key: str
    current_count: int
    limit: int
    remaining: int
    reset_at: int
    window_start: datetime
