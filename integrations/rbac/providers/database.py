"""
Database RBAC provider.

Reads permissions from trusted proxy headers.
unified-ui handles all RBAC queries and injects permissions into request headers.
This provider reads from the current user context (set by middleware).

Enterprise RBAC - 4 Levels:
- Level 1: Profiles (base permissions for job function)
- Level 2: Permission Sets (additive, can be temporary with expiration)
- Level 3: Teams & Hierarchy (team-based access, manager sees subordinates)
- Level 4: Record Sharing (share specific records with users/teams)

NOTE: All RBAC management (profiles, teams, permission sets) is handled by unified-ui.
This provider reads from trusted headers and performs permission checks.
"""

import logging
from contextvars import ContextVar
from typing import Any

from integrations.rbac.base import (
    AccessLevel,
    Permission,
    PermissionSet,
    Profile,
    RBACContext,
    RBACProvider,
    RecordShare,
    SharingRule,
    Team,
    TeamMember,
    TeamRole,
    get_default_permissions,
)

logger = logging.getLogger("proposal-bot")

# Context-local storage for current user context (async-safe)
# Uses contextvars for proper isolation between concurrent async requests
_current_user_context: ContextVar[dict] = ContextVar("user_context", default={})


def set_user_context(
    user_id: str,
    profile: str,
    permissions: list[str],
    permission_sets: list[dict[str, Any]] | None = None,
    teams: list[dict[str, Any]] | None = None,
    team_ids: list[int] | None = None,
    manager_id: str | None = None,
    subordinate_ids: list[str] | None = None,
    sharing_rules: list[dict[str, Any]] | None = None,
    shared_records: dict[str, list[dict[str, Any]]] | None = None,
    shared_from_user_ids: list[str] | None = None,
) -> None:
    """
    Set the current user context for RBAC checks.

    Called by FastAPI middleware after reading trusted headers.
    Uses contextvars for async-safe isolation between requests.

    Args:
        user_id: User's UUID from UI Supabase
        profile: Profile name (e.g., 'system_admin', 'sales_user')
        permissions: Combined permissions from profile + permission sets
        permission_sets: Level 2 - Active permission sets [{id, name, expiresAt}]
        teams: Level 3 - Teams user belongs to [{id, name, role, ...}]
        team_ids: Level 3 - Just team IDs for quick lookups
        manager_id: Level 3 - User's manager ID for hierarchy
        subordinate_ids: Level 3 - IDs of user's direct reports + team members
        sharing_rules: Level 4 - Applicable sharing rules
        shared_records: Level 4 - Records directly shared with user {objectType: [{recordId, accessLevel}]}
        shared_from_user_ids: Level 4 - User IDs whose records are accessible via sharing rules
    """
    _current_user_context.set({
        "user_id": user_id,
        "profile": profile,
        "permissions": set(permissions),
        # Level 2: Permission Sets
        "permission_sets": permission_sets or [],
        # Level 3: Teams & Hierarchy
        "teams": teams or [],
        "team_ids": team_ids or [],
        "manager_id": manager_id,
        "subordinate_ids": subordinate_ids or [],
        # Level 4: Sharing Rules & Record Shares
        "sharing_rules": sharing_rules or [],
        "shared_records": shared_records or {},
        "shared_from_user_ids": shared_from_user_ids or [],
    })


def clear_user_context() -> None:
    """Clear user context after request completes."""
    _current_user_context.set({})


def get_user_context() -> dict:
    """Get current user context."""
    return _current_user_context.get()


def can_access_user_data(target_user_id: str) -> bool:
    """
    Check if current user can access another user's data.

    Returns True if:
    - Current user is system_admin
    - Target is current user (self)
    - Target is a subordinate (direct report or team member)
    - Target is accessible via sharing rules (sharedFromUserIds)
    - Current user has '*:*:*' permission
    """
    ctx = get_user_context()
    if not ctx:
        return False

    current_user_id = ctx.get("user_id")
    profile = ctx.get("profile")
    permissions = ctx.get("permissions", set())
    subordinate_ids = ctx.get("subordinate_ids", [])
    shared_from_user_ids = ctx.get("shared_from_user_ids", [])

    # System admin can access all
    if profile == "system_admin" or "*:*:*" in permissions:
        return True

    # Self access
    if current_user_id == target_user_id:
        return True

    # Subordinate access (manager can see direct reports and team members)
    if target_user_id in subordinate_ids:
        return True

    # Sharing rules - user can access data from these users
    if target_user_id in shared_from_user_ids:
        return True

    return False


