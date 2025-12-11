"""
Database RBAC provider.

Reads permissions from trusted proxy headers.
unified-ui handles all RBAC queries and injects permissions into request headers.
This provider reads from the current user context (set by middleware).

NOTE: All RBAC management (profiles, teams, permission sets) is handled by unified-ui.
This provider only implements permission checking from trusted headers.
"""

import logging
from contextvars import ContextVar
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
    get_default_permissions,
)

logger = logging.getLogger("proposal-bot")

# Context-local storage for current user context (async-safe)
# Uses contextvars for proper isolation between concurrent async requests
_current_user_context: ContextVar[dict] = ContextVar("user_context", default={})


def set_user_context(user_id: str, profile: str, permissions: List[str]) -> None:
    """
    Set the current user context for RBAC checks.

    Called by FastAPI middleware after reading trusted headers.
    Uses contextvars for async-safe isolation between requests.
    """
    _current_user_context.set({
        "user_id": user_id,
        "profile": profile,
        "permissions": set(permissions),
    })


def clear_user_context() -> None:
    """Clear user context after request completes."""
    _current_user_context.set({})


def get_user_context() -> dict:
    """Get current user context."""
    return _current_user_context.get()


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

    async def get_user_permissions(self, user_id: str) -> Set[str]:
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
        context: Optional[RBACContext] = None,
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

        for i, (p, t) in enumerate(zip(pattern_parts, perm_parts)):
            if p != "*" and p != t:
                if i == 2 and p == "manage":
                    return True
                return False

        return True

    async def get_user_profile(self, user_id: str) -> Optional[Profile]:
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

    async def list_permissions(self) -> List[Permission]:
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

    async def get_profile(self, profile_name: str) -> Optional[Profile]:
        logger.warning("[RBAC:DATABASE] get_profile - managed by unified-ui")
        return None

    async def list_profiles(self) -> List[Profile]:
        logger.warning("[RBAC:DATABASE] list_profiles - managed by unified-ui")
        return []

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        logger.warning("[RBAC:DATABASE] create_profile - managed by unified-ui")
        return None

    async def update_profile(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        logger.warning("[RBAC:DATABASE] update_profile - managed by unified-ui")
        return None

    async def delete_profile(self, name: str) -> bool:
        logger.warning("[RBAC:DATABASE] delete_profile - managed by unified-ui")
        return False

    async def get_user_permission_sets(self, user_id: str) -> List[PermissionSet]:
        return []

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        logger.warning("[RBAC:DATABASE] assign_permission_set - managed by unified-ui")
        return False

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        logger.warning("[RBAC:DATABASE] revoke_permission_set - managed by unified-ui")
        return False

    async def get_permission_set(self, name: str) -> Optional[PermissionSet]:
        return None

    async def list_permission_sets(self) -> List[PermissionSet]:
        return []

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[PermissionSet]:
        logger.warning("[RBAC:DATABASE] create_permission_set - managed by unified-ui")
        return None

    async def update_permission_set(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PermissionSet]:
        logger.warning("[RBAC:DATABASE] update_permission_set - managed by unified-ui")
        return None

    async def delete_permission_set(self, name: str) -> bool:
        logger.warning("[RBAC:DATABASE] delete_permission_set - managed by unified-ui")
        return False

    async def get_user_teams(self, user_id: str) -> List[Team]:
        return []

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

    async def get_team(self, team_id: int) -> Optional[Team]:
        return None

    async def get_team_by_name(self, name: str) -> Optional[Team]:
        return None

    async def list_teams(self) -> List[Team]:
        return []

    async def get_team_members(self, team_id: int) -> List[TeamMember]:
        return []

    async def create_team(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
    ) -> Optional[Team]:
        logger.warning("[RBAC:DATABASE] create_team - managed by unified-ui")
        return None

    async def update_team(
        self,
        team_id: int,
        name: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Team]:
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
        shared_with_user_id: Optional[str] = None,
        shared_with_team_id: Optional[int] = None,
        access_level: AccessLevel = AccessLevel.READ,
        expires_at: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[RecordShare]:
        logger.warning("[RBAC:DATABASE] share_record - managed by unified-ui")
        return None

    async def revoke_record_share(self, share_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] revoke_record_share - managed by unified-ui")
        return False

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> List[RecordShare]:
        return []

    async def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        required_access: AccessLevel = AccessLevel.READ,
    ) -> bool:
        return False

    async def list_sharing_rules(self, object_type: Optional[str] = None) -> List[SharingRule]:
        return []

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
        logger.warning("[RBAC:DATABASE] create_sharing_rule - managed by unified-ui")
        return None

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        logger.warning("[RBAC:DATABASE] delete_sharing_rule - managed by unified-ui")
        return False
