"""
Unified Auth Client.

Provides a single interface to interact with any auth provider.
Follows the same pattern as integrations/llm/client.py (LLMClient).
"""

import logging
import os
from typing import Any, Optional

from integrations.auth.base import (
    AuthProvider,
    AuthResult,
    AuthUser,
    TokenPayload,
)

logger = logging.getLogger("proposal-bot")

# Global auth client instance
_auth_client: Optional["AuthClient"] = None


class AuthClient:
    """
    Unified auth client that abstracts provider-specific implementations.

    Similar to LLMClient, this provides a single interface for auth operations
    regardless of the underlying provider (Supabase, Local Dev, etc.).

    Usage:
        from integrations.auth import get_auth_client

        # Get the configured client
        auth = get_auth_client()

        # Verify a token
        result = await auth.verify_token(token)
        if result.success:
            user = result.user
            print(f"Authenticated: {user.email}")

        # Get user by ID
        user = await auth.get_user_by_id("user-123")

        # List all users
        users = await auth.list_users()
    """

    def __init__(self, provider: AuthProvider):
        """
        Initialize the auth client with a provider.

        Args:
            provider: The auth provider implementation to use
        """
        self._provider = provider
        logger.info(f"[AUTH] Client initialized with provider: {provider.name}")

    @classmethod
    def from_config(cls, provider_name: Optional[str] = None) -> "AuthClient":
        """
        Create an AuthClient using configuration from environment.

        Args:
            provider_name: Which provider to use ("supabase" or "local_dev").
                          If None, uses AUTH_PROVIDER env var.

        Returns:
            Configured AuthClient instance

        Raises:
            RuntimeError: In production if AUTH_PROVIDER is not explicitly set
        """
        # Determine which provider to use
        env_provider = os.getenv("AUTH_PROVIDER")
        provider_name = provider_name or env_provider

        # In production, require explicit AUTH_PROVIDER to prevent accidental dev auth
        if not provider_name:
            environment = os.getenv("ENVIRONMENT", "local")
            if environment == "production":
                raise RuntimeError(
                    "[AUTH] AUTH_PROVIDER must be explicitly set in production. "
                    "Set AUTH_PROVIDER=supabase for production use."
                )
            # Default to local_dev only in non-production
            provider_name = "local_dev"
            logger.warning("[AUTH] AUTH_PROVIDER not set, defaulting to local_dev (non-production only)")

        if provider_name == "supabase":
            from integrations.auth.providers.supabase import SupabaseAuthProvider
            provider = SupabaseAuthProvider()
        else:
            from integrations.auth.providers.local_dev import LocalDevAuthProvider
            provider = LocalDevAuthProvider()

        return cls(provider)

    @property
    def provider(self) -> AuthProvider:
        """Access the underlying provider."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Get the name of the current provider."""
        return self._provider.name

    # =========================================================================
    # TOKEN OPERATIONS
    # =========================================================================

    async def verify_token(self, token: str) -> AuthResult:
        """
        Verify a JWT token and return the authenticated user.

        Args:
            token: JWT access token (without 'Bearer ' prefix)

        Returns:
            AuthResult with user info if valid
        """
        # Strip 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        result = await self._provider.verify_token(token)

        if result.success and result.user:
            logger.debug(f"[AUTH] Token verified for: {result.user.email}")
        else:
            logger.debug(f"[AUTH] Token verification failed: {result.error}")

        return result

    async def refresh_token(self, refresh_token: str) -> AuthResult:
        """
        Refresh an access token.

        Args:
            refresh_token: The refresh token

        Returns:
            AuthResult with new token
        """
        return await self._provider.refresh_token(refresh_token)

    async def revoke_token(self, token: str) -> bool:
        """
        Revoke/invalidate a token.

        Args:
            token: Token to revoke

        Returns:
            True if revoked
        """
        return await self._provider.revoke_token(token)

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """
        Decode a JWT token without verification.

        Useful for debugging or extracting claims.

        Args:
            token: JWT token to decode

        Returns:
            TokenPayload or None
        """
        if token.startswith("Bearer "):
            token = token[7:]
        return self._provider.decode_token(token)

    # =========================================================================
    # USER OPERATIONS
    # =========================================================================

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        """
        Get user by their ID.

        Args:
            user_id: User's unique identifier

        Returns:
            AuthUser if found
        """
        return await self._provider.get_user_by_id(user_id)

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        """
        Get user by their email.

        Args:
            email: User's email address

        Returns:
            AuthUser if found
        """
        return await self._provider.get_user_by_email(email)

    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """
        Sync authenticated user to application database.

        Should be called after successful authentication to ensure
        user exists in the local database.

        Args:
            user: Authenticated user to sync

        Returns:
            True if sync successful
        """
        return await self._provider.sync_user_to_db(user)

    async def create_user(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """
        Create a new user.

        Args:
            email: User's email
            name: User's display name
            metadata: Additional user metadata

        Returns:
            Created AuthUser or None
        """
        return await self._provider.create_user(email, name, metadata)

    async def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """
        Update user profile.

        Args:
            user_id: User's ID
            name: New display name
            avatar_url: New avatar URL
            is_active: Active status
            metadata: Updated metadata

        Returns:
            Updated AuthUser or None
        """
        return await self._provider.update_user(
            user_id, name, avatar_url, is_active, metadata
        )

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.

        Args:
            user_id: User's ID to delete

        Returns:
            True if deleted
        """
        return await self._provider.delete_user(user_id)

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        is_active: Optional[bool] = None,
    ) -> list[AuthUser]:
        """
        List users with pagination.

        Args:
            limit: Maximum number of users
            offset: Number of users to skip
            is_active: Filter by active status

        Returns:
            List of AuthUser objects
        """
        return await self._provider.list_users(limit, offset, is_active)


# =============================================================================
# MODULE-LEVEL FUNCTIONS (like integrations/channels/router.py)
# =============================================================================


def get_auth_client() -> AuthClient:
    """
    Get the global auth client instance.

    Creates one if it doesn't exist.
    """
    global _auth_client
    if _auth_client is None:
        _auth_client = AuthClient.from_config()
    return _auth_client


def set_auth_client(client: AuthClient) -> None:
    """
    Set the global auth client instance.

    Args:
        client: AuthClient to use globally
    """
    global _auth_client
    _auth_client = client
    logger.info(f"[AUTH] Global client set to: {client.provider_name}")


def reset_auth_client() -> None:
    """Reset the global auth client (mainly for testing)."""
    global _auth_client
    _auth_client = None


async def verify_token(token: str) -> AuthResult:
    """
    Convenience function to verify a token using the global client.

    Args:
        token: JWT access token

    Returns:
        AuthResult with user info
    """
    return await get_auth_client().verify_token(token)


async def get_current_user(token: str) -> Optional[AuthUser]:
    """
    Convenience function to get the current user from a token.

    Args:
        token: JWT access token

    Returns:
        AuthUser if token is valid, None otherwise
    """
    result = await verify_token(token)
    return result.user if result.success else None
