"""
Static configuration-based RBAC provider.

Implements RBACProvider using in-memory static configuration.
Useful for development and testing without database dependencies.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from integrations.rbac.base import (
    RBACProvider,
    Role,
    Permission,
    RBACContext,
    get_default_roles,
    get_default_permissions,
)

logger = logging.getLogger("proposal-bot")


class StaticRBACProvider(RBACProvider):
    """
    Static RBAC provider using in-memory configuration.

    User roles are assigned based on user metadata or explicit mapping.
    Useful for development without database setup.

    Usage:
        provider = StaticRBACProvider()

        # Assign role by user ID
        provider.set_user_role("user-123", "admin")

        # Or use auth metadata (role field)
        # User with metadata {"role": "admin"} gets admin role
    """

    def __init__(
        self,
        roles: Optional[Dict[str, Role]] = None,
        permissions: Optional[List[Permission]] = None,
        user_roles: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize static RBAC provider.

        Args:
            roles: Custom role definitions (defaults to module-defined roles)
            permissions: Custom permission list (defaults to module-defined permissions)
            user_roles: Initial user-role mappings {user_id: [role_names]}
        """
        self._roles = roles or dict(get_default_roles())
        self._permissions = permissions or list(get_default_permissions())
        self._user_roles: Dict[str, List[str]] = user_roles or {}

        logger.info(f"[RBAC:STATIC] Provider initialized with {len(self._roles)} roles")

    @property
    def name(self) -> str:
        return "static"

    def set_user_role(self, user_id: str, role_name: str) -> None:
        """
        Set a user's role in memory.

        Args:
            user_id: User ID
            role_name: Role name to assign
        """
        if user_id not in self._user_roles:
            self._user_roles[user_id] = []
        if role_name not in self._user_roles[user_id]:
            self._user_roles[user_id].append(role_name)

    def clear_user_roles(self, user_id: str) -> None:
        """Clear all roles for a user."""
        if user_id in self._user_roles:
            del self._user_roles[user_id]

    # =========================================================================
    # ROLE OPERATIONS
    # =========================================================================

    async def get_user_roles(self, user_id: str) -> List[Role]:
        """Get all roles assigned to a user."""
        role_names = self._user_roles.get(user_id, [])

        # Also check for role from auth metadata
        try:
            from integrations.auth import get_auth_client
            auth = get_auth_client()
            user = await auth.get_user_by_id(user_id)
            if user and user.metadata.get("role"):
                metadata_role = user.metadata["role"]
                if metadata_role not in role_names:
                    role_names = role_names + [metadata_role]
        except Exception:
            pass  # Auth integration may not be available

        # Default to sales:sales_person if no roles assigned
        if not role_names:
            role_names = ["sales:sales_person"]

        roles = []
        for name in role_names:
            role = self._roles.get(name)
            if role:
                roles.append(role)

        return roles

    async def assign_role(
        self,
        user_id: str,
        role_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Assign a role to a user."""
        if role_name not in self._roles:
            logger.warning(f"[RBAC:STATIC] Unknown role: {role_name}")
            return False

        self.set_user_role(user_id, role_name)
        logger.info(f"[RBAC:STATIC] Assigned role '{role_name}' to user '{user_id}'")
        return True

    async def revoke_role(self, user_id: str, role_name: str) -> bool:
        """Revoke a role from a user."""
        if user_id not in self._user_roles:
            return False

        if role_name in self._user_roles[user_id]:
            self._user_roles[user_id].remove(role_name)
            logger.info(f"[RBAC:STATIC] Revoked role '{role_name}' from user '{user_id}'")
            return True

        return False

    async def has_role(self, user_id: str, role_name: str) -> bool:
        """Check if user has a specific role."""
        roles = await self.get_user_roles(user_id)
        return any(r.name == role_name for r in roles)

    # =========================================================================
    # PERMISSION OPERATIONS
    # =========================================================================

    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """Get all permissions for a user from all their roles."""
        permissions: Set[str] = set()

        roles = await self.get_user_roles(user_id)
        for role in roles:
            for perm in role.permissions:
                permissions.add(perm.name)

        return permissions

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: Optional[RBACContext] = None,
    ) -> bool:
        """Check if user has a specific permission."""
        roles = await self.get_user_roles(user_id)

        for role in roles:
            if role.has_permission(permission):
                return True

        # Check ownership-based permissions if context provided
        if context and context.is_owner():
            # Owners can read/update/delete their own resources
            parts = permission.split(":", 1)
            if len(parts) == 2 and parts[1] in ("read", "update", "delete"):
                return True

        return False

    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================

    async def get_role(self, role_name: str) -> Optional[Role]:
        """Get a role by name."""
        return self._roles.get(role_name)

    async def list_roles(self) -> List[Role]:
        """List all available roles."""
        return list(self._roles.values())

    async def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """Create a new role in memory."""
        if name in self._roles:
            logger.warning(f"[RBAC:STATIC] Role already exists: {name}")
            return None

        perm_objects = []
        if permissions:
            for perm_name in permissions:
                perm_objects.append(Permission.from_name(perm_name))

        role = Role(
            name=name,
            description=description,
            permissions=perm_objects,
            is_system=False,
        )

        self._roles[name] = role
        logger.info(f"[RBAC:STATIC] Created role: {name}")
        return role

    async def update_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """Update an existing role."""
        role = self._roles.get(name)
        if not role:
            return None

        if role.is_system:
            logger.warning(f"[RBAC:STATIC] Cannot update system role: {name}")
            return None

        if description is not None:
            role.description = description

        if permissions is not None:
            role.permissions = [Permission.from_name(p) for p in permissions]

        logger.info(f"[RBAC:STATIC] Updated role: {name}")
        return role

    async def delete_role(self, name: str) -> bool:
        """Delete a role."""
        role = self._roles.get(name)
        if not role:
            return False

        if role.is_system:
            logger.warning(f"[RBAC:STATIC] Cannot delete system role: {name}")
            return False

        del self._roles[name]
        logger.info(f"[RBAC:STATIC] Deleted role: {name}")
        return True

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    async def list_permissions(self) -> List[Permission]:
        """List all available permissions."""
        return list(self._permissions)

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize_defaults(self) -> bool:
        """Initialize defaults (no-op for static provider)."""
        logger.info("[RBAC:STATIC] Using default static configuration")
        return True
