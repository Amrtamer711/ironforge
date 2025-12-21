"""
Security Data Models.

Provides platform-agnostic data models for authentication and authorization.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthUser:
    """
    Platform-agnostic authenticated user representation.

    Used across all services for consistent user handling.
    Converts from TrustedUserContext headers or auth providers.
    """
    id: str  # UUID from auth provider
    email: str
    name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    # Token info (if applicable)
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: str | None = None

    # Provider-specific IDs
    supabase_id: str | None = None
    local_id: str | None = None

    @property
    def companies(self) -> list[str]:
        """
        Get list of company schema names user has access to.

        Returns empty list if no companies assigned (user cannot access any company data).
        """
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
    def has_company_access(self) -> bool:
        """Check if user has access to at least one company."""
        return len(self.companies) > 0

    def can_access_company(self, company_schema: str) -> bool:
        """
        Check if user can access a specific company's data.

        Args:
            company_schema: The schema name (e.g., 'backlite_dubai', 'viola')

        Returns:
            True if user has access to this company
        """
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
        }

    @classmethod
    def from_context(cls, ctx: dict[str, Any]) -> "AuthUser":
        """
        Create AuthUser from user context dictionary.

        Args:
            ctx: User context from get_user_context()

        Returns:
            AuthUser instance
        """
        return cls(
            id=ctx.get("user_id", ""),
            email=ctx.get("email", ""),
            name=ctx.get("name"),
            is_active=True,
            supabase_id=ctx.get("user_id"),
            metadata={
                "profile": ctx.get("profile"),
                "permissions": ctx.get("permissions", []),
                "companies": ctx.get("companies", []),
                "teams": ctx.get("teams", []),
                "team_ids": ctx.get("team_ids", []),
                "subordinate_ids": ctx.get("subordinate_ids", []),
                "shared_from_user_ids": ctx.get("shared_from_user_ids", []),
            },
        )