def can_access_record(object_type: str, record_id: str, record_owner_id: str = None) -> bool:
    """
    Check if current user can access a specific record.

    Returns True if:
    - User can access the owner's data (via can_access_user_data)
    - Record is directly shared with user (via sharedRecords)
    """
    ctx = get_user_context()
    if not ctx:
        return False

    # First check owner-based access
    if record_owner_id and can_access_user_data(record_owner_id):
        return True

    # Check direct record shares
    shared_records = ctx.get("shared_records", {})
    if object_type in shared_records:
        for share in shared_records[object_type]:
            if str(share.get("recordId")) == str(record_id):
                return True

    return False


def get_shared_record_ids(object_type: str) -> list[str]:
    """
    Get list of record IDs directly shared with the current user for an object type.

    Returns list of record IDs that have been explicitly shared.
    """
    ctx = get_user_context()
    if not ctx:
        return []

    shared_records = ctx.get("shared_records", {})
    if object_type in shared_records:
        return [str(share.get("recordId")) for share in shared_records[object_type]]

    return []


def get_accessible_user_ids() -> list[str]:
    """
    Get list of user IDs the current user can access data for.

    Returns:
        - [current_user_id] for regular users
        - [current_user_id, ...subordinate_ids, ...sharedFromUserIds] for managers/users with sharing
        - None for admins (access to all)
    """
    ctx = get_user_context()
    if not ctx:
        return []

    current_user_id = ctx.get("user_id")
    profile = ctx.get("profile")
    permissions = ctx.get("permissions", set())
    subordinate_ids = ctx.get("subordinate_ids", [])
    shared_from_user_ids = ctx.get("shared_from_user_ids", [])

    # System admin can access all - return None to indicate "all"
    if profile == "system_admin" or "*:*:*" in permissions:
        return None  # type: ignore

    # Return self + subordinates + sharing rule users
    accessible = [current_user_id] if current_user_id else []
    accessible.extend(subordinate_ids)
    accessible.extend(shared_from_user_ids)
    return list(set(accessible))


