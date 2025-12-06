"""
Database-backed RBAC provider.

Implements RBACProvider using the unified database schema for storing
roles, permissions, and user assignments.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from integrations.rbac.base import (
    RBACProvider,
    Role,
    Permission,
    UserRole,
    RBACContext,
    DEFAULT_ROLES,
    DEFAULT_PERMISSIONS,
)
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")


class DatabaseRBACProvider(RBACProvider):
    """
    Database-backed RBAC provider.

    Uses the unified database schema (db/schema.py) for storing:
    - roles: Role definitions
    - permissions: Permission definitions
    - user_roles: User-role assignments
    - role_permissions: Role-permission assignments

    Works with both SQLite and Supabase backends.
    """

    def __init__(self):
        """Initialize database RBAC provider."""
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 60  # seconds
        logger.info("[RBAC:DB] Provider initialized")

    def _get_db(self):
        """Get database instance."""
        from db.database import db
        return db

    @property
    def name(self) -> str:
        return "database"

    # =========================================================================
    # ROLE OPERATIONS
    # =========================================================================

    async def get_user_roles(self, user_id: str) -> List[Role]:
        """Get all roles assigned to a user."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'get_user_roles'):
                logger.warning("[RBAC:DB] Backend doesn't support get_user_roles")
                return []

            role_data = db._backend.get_user_roles(user_id)
            roles = []

            for rd in role_data:
                role = await self.get_role(rd["name"])
                if role:
                    roles.append(role)

            return roles

        except Exception as e:
            logger.error(f"[RBAC:DB] Get user roles failed: {e}")
            return []

    async def assign_role(
        self,
        user_id: str,
        role_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Assign a role to a user."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'assign_user_role'):
                logger.warning("[RBAC:DB] Backend doesn't support assign_user_role")
                return False

            # Check if role exists
            role = await self.get_role(role_name)
            if not role:
                logger.warning(f"[RBAC:DB] Role not found: {role_name}")
                return False

            now = get_uae_time().isoformat()

            success = db._backend.assign_user_role(
                user_id=user_id,
                role_id=role.id,
                granted_by=granted_by,
                granted_at=now,
                expires_at=expires_at,
            )

            if success:
                logger.info(f"[RBAC:DB] Assigned role '{role_name}' to user '{user_id}'")

            return success

        except Exception as e:
            logger.error(f"[RBAC:DB] Assign role failed: {e}")
            return False

    async def revoke_role(self, user_id: str, role_name: str) -> bool:
        """Revoke a role from a user."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'revoke_user_role'):
                logger.warning("[RBAC:DB] Backend doesn't support revoke_user_role")
                return False

            success = db._backend.revoke_user_role(user_id, role_name)

            if success:
                logger.info(f"[RBAC:DB] Revoked role '{role_name}' from user '{user_id}'")

            return success

        except Exception as e:
            logger.error(f"[RBAC:DB] Revoke role failed: {e}")
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
        """Get a role by name with its permissions."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'get_role_by_name'):
                # Fallback to static roles
                return DEFAULT_ROLES.get(role_name)

            role_data = db._backend.get_role_by_name(role_name)
            if not role_data:
                return DEFAULT_ROLES.get(role_name)

            # Get permissions for this role
            permissions = []
            if hasattr(db._backend, 'get_role_permissions'):
                perm_data = db._backend.get_role_permissions(role_data["id"])
                for pd in perm_data:
                    permissions.append(Permission(
                        id=pd.get("id"),
                        name=pd["name"],
                        resource=pd.get("resource", ""),
                        action=pd.get("action", ""),
                        description=pd.get("description"),
                    ))

            return Role(
                id=role_data.get("id"),
                name=role_data["name"],
                description=role_data.get("description"),
                permissions=permissions,
                is_system=bool(role_data.get("is_system", False)),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get role failed: {e}")
            return DEFAULT_ROLES.get(role_name)

    async def list_roles(self) -> List[Role]:
        """List all available roles."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'list_roles'):
                return list(DEFAULT_ROLES.values())

            role_data_list = db._backend.list_roles()
            roles = []

            for rd in role_data_list:
                role = await self.get_role(rd["name"])
                if role:
                    roles.append(role)

            return roles if roles else list(DEFAULT_ROLES.values())

        except Exception as e:
            logger.error(f"[RBAC:DB] List roles failed: {e}")
            return list(DEFAULT_ROLES.values())

    async def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """Create a new role."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'create_role'):
                logger.warning("[RBAC:DB] Backend doesn't support create_role")
                return None

            now = get_uae_time().isoformat()

            role_id = db._backend.create_role(
                name=name,
                description=description,
                is_system=False,
                created_at=now,
            )

            if not role_id:
                return None

            # Assign permissions
            if permissions and hasattr(db._backend, 'assign_role_permission'):
                for perm_name in permissions:
                    db._backend.assign_role_permission(role_id, perm_name, now)

            logger.info(f"[RBAC:DB] Created role: {name}")
            return await self.get_role(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Create role failed: {e}")
            return None

    async def update_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """Update an existing role."""
        try:
            db = self._get_db()

            role = await self.get_role(name)
            if not role:
                return None

            if role.is_system:
                logger.warning(f"[RBAC:DB] Cannot update system role: {name}")
                return None

            if not hasattr(db._backend, 'update_role'):
                logger.warning("[RBAC:DB] Backend doesn't support update_role")
                return None

            db._backend.update_role(role.id, description=description)

            # Update permissions if provided
            if permissions is not None and hasattr(db._backend, 'set_role_permissions'):
                now = get_uae_time().isoformat()
                db._backend.set_role_permissions(role.id, permissions, now)

            logger.info(f"[RBAC:DB] Updated role: {name}")
            return await self.get_role(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Update role failed: {e}")
            return None

    async def delete_role(self, name: str) -> bool:
        """Delete a role."""
        try:
            role = await self.get_role(name)
            if not role:
                return False

            if role.is_system:
                logger.warning(f"[RBAC:DB] Cannot delete system role: {name}")
                return False

            db = self._get_db()

            if not hasattr(db._backend, 'delete_role'):
                logger.warning("[RBAC:DB] Backend doesn't support delete_role")
                return False

            success = db._backend.delete_role(role.id)

            if success:
                logger.info(f"[RBAC:DB] Deleted role: {name}")

            return success

        except Exception as e:
            logger.error(f"[RBAC:DB] Delete role failed: {e}")
            return False

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    async def list_permissions(self) -> List[Permission]:
        """List all available permissions."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'list_permissions'):
                return DEFAULT_PERMISSIONS

            perm_data_list = db._backend.list_permissions()
            permissions = []

            for pd in perm_data_list:
                permissions.append(Permission(
                    id=pd.get("id"),
                    name=pd["name"],
                    resource=pd.get("resource", ""),
                    action=pd.get("action", ""),
                    description=pd.get("description"),
                ))

            return permissions if permissions else DEFAULT_PERMISSIONS

        except Exception as e:
            logger.error(f"[RBAC:DB] List permissions failed: {e}")
            return DEFAULT_PERMISSIONS

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize_defaults(self) -> bool:
        """Initialize default roles and permissions in database."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            # Check if backend supports RBAC operations
            if not hasattr(db._backend, 'create_permission'):
                logger.warning("[RBAC:DB] Backend doesn't support RBAC operations")
                return False

            # Create default permissions
            for perm in DEFAULT_PERMISSIONS:
                try:
                    db._backend.create_permission(
                        name=perm.name,
                        resource=perm.resource,
                        action=perm.action,
                        description=perm.description,
                        created_at=now,
                    )
                except Exception:
                    pass  # Permission may already exist

            # Create default roles
            for role_name, role in DEFAULT_ROLES.items():
                try:
                    role_id = db._backend.create_role(
                        name=role.name,
                        description=role.description,
                        is_system=role.is_system,
                        created_at=now,
                    )

                    if role_id and hasattr(db._backend, 'assign_role_permission'):
                        for perm in role.permissions:
                            db._backend.assign_role_permission(role_id, perm.name, now)

                except Exception:
                    pass  # Role may already exist

            logger.info("[RBAC:DB] Default roles and permissions initialized")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Initialize defaults failed: {e}")
            return False
