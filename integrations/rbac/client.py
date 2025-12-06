"""
Unified RBAC Client.

Provides a single interface to interact with any RBAC provider.
Follows the same pattern as integrations/llm/client.py (LLMClient)
and integrations/auth/client.py (AuthClient).
"""

import os
import logging
from typing import List, Optional, Set

from integrations.rbac.base import (
    RBACProvider,
    Role,
    Permission,
    RBACContext,
)

logger = logging.getLogger("proposal-bot")

# Global RBAC client instance
_rbac_client: Optional["RBACClient"] = None


class RBACClient:
    """
    Unified RBAC client that abstracts provider-specific implementations.

    Similar to LLMClient and AuthClient, this provides a single interface
    for RBAC operations regardless of the underlying provider.

    Usage:
        from integrations.rbac import get_rbac_client

        # Get the configured client
        rbac = get_rbac_client()

        # Check permissions
        if await rbac.has_permission(user_id, "proposals:create"):
            # User can create proposals

        # Get user roles
        roles = await rbac.get_user_roles(user_id)

        # Assign a role
        await rbac.assign_role(user_id, "admin", granted_by=admin_user_id)
    """

    def __init__(self, provider: RBACProvider):
        """
        Initialize the RBAC client with a provider.

        Args:
            provider: The RBAC provider implementation to use
        """
        self._provider = provider
        logger.info(f"[RBAC] Client initialized with provider: {provider.name}")

    @classmethod
    def from_config(cls, provider_name: Optional[str] = None) -> "RBACClient":
        """
        Create an RBACClient using configuration from environment.

        Args:
            provider_name: Which provider to use ("database" or "static").
                          If None, uses RBAC_PROVIDER env var or defaults to "static".

        Returns:
            Configured RBACClient instance
        """
        provider_name = provider_name or os.getenv("RBAC_PROVIDER", "static")

        if provider_name == "database":
            from integrations.rbac.providers.database import DatabaseRBACProvider
            provider = DatabaseRBACProvider()
        else:
            from integrations.rbac.providers.static import StaticRBACProvider
            provider = StaticRBACProvider()

        return cls(provider)

    @property
    def provider(self) -> RBACProvider:
        """Access the underlying provider."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Get the name of the current provider."""
        return self._provider.name

    # =========================================================================
    # ROLE OPERATIONS
    # =========================================================================

    async def get_user_roles(self, user_id: str) -> List[Role]:
        """
        Get all roles assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of Role objects
        """
        return await self._provider.get_user_roles(user_id)

    async def assign_role(
        self,
        user_id: str,
        role_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: User's ID
            role_name: Name of the role to assign
            granted_by: ID of user granting the role
            expires_at: Optional expiration datetime

        Returns:
            True if assigned successfully
        """
        return await self._provider.assign_role(
            user_id, role_name, granted_by, expires_at
        )

    async def revoke_role(self, user_id: str, role_name: str) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: User's ID
            role_name: Name of the role to revoke

        Returns:
            True if revoked successfully
        """
        return await self._provider.revoke_role(user_id, role_name)

    async def has_role(self, user_id: str, role_name: str) -> bool:
        """
        Check if user has a specific role.

        Args:
            user_id: User's ID
            role_name: Role to check

        Returns:
            True if user has the role
        """
        return await self._provider.has_role(user_id, role_name)

    # =========================================================================
    # PERMISSION OPERATIONS
    # =========================================================================

    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """
        Get all permissions for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Set of permission names
        """
        return await self._provider.get_user_permissions(user_id)

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: Optional[RBACContext] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User's ID
            permission: Permission to check (e.g., "proposals:create")
            context: Optional context for ownership checks

        Returns:
            True if user has the permission
        """
        return await self._provider.has_permission(user_id, permission, context)

    async def require_permission(
        self,
        user_id: str,
        permission: str,
        context: Optional[RBACContext] = None,
    ) -> None:
        """
        Require a user to have a permission. Raises exception if not.

        Args:
            user_id: User's ID
            permission: Required permission
            context: Optional context for ownership checks

        Raises:
            PermissionError: If user lacks the permission
        """
        if not await self.has_permission(user_id, permission, context):
            raise PermissionError(
                f"User {user_id} lacks required permission: {permission}"
            )

    async def require_role(self, user_id: str, role_name: str) -> None:
        """
        Require a user to have a role. Raises exception if not.

        Args:
            user_id: User's ID
            role_name: Required role

        Raises:
            PermissionError: If user lacks the role
        """
        if not await self.has_role(user_id, role_name):
            raise PermissionError(
                f"User {user_id} lacks required role: {role_name}"
            )

    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================

    async def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get a role by name.

        Args:
            role_name: Role name

        Returns:
            Role object or None
        """
        return await self._provider.get_role(role_name)

    async def list_roles(self) -> List[Role]:
        """
        List all available roles.

        Returns:
            List of Role objects
        """
        return await self._provider.list_roles()

    async def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """
        Create a new role.

        Args:
            name: Role name
            description: Role description
            permissions: List of permission names

        Returns:
            Created Role or None
        """
        return await self._provider.create_role(name, description, permissions)

    async def update_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """
        Update an existing role.

        Args:
            name: Role name
            description: New description
            permissions: New list of permissions

        Returns:
            Updated Role or None
        """
        return await self._provider.update_role(name, description, permissions)

    async def delete_role(self, name: str) -> bool:
        """
        Delete a role.

        Args:
            name: Role name

        Returns:
            True if deleted
        """
        return await self._provider.delete_role(name)

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    async def list_permissions(self) -> List[Permission]:
        """
        List all available permissions.

        Returns:
            List of Permission objects
        """
        return await self._provider.list_permissions()

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize_defaults(self) -> bool:
        """
        Initialize default roles and permissions.

        Should be called on first run.

        Returns:
            True if initialized
        """
        return await self._provider.initialize_defaults()


# =============================================================================
# MODULE-LEVEL FUNCTIONS
# =============================================================================


def get_rbac_client() -> RBACClient:
    """
    Get the global RBAC client instance.

    Creates one if it doesn't exist.
    """
    global _rbac_client
    if _rbac_client is None:
        _rbac_client = RBACClient.from_config()
    return _rbac_client


def set_rbac_client(client: RBACClient) -> None:
    """
    Set the global RBAC client instance.

    Args:
        client: RBACClient to use globally
    """
    global _rbac_client
    _rbac_client = client
    logger.info(f"[RBAC] Global client set to: {client.provider_name}")


def reset_rbac_client() -> None:
    """Reset the global RBAC client (mainly for testing)."""
    global _rbac_client
    _rbac_client = None


async def has_permission(
    user_id: str,
    permission: str,
    context: Optional[RBACContext] = None,
) -> bool:
    """
    Convenience function to check permission using global client.

    Args:
        user_id: User's ID
        permission: Permission to check
        context: Optional context

    Returns:
        True if user has the permission
    """
    return await get_rbac_client().has_permission(user_id, permission, context)


async def has_role(user_id: str, role_name: str) -> bool:
    """
    Convenience function to check role using global client.

    Args:
        user_id: User's ID
        role_name: Role to check

    Returns:
        True if user has the role
    """
    return await get_rbac_client().has_role(user_id, role_name)


async def require_permission(
    user_id: str,
    permission: str,
    context: Optional[RBACContext] = None,
) -> None:
    """
    Convenience function to require permission.

    Args:
        user_id: User's ID
        permission: Required permission
        context: Optional context

    Raises:
        PermissionError: If user lacks the permission
    """
    await get_rbac_client().require_permission(user_id, permission, context)


async def require_role(user_id: str, role_name: str) -> None:
    """
    Convenience function to require role.

    Args:
        user_id: User's ID
        role_name: Required role

    Raises:
        PermissionError: If user lacks the role
    """
    await get_rbac_client().require_role(user_id, role_name)