class DatabaseRBACProvider(RBACProvider):
    """
    Database RBAC provider that reads from trusted proxy headers.

    unified-ui is the RBAC gateway:
    - Queries profiles and permissions from UI Supabase
    - Injects permissions into X-Trusted-User-Permissions header
    - This provider reads from that header via middleware

    All RBAC management operations are handled by unified-ui.
    This provider is read-only for permission checks.
    """

    def __init__(self, **kwargs):
        """Initialize database RBAC provider."""
        logger.info("[RBAC:DATABASE] Provider initialized (trusted proxy mode)")

    @property
    def name(self) -> str:
        return "database"

    async def get_user_permissions(self, user_id: str) -> set[str]:
        """
        Get permissions for user from trusted context.

        Permissions are provided by unified-ui via headers.
        """
        ctx = get_user_context()
        if ctx.get("user_id") == user_id:
            return ctx.get("permissions", set())

        logger.warning(f"[RBAC:DATABASE] No context for user {user_id}")
        return set()

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: RBACContext | None = None,
    ) -> bool:
        """
        Check if user has permission.

        Permissions come from trusted headers set by unified-ui.
        """
        permissions = await self.get_user_permissions(user_id)

        # Direct match
        if permission in permissions:
            return True

        # Check wildcard patterns
        for perm in permissions:
            if self._matches_wildcard(perm, permission):
                return True

        # Check ownership if context provided
        if context and context.is_owner():
            # Owners can read/update their own resources
            if permission.endswith(":read") or permission.endswith(":update"):
                return True

        return False

    def _matches_wildcard(self, pattern: str, permission: str) -> bool:
        """Check if a wildcard pattern matches a permission."""
        if pattern == "*:*:*":
            return True

        pattern_parts = pattern.split(":")
        perm_parts = permission.split(":")

        if len(pattern_parts) != 3 or len(perm_parts) != 3:
            return False

        for i, (p, t) in enumerate(zip(pattern_parts, perm_parts, strict=False)):
            if p != "*" and p != t:
                if i == 2 and p == "manage":
                    return True
                return False

        return True

    async def get_user_profile(self, user_id: str) -> Profile | None:
        """
        Get user's profile from trusted context.
        """
        ctx = get_user_context()
        if ctx.get("user_id") == user_id and ctx.get("profile"):
            return Profile(
                name=ctx["profile"],
                display_name=ctx["profile"],
                permissions=ctx.get("permissions", set()),
            )
        return None

    async def list_permissions(self) -> list[Permission]:
        """List all available permissions."""
        return get_default_permissions()

    async def initialize_defaults(self) -> bool:
        """
        Initialize defaults.

        RBAC initialization is handled by unified-ui.
        """
        logger.info("[RBAC:DATABASE] Defaults managed by unified-ui")
        return True

    # =========================================================================
    # MANAGEMENT OPERATIONS (NOT AVAILABLE - MANAGED BY UNIFIED-UI)
    # =========================================================================

    async def assign_profile(self, user_id: str, profile_name: str) -> bool:
        logger.warning("[RBAC:DATABASE] assign_profile - managed by unified-ui")
        return False

    async def get_profile(self, profile_name: str) -> Profile | None:
        logger.warning("[RBAC:DATABASE] get_profile - managed by unified-ui")
        return None

    async def list_profiles(self) -> list[Profile]:
        logger.warning("[RBAC:DATABASE] list_profiles - managed by unified-ui")
        return []

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Profile | None:
        logger.warning("[RBAC:DATABASE] create_profile - managed by unified-ui")
        return None

    async def update_profile(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Profile | None:
        logger.warning("[RBAC:DATABASE] update_profile - managed by unified-ui")
        return None

    async def delete_profile(self, name: str) -> bool:
        logger.warning("[RBAC:DATABASE] delete_profile - managed by unified-ui")
        return False

    async def get_user_permission_sets(self, user_id: str) -> list[PermissionSet]:
        return []

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: str | None = None,
        expires_at: str | None = None,
    ) -> bool:
        logger.warning("[RBAC:DATABASE] assign_permission_set - managed by unified-ui")
        return False

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        logger.warning("[RBAC:DATABASE] revoke_permission_set - managed by unified-ui")
        return False

    async def get_permission_set(self, name: str) -> PermissionSet | None:
        return None

    async def list_permission_sets(self) -> list[PermissionSet]:
        return []

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> PermissionSet | None:
        logger.warning("[RBAC:DATABASE] create_permission_set - managed by unified-ui")
        return None

    async def update_permission_set(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
        is_active: bool | None = None,
    ) -> PermissionSet | None:
        logger.warning("[RBAC:DATABASE] update_permission_set - managed by unified-ui")
        return None

    async def delete_permission_set(self, name: str) -> bool:
        logger.warning("[RBAC:DATABASE] delete_permission_set - managed by unified-ui")
        return False

    async def get_user_teams(self, user_id: str) -> list[Team]:
        """Get user's teams from context (populated by trusted headers)."""
        ctx = get_user_context()
        if ctx.get("user_id") == user_id:
            teams_data = ctx.get("teams", [])
            return [
                Team(
                    id=t.get("id"),
                    name=t.get("name", ""),
                    display_name=t.get("displayName"),
                    parent_team_id=t.get("parentTeamId"),
                )
                for t in teams_data
            ]
        return []

    def get_user_team_ids(self, user_id: str) -> list[int]:
        """Get just team IDs for a user (sync helper)."""
        ctx = get_user_context()
        if ctx.get("user_id") == user_id:
            return ctx.get("team_ids", [])
        return []

    def get_subordinate_ids(self, user_id: str) -> list[str]:
        """Get subordinate IDs for a user (sync helper)."""
        ctx = get_user_context()
        if ctx.get("user_id") == user_id:
            return ctx.get("subordinate_ids", [])
        return []

    def is_team_leader(self, user_id: str, team_id: int) -> bool:
        """Check if user is a leader of a specific team."""
        ctx = get_user_context()
        if ctx.get("user_id") == user_id:
            teams_data = ctx.get("teams", [])
            for t in teams_data:
                if t.get("id") == team_id and t.get("role") == "leader":
                    return True
        return False

    async def add_user_to_team(
        self,
        user_id: str,
        team_id: int,
        role: TeamRole = TeamRole.MEMBER,
    ) -> bool:
        logger.warning("[RBAC:DATABASE] add_user_to_team - managed by unified-ui")
        return False

    async def remove_user_from_team(self, user_id: str, team_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] remove_user_from_team - managed by unified-ui")
        return False

    async def get_team(self, team_id: int) -> Team | None:
        return None

    async def get_team_by_name(self, name: str) -> Team | None:
        return None

    async def list_teams(self) -> list[Team]:
        return []

    async def get_team_members(self, team_id: int) -> list[TeamMember]:
        return []

    async def create_team(
        self,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        parent_team_id: int | None = None,
    ) -> Team | None:
        logger.warning("[RBAC:DATABASE] create_team - managed by unified-ui")
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
        logger.warning("[RBAC:DATABASE] update_team - managed by unified-ui")
        return None

    async def delete_team(self, team_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] delete_team - managed by unified-ui")
        return False

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
        logger.warning("[RBAC:DATABASE] share_record - managed by unified-ui")
        return None

    async def revoke_record_share(self, share_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] revoke_record_share - managed by unified-ui")
        return False

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> list[RecordShare]:
        return []

    async def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        required_access: AccessLevel = AccessLevel.READ,
    ) -> bool:
        return False

    async def list_sharing_rules(self, object_type: str | None = None) -> list[SharingRule]:
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
        logger.warning("[RBAC:DATABASE] create_sharing_rule - managed by unified-ui")
        return None

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] delete_sharing_rule - managed by unified-ui")
        return False
