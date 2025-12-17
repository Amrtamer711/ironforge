"""
Abstract base class for RBAC (Role-Based Access Control) providers.

Enterprise RBAC Architecture:
- Level 1: Profiles (base permission templates, like Salesforce)
- Level 2: Permission Sets (additive permissions on top of profiles)
- Level 3: Teams & Hierarchy (organizational structure)
- Level 4: Record-Level Sharing (manual and rule-based sharing)

Each provider implements their own storage-specific syntax.
Follows the same pattern as integrations/llm/base.py and integrations/auth/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionAction(str, Enum):
    """Standard permission actions."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    MANAGE = "manage"  # Full control (implies all others)


class AccessLevel(str, Enum):
    """Access levels for record sharing."""
    READ = "read"
    READ_WRITE = "read_write"
    FULL = "full"  # Includes ability to share with others


class TeamRole(str, Enum):
    """Roles within a team."""
    MEMBER = "member"
    LEADER = "leader"


@dataclass
class Permission:
    """
    Permission definition.

    Format: "{module}:{resource}:{action}" e.g., "sales:proposals:create", "core:users:manage"
    """
    id: int | None = None
    name: str = ""  # Full permission name (e.g., "sales:proposals:create")
    resource: str = ""  # Resource type (e.g., "proposals")
    action: str = ""  # Action (e.g., "create")
    description: str | None = None

    @classmethod
    def from_name(cls, name: str, description: str | None = None) -> "Permission":
        """Create a Permission from a name string."""
        parts = name.split(":", 1)
        resource = parts[0] if parts else ""
        action = parts[1] if len(parts) > 1 else ""
        return cls(name=name, resource=resource, action=action, description=description)

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other) -> bool:
        if isinstance(other, Permission):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False


# =============================================================================
# LEVEL 1: PROFILES
# =============================================================================

@dataclass
class Profile:
    """
    Profile definition (Salesforce-style base permission template).

    Users are assigned exactly one profile which defines their base permissions.
    Profiles are like "job functions" - System Admin, Sales User, etc.
    """
    id: int | None = None
    name: str = ""  # e.g., "system_admin", "sales_user"
    display_name: str = ""
    description: str | None = None
    permissions: set[str] = field(default_factory=set)  # Permission names
    is_system: bool = False  # System profiles can't be deleted
    created_at: str | None = None
    updated_at: str | None = None

    def has_permission(self, permission: str) -> bool:
        """Check if profile has a specific permission."""
        if permission in self.permissions:
            return True

        # Check wildcard patterns
        return any(self._matches_wildcard(perm, permission) for perm in self.permissions)

    def _matches_wildcard(self, pattern: str, permission: str) -> bool:
        """Check if a wildcard pattern matches a permission."""
        # Full wildcard: *:*:* or *:*:manage
        if pattern.startswith("*:*:"):
            return True

        # Module wildcard: sales:*:* or sales:*:read
        pattern_parts = pattern.split(":")
        perm_parts = permission.split(":")

        if len(pattern_parts) != 3 or len(perm_parts) != 3:
            return False

        for i, (p, t) in enumerate(zip(pattern_parts, perm_parts, strict=False)):
            if p != "*" and p != t:
                # Special case: "manage" implies all actions
                if i == 2 and p == "manage":
                    return True
                return False

        return True

    def __str__(self) -> str:
        return self.name


# =============================================================================
# LEVEL 2: PERMISSION SETS
# =============================================================================

@dataclass
class PermissionSet:
    """
    Permission Set - additive permissions on top of a profile.

    Unlike profiles (one per user), users can have multiple permission sets.
    Used for temporary access, special capabilities, or feature toggles.
    """
    id: int | None = None
    name: str = ""  # e.g., "export_reports", "api_access"
    display_name: str = ""
    description: str | None = None
    permissions: set[str] = field(default_factory=set)
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def has_permission(self, permission: str) -> bool:
        """Check if permission set grants a specific permission."""
        return permission in self.permissions

    def __str__(self) -> str:
        return self.name


@dataclass
class UserPermissionSet:
    """
    Assignment of a permission set to a user.
    """
    user_id: str
    permission_set: PermissionSet
    granted_by: str | None = None
    granted_at: str | None = None
    expires_at: str | None = None  # NULL = permanent


