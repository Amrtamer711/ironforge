"""
Authentication Models.

Adapted from shared/security/models.py and shared/security/context.py.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# DATACLASS MODELS (Internal use)
# =============================================================================

@dataclass
class AuthUser:
    """
    Platform-agnostic authenticated user representation.

    Used across all services for consistent user handling.
    Adapted from shared/security/models.py.
    """
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    # Token info (if applicable)
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: str | None = None

    @property
    def companies(self) -> list[str]:
        """Get list of company schema names user has access to."""
        return self.metadata.get("companies", [])

    @property
    def permissions(self) -> list[str]:
        """Get list of user's permissions."""
        return self.metadata.get("permissions", [])

    @property
    def profile(self) -> str | None:
        """Get user's profile name."""
        return self.metadata.get("profile")

    @property
    def teams(self) -> list[dict]:
        """Get user's teams."""
        return self.metadata.get("teams", [])

    @property
    def team_ids(self) -> list[int]:
        """Get user's team IDs."""
        return self.metadata.get("team_ids", [])

    @property
    def subordinate_ids(self) -> list[str]:
        """Get user's subordinate IDs."""
        return self.metadata.get("subordinate_ids", [])

    @property
    def shared_from_user_ids(self) -> list[str]:
        """Get IDs of users who have shared records with this user."""
        return self.metadata.get("shared_from_user_ids", [])

    def can_access_company(self, company_schema: str) -> bool:
        """Check if user can access a specific company's data."""
        return company_schema in self.companies

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "metadata": self.metadata,
            "companies": self.companies,
            "profile": self.profile,
            "permissions": self.permissions,
        }


# =============================================================================
# PYDANTIC MODELS (API Request/Response)
# =============================================================================

class UserContext(BaseModel):
    """
    Full user context for RBAC.

    This is what gets returned from /auth/context endpoint.
    Follows 5-level RBAC structure.
    """
    # Level 1: Identity
    user_id: str
    email: str
    name: str | None = None
    profile: str | None = None

    # Level 2: Permissions
    permissions: list[str] = Field(default_factory=list)
    permission_sets: list[str] = Field(default_factory=list)

    # Level 3: Teams & Hierarchy
    teams: list[dict] = Field(default_factory=list)
    team_ids: list[int] = Field(default_factory=list)
    manager_id: str | None = None
    subordinate_ids: list[str] = Field(default_factory=list)

    # Level 4: Sharing
    sharing_rules: list[dict] = Field(default_factory=list)
    shared_records: dict[str, list[dict]] = Field(default_factory=dict)
    shared_from_user_ids: list[str] = Field(default_factory=list)

    # Level 5: Companies
    companies: list[str] = Field(default_factory=list)


class TokenValidationRequest(BaseModel):
    """Request to validate a JWT token."""
    token: str


class TokenValidationResponse(BaseModel):
    """Response from token validation."""
    valid: bool
    user_id: str | None = None
    email: str | None = None
    error: str | None = None


class ServiceTokenRequest(BaseModel):
    """Request for a service-to-service token."""
    service_name: str


class ServiceTokenResponse(BaseModel):
    """Response with service token."""
    token: str
    expires_in: int  # seconds


class PermissionCheckRequest(BaseModel):
    """Request to check user permission."""
    user_id: str
    permission: str
    resource_id: str | None = None
    resource_owner_id: str | None = None


class PermissionCheckResponse(BaseModel):
    """Response from permission check."""
    allowed: bool
    reason: str | None = None
