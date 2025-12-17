"""
Abstract base class for authentication providers.

Each provider implements their own auth-specific syntax.
Follows the same pattern as integrations/llm/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthStatus(str, Enum):
    """Authentication status."""
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass
class AuthUser:
    """
    Platform-agnostic authenticated user representation.

    Similar to integrations/channels/base.py User dataclass.
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


@dataclass
class TokenPayload:
    """Decoded JWT token payload."""
    sub: str  # Subject (user ID)
    email: str | None = None
    exp: int | None = None  # Expiration timestamp
    iat: int | None = None  # Issued at timestamp
    aud: str | None = None  # Audience
    role: str | None = None  # Supabase role
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthResult:
    """Result from authentication operations."""
    success: bool
    user: AuthUser | None = None
    status: AuthStatus = AuthStatus.UNAUTHENTICATED
    error: str | None = None
    token: str | None = None


class AuthProvider(ABC):
    """
    Abstract base class for authentication providers.

    Each provider (Supabase, Local Dev, etc.) implements this interface
    with their own auth-specific syntax.

    Pattern follows:
    - integrations/llm/base.py (LLMProvider)
    - integrations/channels/base.py (ChannelAdapter)
    - db/base.py (DatabaseBackend)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'supabase', 'local_dev')."""
        pass

    @abstractmethod
    async def verify_token(self, token: str) -> AuthResult:
        """
        Verify a JWT token and return the authenticated user.

        Args:
            token: JWT access token (without 'Bearer ' prefix)

        Returns:
            AuthResult with user info if valid, error if not
        """
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> AuthUser | None:
        """
        Get user by their ID.

        Args:
            user_id: User's unique identifier

        Returns:
            AuthUser if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> AuthUser | None:
        """
        Get user by their email.

        Args:
            email: User's email address

        Returns:
            AuthUser if found, None otherwise
        """
        pass

    @abstractmethod
    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """
        Sync authenticated user to local database.

        Called after successful authentication to ensure user exists
        in the application database with current profile data.

        Args:
            user: Authenticated user to sync

        Returns:
            True if sync successful
        """
        pass

    @abstractmethod
    async def create_user(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthUser | None:
        """
        Create a new user in the auth system.

        For Supabase: Creates user in auth.users
        For Local Dev: Creates user in local database

        Args:
            email: User's email
            name: User's display name
            metadata: Additional user metadata

        Returns:
            Created AuthUser or None if failed
        """
        pass

    @abstractmethod
    async def update_user(
        self,
        user_id: str,
        name: str | None = None,
        avatar_url: str | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthUser | None:
        """
        Update user profile.

        Args:
            user_id: User's ID
            name: New display name
            avatar_url: New avatar URL
            is_active: Active status
            metadata: Updated metadata

        Returns:
            Updated AuthUser or None if failed
        """
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.

        Args:
            user_id: User's ID to delete

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        is_active: bool | None = None,
    ) -> list[AuthUser]:
        """
        List users with pagination.

        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            is_active: Filter by active status

        Returns:
            List of AuthUser objects
        """
        pass

    # =========================================================================
    # OPTIONAL METHODS (with default implementations)
    # =========================================================================

    async def refresh_token(self, refresh_token: str) -> AuthResult:
        """
        Refresh an access token using a refresh token.

        Default implementation returns error (not all providers support this).

        Args:
            refresh_token: The refresh token

        Returns:
            AuthResult with new token or error
        """
        return AuthResult(
            success=False,
            status=AuthStatus.INVALID,
            error=f"{self.name} does not support token refresh"
        )

    async def revoke_token(self, token: str) -> bool:
        """
        Revoke/invalidate a token.

        Default implementation returns False (not all providers support this).

        Args:
            token: Token to revoke

        Returns:
            True if revoked successfully
        """
        return False

    def decode_token(self, token: str) -> TokenPayload | None:
        """
        Decode a JWT token without verification.

        Useful for extracting claims for logging/debugging.
        Default implementation returns None.

        Args:
            token: JWT token to decode

        Returns:
            TokenPayload or None if decode fails
        """
        return None