# =============================================================================
# LEVEL 3: TEAMS & HIERARCHY
# =============================================================================

@dataclass
class Team:
    """
    Team/Group for organizational structure.

    Teams can be nested (parent_team_id) to create hierarchies.
    Used for data visibility and sharing rules.
    """
    id: int | None = None
    name: str = ""
    display_name: str | None = None
    description: str | None = None
    parent_team_id: int | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def __str__(self) -> str:
        return self.display_name or self.name


@dataclass
class TeamMember:
    """
    User membership in a team.
    """
    team_id: int
    user_id: str
    role: TeamRole = TeamRole.MEMBER
    joined_at: str | None = None


# =============================================================================
# LEVEL 4: RECORD-LEVEL SHARING
# =============================================================================

@dataclass
class SharingRule:
    """
    Automatic sharing rule (org-wide defaults).

    Defines how records are automatically shared based on ownership,
    profile, or team membership.
    """
    id: int | None = None
    name: str = ""
    description: str | None = None
    object_type: str = ""  # e.g., "proposal", "booking_order"
    share_from_type: str = ""  # "owner", "profile", "team"
    share_from_id: str | None = None
    share_to_type: str = ""  # "profile", "team", "all"
    share_to_id: str | None = None
    access_level: AccessLevel = AccessLevel.READ
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class RecordShare:
    """
    Manual record-level share.

    Grants specific users or teams access to individual records.
    """
    id: int | None = None
    object_type: str = ""
    record_id: str = ""
    shared_with_user_id: str | None = None
    shared_with_team_id: int | None = None
    access_level: AccessLevel = AccessLevel.READ
    shared_by: str = ""
    shared_at: str | None = None
    expires_at: str | None = None
    reason: str | None = None


# =============================================================================
# RBAC CONTEXT
# =============================================================================

@dataclass
class RBACContext:
    """
    Context for RBAC decisions.

    Provides additional context for permission checks including:
    - Resource ownership
    - Team membership
    - Manager hierarchy
    """
    user_id: str
    resource_id: str | None = None
    resource_owner_id: str | None = None
    resource_type: str | None = None
    user_profile_id: int | None = None
    user_team_ids: list[int] = field(default_factory=list)
    user_manager_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_owner(self) -> bool:
        """Check if user owns the resource."""
        return self.resource_owner_id == self.user_id

    def is_manager_of(self, other_user_id: str) -> bool:
        """Check if user is manager of another user (requires metadata lookup)."""
        # This would need to be populated by the provider
        return self.metadata.get("is_manager_of", {}).get(other_user_id, False)

    def in_same_team(self, other_user_id: str) -> bool:
        """Check if user is in same team as another user."""
        other_teams = self.metadata.get("user_teams", {}).get(other_user_id, [])
        return bool(set(self.user_team_ids) & set(other_teams))


# =============================================================================
# MODULE REGISTRY INTEGRATION
# =============================================================================

def get_default_permissions() -> list[Permission]:
    """
    Get all permissions from registered modules.

    Returns:
        Combined list of all permissions from all registered modules.
    """
    from integrations.rbac.modules import get_all_permissions
    return get_all_permissions()


