"""
Unified RBAC Client.

Provides a single interface to interact with any RBAC provider.
Follows the same pattern as integrations/llm/client.py (LLMClient)
and integrations/auth/client.py (AuthClient).

Enterprise RBAC with 4 levels:
- Level 1: Profiles (base permission templates)
- Level 2: Permission Sets (additive permissions)
- Level 3: Teams & Hierarchy
- Level 4: Record-Level Sharing
"""

import os
import logging
from typing import List, Optional, Set

from integrations.rbac.base import (
    RBACProvider,
    Permission,
    Profile,
    PermissionSet,
    Team,
    TeamMember,
    TeamRole,
    SharingRule,
    RecordShare,
    AccessLevel,
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

        # Check permissions (format: module:resource:action)
        if await rbac.has_permission(user_id, "sales:proposals:create"):
            # User can create proposals

        # Get user profile
        profile = await rbac.get_user_profile(user_id)

        # Assign a permission set
        await rbac.assign_permission_set(user_id, "api_access", granted_by=admin_user_id)
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
    # LEVEL 1: PROFILE OPERATIONS
    # =========================================================================

    async def get_user_profile(self, user_id: str) -> Optional[Profile]:
        """
        Get the profile assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Profile object or None
        """
        return await self._provider.get_user_profile(user_id)

    async def assign_profile(self, user_id: str, profile_name: str) -> bool:
        """
        Assign a profile to a user.

        Args:
            user_id: User's ID
            profile_name: Name of the profile to assign

        Returns:
            True if assigned successfully
        """
        return await self._provider.assign_profile(user_id, profile_name)

    async def get_profile(self, profile_name: str) -> Optional[Profile]:
        """
        Get a profile by name.

        Args:
            profile_name: Profile name

        Returns:
            Profile object or None
        """
        return await self._provider.get_profile(profile_name)

    async def list_profiles(self) -> List[Profile]:
        """
        List all available profiles.

        Returns:
            List of Profile objects
        """
        return await self._provider.list_profiles()

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        """
        Create a new profile.

        Args:
            name: Profile name
            display_name: Display name
            description: Description
            permissions: List of permission names

        Returns:
            Created Profile or None
        """
        return await self._provider.create_profile(name, display_name, description, permissions)

    async def update_profile(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        """
        Update an existing profile.

        Args:
            name: Profile name
            display_name: New display name
            description: New description
            permissions: New list of permissions

        Returns:
            Updated Profile or None
        """
        return await self._provider.update_profile(name, display_name, description, permissions)

    async def delete_profile(self, name: str) -> bool:
        """
        Delete a profile.

        Args:
            name: Profile name

        Returns:
            True if deleted
        """
        return await self._provider.delete_profile(name)

    # =========================================================================
    # LEVEL 2: PERMISSION SET OPERATIONS
    # =========================================================================

    async def get_user_permission_sets(self, user_id: str) -> List[PermissionSet]:
        """
        Get all permission sets assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of PermissionSet objects
        """
        return await self._provider.get_user_permission_sets(user_id)

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """
        Assign a permission set to a user.

        Args:
            user_id: User's ID
            permission_set_name: Name of the permission set
            granted_by: ID of user granting
            expires_at: Optional expiration datetime

        Returns:
            True if assigned successfully
        """
        return await self._provider.assign_permission_set(
            user_id, permission_set_name, granted_by, expires_at
        )

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        """
        Revoke a permission set from a user.

        Args:
            user_id: User's ID
            permission_set_name: Name of the permission set

        Returns:
            True if revoked successfully
        """
        return await self._provider.revoke_permission_set(user_id, permission_set_name)

    async def get_permission_set(self, name: str) -> Optional[PermissionSet]:
        """
        Get a permission set by name.

        Args:
            name: Permission set name

        Returns:
            PermissionSet object or None
        """
        return await self._provider.get_permission_set(name)

    async def list_permission_sets(self) -> List[PermissionSet]:
        """
        List all available permission sets.

        Returns:
            List of PermissionSet objects
        """
        return await self._provider.list_permission_sets()

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[PermissionSet]:
        """
        Create a new permission set.

        Args:
            name: Permission set name
            display_name: Display name
            description: Description
            permissions: List of permission names

        Returns:
            Created PermissionSet or None
        """
        return await self._provider.create_permission_set(name, display_name, description, permissions)

    async def update_permission_set(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PermissionSet]:
        """
        Update an existing permission set.

        Args:
            name: Permission set name
            display_name: New display name
            description: New description
            permissions: New list of permissions
            is_active: Active status

        Returns:
            Updated PermissionSet or None
        """
        return await self._provider.update_permission_set(
            name, display_name, description, permissions, is_active
        )

    async def delete_permission_set(self, name: str) -> bool:
        """
        Delete a permission set.

        Args:
            name: Permission set name

        Returns:
            True if deleted
        """
        return await self._provider.delete_permission_set(name)

    # =========================================================================
    # LEVEL 3: TEAM OPERATIONS
    # =========================================================================

    async def get_user_teams(self, user_id: str) -> List[Team]:
        """
        Get all teams a user belongs to.

        Args:
            user_id: User's unique identifier

        Returns:
            List of Team objects
        """
        return await self._provider.get_user_teams(user_id)

    async def add_user_to_team(
        self,
        user_id: str,
        team_id: int,
        role: TeamRole = TeamRole.MEMBER,
    ) -> bool:
        """
        Add a user to a team.

        Args:
            user_id: User's ID
            team_id: Team ID
            role: Role in the team (member or leader)

        Returns:
            True if added successfully
        """
        return await self._provider.add_user_to_team(user_id, team_id, role)

    async def remove_user_from_team(self, user_id: str, team_id: int) -> bool:
        """
        Remove a user from a team.

        Args:
            user_id: User's ID
            team_id: Team ID

        Returns:
            True if removed successfully
        """
        return await self._provider.remove_user_from_team(user_id, team_id)

    async def get_team(self, team_id: int) -> Optional[Team]:
        """
        Get a team by ID.

        Args:
            team_id: Team ID

        Returns:
            Team object or None
        """
        return await self._provider.get_team(team_id)

    async def get_team_by_name(self, name: str) -> Optional[Team]:
        """
        Get a team by name.

        Args:
            name: Team name

        Returns:
            Team object or None
        """
        return await self._provider.get_team_by_name(name)

    async def list_teams(self) -> List[Team]:
        """
        List all teams.

        Returns:
            List of Team objects
        """
        return await self._provider.list_teams()

    async def get_team_members(self, team_id: int) -> List[TeamMember]:
        """
        Get all members of a team.

        Args:
            team_id: Team ID

        Returns:
            List of TeamMember objects
        """
        return await self._provider.get_team_members(team_id)

    async def create_team(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
    ) -> Optional[Team]:
        """
        Create a new team.

        Args:
            name: Team name
            display_name: Display name
            description: Description
            parent_team_id: Parent team for hierarchy

        Returns:
            Created Team or None
        """
        return await self._provider.create_team(name, display_name, description, parent_team_id)

    async def update_team(
        self,
        team_id: int,
        name: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Team]:
        """
        Update an existing team.

        Args:
            team_id: Team ID
            name: New name
            display_name: New display name
            description: New description
            parent_team_id: New parent team
            is_active: Active status

        Returns:
            Updated Team or None
        """
        return await self._provider.update_team(
            team_id, name, display_name, description, parent_team_id, is_active
        )

    async def delete_team(self, team_id: int) -> bool:
        """
        Delete a team.

        Args:
            team_id: Team ID

        Returns:
            True if deleted
        """
        return await self._provider.delete_team(team_id)

    # =========================================================================
    # LEVEL 4: RECORD SHARING OPERATIONS
    # =========================================================================

    async def share_record(
        self,
        object_type: str,
        record_id: str,
        shared_by: str,
        shared_with_user_id: Optional[str] = None,
        shared_with_team_id: Optional[int] = None,
        access_level: AccessLevel = AccessLevel.READ,
        expires_at: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[RecordShare]:
        """
        Share a record with a user or team.

        Args:
            object_type: Type of record (e.g., "proposal")
            record_id: ID of the record
            shared_by: User sharing the record
            shared_with_user_id: User to share with
            shared_with_team_id: Team to share with
            access_level: Level of access
            expires_at: Optional expiration
            reason: Reason for sharing

        Returns:
            Created RecordShare or None
        """
        return await self._provider.share_record(
            object_type, record_id, shared_by,
            shared_with_user_id, shared_with_team_id,
            access_level, expires_at, reason
        )

    async def revoke_record_share(self, share_id: int) -> bool:
        """
        Revoke a record share.

        Args:
            share_id: Share ID

        Returns:
            True if revoked successfully
        """
        return await self._provider.revoke_record_share(share_id)

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> List[RecordShare]:
        """
        Get all shares for a record.

        Args:
            object_type: Type of record
            record_id: ID of the record

        Returns:
            List of RecordShare objects
        """
        return await self._provider.get_record_shares(object_type, record_id)

    async def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        required_access: AccessLevel = AccessLevel.READ,
    ) -> bool:
        """
        Check if user has access to a specific record.

        Args:
            user_id: User's ID
            object_type: Type of record
            record_id: ID of the record
            required_access: Minimum access level required

        Returns:
            True if user has access
        """
        return await self._provider.check_record_access(
            user_id, object_type, record_id, required_access
        )

    async def list_sharing_rules(self, object_type: Optional[str] = None) -> List[SharingRule]:
        """
        List sharing rules.

        Args:
            object_type: Optional filter by object type

        Returns:
            List of SharingRule objects
        """
        return await self._provider.list_sharing_rules(object_type)

    async def create_sharing_rule(
        self,
        name: str,
        object_type: str,
        share_from_type: str,
        share_to_type: str,
        access_level: AccessLevel,
        share_from_id: Optional[str] = None,
        share_to_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[SharingRule]:
        """
        Create a sharing rule.

        Args:
            name: Rule name
            object_type: Type of records
            share_from_type: "owner", "profile", or "team"
            share_to_type: "profile", "team", or "all"
            access_level: Level of access
            share_from_id: ID for profile/team
            share_to_id: ID for profile/team
            description: Rule description

        Returns:
            Created SharingRule or None
        """
        return await self._provider.create_sharing_rule(
            name, object_type, share_from_type, share_to_type,
            access_level, share_from_id, share_to_id, description
        )

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        """
        Delete a sharing rule.

        Args:
            rule_id: Rule ID

        Returns:
            True if deleted
        """
        return await self._provider.delete_sharing_rule(rule_id)

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
        Initialize default profiles and permission sets.

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


# =============================================================================
# CHANNEL IDENTITY HELPER FUNCTIONS
# =============================================================================


async def get_platform_user_id_from_channel(
    provider: str,
    provider_user_id: str,
) -> Optional[str]:
    """
    Get the platform user ID linked to a channel identity (e.g., Slack user).

    Args:
        provider: Channel provider name (e.g., 'slack', 'teams')
        provider_user_id: The user ID from the channel provider

    Returns:
        Platform user ID if linked, None otherwise
    """
    # Query the channel_identities table via database provider
    client = get_rbac_client()
    if hasattr(client._provider, 'get_platform_user_from_channel'):
        return await client._provider.get_platform_user_from_channel(provider, provider_user_id)

    # Fallback: Direct database query if not implemented in provider
    try:
        from db.supabase_client import get_ui_supabase
        supabase = get_ui_supabase()
        if supabase:
            result = supabase.table('channel_identities').select('user_id').eq(
                'provider', provider
            ).eq('provider_user_id', provider_user_id).single().execute()
            if result.data and result.data.get('user_id'):
                return result.data['user_id']
    except Exception as e:
        logger.debug(f"[RBAC] Failed to query channel_identities: {e}")

    return None


async def has_permission_by_channel(
    provider: str,
    provider_user_id: str,
    permission: str,
    context: Optional[RBACContext] = None,
) -> bool:
    """
    Check if a channel user (e.g., Slack user) has a specific permission.

    First looks up the linked platform user, then checks their permissions.

    Args:
        provider: Channel provider name (e.g., 'slack', 'teams')
        provider_user_id: The user ID from the channel provider
        permission: Permission to check (format: module:resource:action)
        context: Optional context for ownership checks

    Returns:
        True if user has the permission, False if not linked or lacks permission
    """
    # Get the linked platform user ID
    platform_user_id = await get_platform_user_id_from_channel(provider, provider_user_id)

    if not platform_user_id:
        logger.debug(f"[RBAC] Channel user {provider}:{provider_user_id} not linked to platform user")
        return False

    # Check permission for the platform user
    return await has_permission(platform_user_id, permission, context)


async def require_permission_by_channel(
    provider: str,
    provider_user_id: str,
    permission: str,
    context: Optional[RBACContext] = None,
) -> None:
    """
    Require a channel user to have a permission. Raises exception if not.

    Args:
        provider: Channel provider name (e.g., 'slack', 'teams')
        provider_user_id: The user ID from the channel provider
        permission: Required permission
        context: Optional context

    Raises:
        PermissionError: If user not linked or lacks permission
    """
    if not await has_permission_by_channel(provider, provider_user_id, permission, context):
        raise PermissionError(
            f"Channel user {provider}:{provider_user_id} lacks required permission: {permission}"
        )
