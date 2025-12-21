"""
API Key Models.

Adapted from shared/security/api_keys.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

class APIKeyScope(str, Enum):
    """API key access scopes."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    PROPOSALS = "proposals"
    MOCKUPS = "mockups"
    ASSETS = "assets"


# =============================================================================
# DATACLASS MODELS (Internal use)
# =============================================================================

@dataclass
class APIKeyInfo:
    """
    Information about a validated API key.

    Adapted from shared/security/api_keys.py.
    """
    key_id: str
    client_name: str
    scopes: list[APIKeyScope] = field(default_factory=list)
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    rate_limit_per_minute: int | None = None
    rate_limit_per_day: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if key has a specific scope."""
        # Admin scope implies all other scopes
        if APIKeyScope.ADMIN in self.scopes:
            return True
        # Write scope implies read
        if scope == APIKeyScope.READ and APIKeyScope.WRITE in self.scopes:
            return True
        return scope in self.scopes


# =============================================================================
# PYDANTIC MODELS (API Request/Response)
# =============================================================================

class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    scopes: list[APIKeyScope] = Field(default_factory=lambda: [APIKeyScope.READ])
    allowed_services: list[str] | None = None  # None = all services
    allowed_ips: list[str] | None = None  # None = all IPs
    rate_limit_per_minute: int = Field(default=100, ge=1)
    rate_limit_per_day: int = Field(default=10000, ge=1)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class APIKeyCreateResponse(BaseModel):
    """
    Response after creating an API key.

    IMPORTANT: The raw_key is only returned ONCE at creation time.
    """
    id: str
    name: str
    key_prefix: str  # First 8 chars for identification
    raw_key: str  # Full key - only shown once!
    scopes: list[str]
    created_at: datetime


class APIKeyResponse(BaseModel):
    """API key info returned from API (no raw key)."""
    id: str
    name: str
    description: str | None = None
    key_prefix: str
    scopes: list[str]
    allowed_services: list[str] | None = None
    allowed_ips: list[str] | None = None
    rate_limit_per_minute: int
    rate_limit_per_day: int
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    use_count: int = 0
    created_at: datetime
    created_by: str | None = None


class APIKeyUpdateRequest(BaseModel):
    """Request to update an API key."""
    name: str | None = None
    description: str | None = None
    scopes: list[APIKeyScope] | None = None
    allowed_services: list[str] | None = None
    allowed_ips: list[str] | None = None
    rate_limit_per_minute: int | None = None
    rate_limit_per_day: int | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class APIKeyValidateRequest(BaseModel):
    """Request to validate an API key."""
    api_key: str


class APIKeyValidateResponse(BaseModel):
    """Response from API key validation."""
    valid: bool
    key_id: str | None = None
    client_name: str | None = None
    scopes: list[str] = Field(default_factory=list)
    error: str | None = None


class APIKeyListResponse(BaseModel):
    """Paginated list of API keys."""
    items: list[APIKeyResponse]
    total: int


class APIKeyUsageResponse(BaseModel):
    """API key usage statistics."""
    key_id: str
    total_requests: int
    requests_today: int
    requests_this_hour: int
    last_used_at: datetime | None = None
    top_endpoints: list[dict[str, Any]] = Field(default_factory=list)