class RBACProvider(ABC):
    """
    Abstract base class for RBAC providers.

    Enterprise RBAC with 4 levels:
    - Level 1: Profiles (base permission templates)
    - Level 2: Permission Sets (additive permissions)
    - Level 3: Teams & Hierarchy
    - Level 4: Record-Level Sharing

    Each provider (Database, Static, etc.) implements this interface
    with their own storage-specific syntax.

    Pattern follows:
    - integrations/llm/base.py (LLMProvider)
    - integrations/auth/base.py (AuthProvider)
    - db/base.py (DatabaseBackend)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'database', 'static')."""
        pass

    # =========================================================================
    # LEVEL 1: PROFILE OPERATIONS
    # =========================================================================

    async def get_user_profile(self, user_id: str) -> Profile | None:
        """
        Get the profile assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Profile object or None
        """
        # Default implementation - override in providers
        return None

    async def assign_profile(
        self,
        user_id: str,
        profile_name: str,
    ) -> bool:
        """
        Assign a profile to a user.

        Args:
            user_id: User's ID
            profile_name: Name of the profile to assign

        Returns:
            True if assigned successfully
        """
        # Default implementation - override in providers
        return False

    async def get_profile(self, profile_name: str) -> Profile | None:
        """
        Get a profile by name.

        Args:
            profile_name: Profile name

        Returns:
            Profile object or None
        """
        # Default implementation - override in providers
        return None

    async def list_profiles(self) -> list[Profile]:
        """
        List all available profiles.

        Returns:
            List of Profile objects
        """
        # Default implementation - override in providers
        return []

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Profile | None:
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
        # Default implementation - override in providers
        return None

    async def update_profile(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Profile | None:
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
        # Default implementation - override in providers
        return None

    async def delete_profile(self, name: str) -> bool:
        """
        Delete a profile (system profiles cannot be deleted).

        Args:
            name: Profile name

        Returns:
            True if deleted
        """
        # Default implementation - override in providers
        return False

    # =========================================================================
    # LEVEL 2: PERMISSION SET OPERATIONS
    # =========================================================================

    async def get_user_permission_sets(self, user_id: str) -> list[PermissionSet]:
        """
        Get all permission sets assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of PermissionSet objects
        """
        # Default implementation - override in providers
        return []

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: str | None = None,
        expires_at: str | None = None,
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
        # Default implementation - override in providers
        return False

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        """
        Revoke a permission set from a user.

        Args:
            user_id: User's ID
            permission_set_name: Name of the permission set

        Returns:
            True if revoked successfully
        """
        # Default implementation - override in providers
        return False

    async def get_permission_set(self, name: str) -> PermissionSet | None:
        """
        Get a permission set by name.

        Args:
            name: Permission set name

        Returns:
            PermissionSet object or None
        """
        # Default implementation - override in providers
        return None

    async def list_permission_sets(self) -> list[PermissionSet]:
        """
        List all available permission sets.

        Returns:
            List of PermissionSet objects
        """
        # Default implementation - override in providers
        return []

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> PermissionSet | None:
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
        # Default implementation - override in providers
        return None

    async def update_permission_set(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
        is_active: bool | None = None,
    ) -> PermissionSet | None:
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
        # Default implementation - override in providers
        return None

    async def delete_permission_set(self, name: str) -> bool:
        """
        Delete a permission set.

        Args:
            name: Permission set name

        Returns:
            True if deleted
        """
        # Default implementation - override in providers
        return False

    # =========================================================================
    # LEVEL 3: TEAM OPERATIONS
    # =========================================================================

    async def get_user_teams(self, user_id: str) -> list[Team]:
        """
        Get all teams a user belongs to.

        Args:
            user_id: User's unique identifier

        Returns:
            List of Team objects
        """
        # Default implementation - override in providers
        return []

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
        # Default implementation - override in providers
        return False

    async def remove_user_from_team(self, user_id: str, team_id: int) -> bool:
        """
        Remove a user from a team.

        Args:
            user_id: User's ID
            team_id: Team ID

        Returns:
            True if removed successfully
        """
        # Default implementation - override in providers
        return False

    async def get_team(self, team_id: int) -> Team | None:
        """
        Get a team by ID.

        Args:
            team_id: Team ID

        Returns:
            Team object or None
        """
        # Default implementation - override in providers
        return None

    async def get_team_by_name(self, name: str) -> Team | None:
        """
        Get a team by name.

        Args:
            name: Team name

        Returns:
            Team object or None
        """
        # Default implementation - override in providers
        return None

    async def list_teams(self) -> list[Team]:
        """
        List all teams.

        Returns:
            List of Team objects
        """
        # Default implementation - override in providers
        return []

    async def get_team_members(self, team_id: int) -> list[TeamMember]:
        """
        Get all members of a team.

        Args:
            team_id: Team ID

        Returns:
            List of TeamMember objects
        """
        # Default implementation - override in providers
        return []

    async def create_team(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        parent_team_id: int | None = None,
    ) -> Team | None:
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
        # Default implementation - override in providers
        return None

    async def update_team(
        self,
        team_id: int,
        name: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        parent_team_id: int | None = None,
        is_active: bool | None = None,
    ) -> Team | None:
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
        # Default implementation - override in providers
        return None

    async def delete_team(self, team_id: int) -> bool:
        """
        Delete a team.

        Args:
            team_id: Team ID

        Returns:
            True if deleted
        """
        # Default implementation - override in providers
        return False

    # =========================================================================
    # LEVEL 4: RECORD SHARING OPERATIONS
    # =========================================================================

    async def share_record(
        self,
        object_type: str,
        record_id: str,
        shared_by: str,
        shared_with_user_id: str | None = None,
        shared_with_team_id: int | None = None,
        access_level: AccessLevel = AccessLevel.READ,
        expires_at: str | None = None,
        reason: str | None = None,
    ) -> RecordShare | None:
        """
        Share a record with a user or team.

        Args:
            object_type: Type of record (e.g., "proposal")
            record_id: ID of the record
            shared_by: User sharing the record
            shared_with_user_id: User to share with (one of user/team required)
            shared_with_team_id: Team to share with
            access_level: Level of access
            expires_at: Optional expiration
            reason: Reason for sharing

        Returns:
            Created RecordShare or None
        """
        # Default implementation - override in providers
        return None

    async def revoke_record_share(self, share_id: int) -> bool:
        """
        Revoke a record share.

        Args:
            share_id: Share ID

        Returns:
            True if revoked successfully
        """
        # Default implementation - override in providers
        return False

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> list[RecordShare]:
        """
        Get all shares for a record.

        Args:
            object_type: Type of record
            record_id: ID of the record

        Returns:
            List of RecordShare objects
        """
        # Default implementation - override in providers
        return []

    async def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        required_access: AccessLevel = AccessLevel.READ,
    ) -> bool:
        """
        Check if user has access to a specific record.

        Checks:
        1. Ownership
        2. Direct sharing
        3. Team-based sharing
        4. Sharing rules
        5. Manager hierarchy

        Args:
            user_id: User's ID
            object_type: Type of record
            record_id: ID of the record
            required_access: Minimum access level required

        Returns:
            True if user has access
        """
        # Default implementation - override in providers
        return False

    async def list_sharing_rules(self, object_type: str | None = None) -> list[SharingRule]:
        """
        List sharing rules, optionally filtered by object type.

        Args:
            object_type: Optional filter by object type

        Returns:
            List of SharingRule objects
        """
        # Default implementation - override in providers
        return []

    async def create_sharing_rule(
        self,
        name: str,
        object_type: str,
        share_from_type: str,
        share_to_type: str,
        access_level: AccessLevel,
        share_from_id: str | None = None,
        share_to_id: str | None = None,
        description: str | None = None,
    ) -> SharingRule | None:
        """
        Create a sharing rule.

        Args:
            name: Rule name
            object_type: Type of records this applies to
            share_from_type: "owner", "profile", or "team"
            share_to_type: "profile", "team", or "all"
            access_level: Level of access to grant
            share_from_id: ID for profile/team (if applicable)
            share_to_id: ID for profile/team (if applicable)
            description: Rule description

        Returns:
            Created SharingRule or None
        """
        # Default implementation - override in providers
        return None

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        """
        Delete a sharing rule.

        Args:
            rule_id: Rule ID

        Returns:
            True if deleted
        """
        # Default implementation - override in providers
        return False

    # =========================================================================
    # UNIFIED PERMISSION OPERATIONS
    # =========================================================================

    @abstractmethod
    async def get_user_permissions(self, user_id: str) -> set[str]:
        """
        Get all permissions for a user.

        Aggregates permissions from:
        1. User's profile
        2. User's permission sets

        Args:
            user_id: User's unique identifier

        Returns:
            Set of permission names
        """
        pass

    @abstractmethod
    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: RBACContext | None = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Checks in order:
        1. Profile permissions
        2. Permission set permissions
        3. Ownership (if context provided)

        Args:
            user_id: User's ID
            permission: Permission to check (e.g., "sales:proposals:create")
            context: Optional context for ownership-based checks

        Returns:
            True if user has the permission
        """
        pass

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    @abstractmethod
    async def list_permissions(self) -> list[Permission]:
        """
        List all available permissions.

        Returns:
            List of Permission objects
        """
        pass

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    @abstractmethod
    async def initialize_defaults(self) -> bool:
        """
        Initialize default profiles, permission sets, and teams.

        Should be called on first run to set up:
        - System profiles (System Admin, Sales User, etc.)
        - Default permission sets

        Returns:
            True if initialized successfully
        """
        pass
