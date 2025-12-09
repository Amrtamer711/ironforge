"""
Database-backed RBAC provider.

Implements RBACProvider using the unified database schema for storing
roles, permissions, and user assignments.

Enterprise RBAC Architecture:
- Level 1: Profiles (base permission templates)
- Level 2: Permission Sets (additive permissions)
- Level 3: Teams & Hierarchy
- Level 4: Record-Level Sharing
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from integrations.rbac.base import (
    RBACProvider,
    Permission,
    RBACContext,
    Profile,
    PermissionSet,
    Team,
    TeamMember,
    TeamRole,
    SharingRule,
    RecordShare,
    AccessLevel,
    get_default_permissions,
)
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")


class DatabaseRBACProvider(RBACProvider):
    """
    Database-backed RBAC provider.

    Uses the unified database schema (db/schema.py) for enterprise RBAC:
    - Level 1: Profiles (base permission templates)
    - Level 2: Permission Sets (additive permissions)
    - Level 3: Teams & Hierarchy
    - Level 4: Record-Level Sharing

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
    # UNIFIED PERMISSION OPERATIONS
    # =========================================================================

    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """Get all permissions for a user from profile and permission sets."""
        permissions: Set[str] = set()

        # From profile
        profile = await self.get_user_profile(user_id)
        if profile:
            permissions.update(profile.permissions)

        # From permission sets
        permission_sets = await self.get_user_permission_sets(user_id)
        for ps in permission_sets:
            permissions.update(ps.permissions)

        return permissions

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: Optional[RBACContext] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Checks in order:
        1. Profile permissions (Level 1)
        2. Permission set permissions (Level 2)
        3. Ownership (if context provided)
        """
        # Level 1: Check profile permissions
        profile = await self.get_user_profile(user_id)
        if profile and profile.has_permission(permission):
            return True

        # Level 2: Check permission set permissions
        permission_sets = await self.get_user_permission_sets(user_id)
        for ps in permission_sets:
            if ps.has_permission(permission):
                return True

        # Check ownership-based permissions if context provided
        if context and context.is_owner():
            # Owners can read/update/delete their own resources
            parts = permission.split(":")
            if len(parts) >= 3 and parts[2] in ("read", "update", "delete"):
                return True

        return False

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    async def list_permissions(self) -> List[Permission]:
        """List all available permissions."""
        try:
            db = self._get_db()

            if not hasattr(db._backend, 'list_permissions'):
                return get_default_permissions()

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

            return permissions if permissions else get_default_permissions()

        except Exception as e:
            logger.error(f"[RBAC:DB] List permissions failed: {e}")
            return get_default_permissions()

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize_defaults(self) -> bool:
        """Initialize default profiles and permissions in database."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            # Create default permissions
            for perm in get_default_permissions():
                try:
                    if hasattr(db._backend, 'create_permission'):
                        db._backend.create_permission(
                            name=perm.name,
                            resource=perm.resource,
                            action=perm.action,
                            description=perm.description,
                            created_at=now,
                        )
                except Exception:
                    pass  # Permission may already exist

            # Create default profiles
            await self._create_default_profiles()

            logger.info("[RBAC:DB] Default configuration initialized")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Initialize defaults failed: {e}")
            return False

    async def _create_default_profiles(self) -> None:
        """Create default system profiles."""
        # System Admin profile
        admin = await self.get_profile("system_admin")
        if not admin:
            admin = await self.create_profile(
                name="system_admin",
                display_name="System Administrator",
                description="Full system access",
                permissions=["*:*:*"],
            )
            if admin:
                # Mark as system profile
                try:
                    db = self._get_db()
                    db._backend.execute_query(
                        "UPDATE profiles SET is_system = true WHERE id = %s",
                        (admin.id,)
                    )
                except Exception:
                    pass

        # Sales User profile
        sales = await self.get_profile("sales_user")
        if not sales:
            sales = await self.create_profile(
                name="sales_user",
                display_name="Sales User",
                description="Standard sales user access",
                permissions=[
                    "sales:proposals:create",
                    "sales:proposals:read",
                    "sales:proposals:update",
                    "sales:booking_orders:create",
                    "sales:booking_orders:read",
                    "sales:booking_orders:update",
                    "sales:clients:read",
                    "sales:products:read",
                ],
            )
            if sales:
                try:
                    db = self._get_db()
                    db._backend.execute_query(
                        "UPDATE profiles SET is_system = true WHERE id = %s",
                        (sales.id,)
                    )
                except Exception:
                    pass

        # Read Only profile
        readonly = await self.get_profile("read_only")
        if not readonly:
            readonly = await self.create_profile(
                name="read_only",
                display_name="Read Only",
                description="Read-only access to sales data",
                permissions=[
                    "sales:proposals:read",
                    "sales:booking_orders:read",
                    "sales:clients:read",
                    "sales:products:read",
                ],
            )
            if readonly:
                try:
                    db = self._get_db()
                    db._backend.execute_query(
                        "UPDATE profiles SET is_system = true WHERE id = %s",
                        (readonly.id,)
                    )
                except Exception:
                    pass

    # =========================================================================
    # LEVEL 1: PROFILE OPERATIONS
    # =========================================================================

    async def get_user_profile(self, user_id: str) -> Optional[Profile]:
        """Get the profile assigned to a user."""
        try:
            db = self._get_db()

            # Get user with profile_id
            if not hasattr(db._backend, 'execute_query'):
                return None

            result = db._backend.execute_query(
                "SELECT profile_id FROM users WHERE id = %s",
                (user_id,)
            )

            if not result or not result[0].get("profile_id"):
                return None

            profile_id = result[0]["profile_id"]
            return await self._get_profile_by_id(profile_id)

        except Exception as e:
            logger.error(f"[RBAC:DB] Get user profile failed: {e}")
            return None

    async def _get_profile_by_id(self, profile_id: int) -> Optional[Profile]:
        """Get a profile by ID."""
        try:
            db = self._get_db()

            # Get profile data
            profile_result = db._backend.execute_query(
                "SELECT * FROM profiles WHERE id = %s",
                (profile_id,)
            )

            if not profile_result:
                return None

            pd = profile_result[0]

            # Get profile permissions
            perm_result = db._backend.execute_query(
                "SELECT permission FROM profile_permissions WHERE profile_id = %s",
                (profile_id,)
            )

            permissions = {p["permission"] for p in perm_result} if perm_result else set()

            return Profile(
                id=pd["id"],
                name=pd["name"],
                display_name=pd["display_name"],
                description=pd.get("description"),
                permissions=permissions,
                is_system=bool(pd.get("is_system", False)),
                created_at=pd.get("created_at"),
                updated_at=pd.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get profile by ID failed: {e}")
            return None

    async def assign_profile(self, user_id: str, profile_name: str) -> bool:
        """Assign a profile to a user."""
        try:
            db = self._get_db()

            # Get profile ID
            profile = await self.get_profile(profile_name)
            if not profile:
                logger.warning(f"[RBAC:DB] Profile not found: {profile_name}")
                return False

            now = get_uae_time().isoformat()

            # Update user's profile_id
            db._backend.execute_query(
                "UPDATE users SET profile_id = %s, updated_at = %s WHERE id = %s",
                (profile.id, now, user_id)
            )

            logger.info(f"[RBAC:DB] Assigned profile '{profile_name}' to user '{user_id}'")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Assign profile failed: {e}")
            return False

    async def get_profile(self, profile_name: str) -> Optional[Profile]:
        """Get a profile by name."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM profiles WHERE name = %s",
                (profile_name,)
            )

            if not result:
                return None

            pd = result[0]

            # Get permissions
            perm_result = db._backend.execute_query(
                "SELECT permission FROM profile_permissions WHERE profile_id = %s",
                (pd["id"],)
            )

            permissions = {p["permission"] for p in perm_result} if perm_result else set()

            return Profile(
                id=pd["id"],
                name=pd["name"],
                display_name=pd["display_name"],
                description=pd.get("description"),
                permissions=permissions,
                is_system=bool(pd.get("is_system", False)),
                created_at=pd.get("created_at"),
                updated_at=pd.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get profile failed: {e}")
            return None

    async def list_profiles(self) -> List[Profile]:
        """List all available profiles."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM profiles ORDER BY name"
            )

            if not result:
                return []

            profiles = []
            for pd in result:
                # Get permissions for each profile
                perm_result = db._backend.execute_query(
                    "SELECT permission FROM profile_permissions WHERE profile_id = %s",
                    (pd["id"],)
                )
                permissions = {p["permission"] for p in perm_result} if perm_result else set()

                profiles.append(Profile(
                    id=pd["id"],
                    name=pd["name"],
                    display_name=pd["display_name"],
                    description=pd.get("description"),
                    permissions=permissions,
                    is_system=bool(pd.get("is_system", False)),
                    created_at=pd.get("created_at"),
                    updated_at=pd.get("updated_at"),
                ))

            return profiles

        except Exception as e:
            logger.error(f"[RBAC:DB] List profiles failed: {e}")
            return []

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        """Create a new profile."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            # Insert profile
            db._backend.execute_query(
                """INSERT INTO profiles (name, display_name, description, is_system, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (name, display_name, description, False, now, now)
            )

            # Get the created profile
            profile = await self.get_profile(name)
            if not profile:
                return None

            # Add permissions
            if permissions:
                for perm in permissions:
                    db._backend.execute_query(
                        """INSERT INTO profile_permissions (profile_id, permission, created_at)
                           VALUES (%s, %s, %s)""",
                        (profile.id, perm, now)
                    )

            logger.info(f"[RBAC:DB] Created profile: {name}")
            return await self.get_profile(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Create profile failed: {e}")
            return None

    async def update_profile(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Profile]:
        """Update an existing profile."""
        try:
            profile = await self.get_profile(name)
            if not profile:
                return None

            if profile.is_system:
                logger.warning(f"[RBAC:DB] Cannot update system profile: {name}")
                return None

            db = self._get_db()
            now = get_uae_time().isoformat()

            # Update profile fields
            updates = ["updated_at = %s"]
            params = [now]

            if display_name is not None:
                updates.append("display_name = %s")
                params.append(display_name)

            if description is not None:
                updates.append("description = %s")
                params.append(description)

            params.append(profile.id)

            db._backend.execute_query(
                f"UPDATE profiles SET {', '.join(updates)} WHERE id = %s",
                tuple(params)
            )

            # Update permissions if provided
            if permissions is not None:
                # Remove existing permissions
                db._backend.execute_query(
                    "DELETE FROM profile_permissions WHERE profile_id = %s",
                    (profile.id,)
                )

                # Add new permissions
                for perm in permissions:
                    db._backend.execute_query(
                        """INSERT INTO profile_permissions (profile_id, permission, created_at)
                           VALUES (%s, %s, %s)""",
                        (profile.id, perm, now)
                    )

            logger.info(f"[RBAC:DB] Updated profile: {name}")
            return await self.get_profile(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Update profile failed: {e}")
            return None

    async def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        try:
            profile = await self.get_profile(name)
            if not profile:
                return False

            if profile.is_system:
                logger.warning(f"[RBAC:DB] Cannot delete system profile: {name}")
                return False

            db = self._get_db()

            # Delete profile (permissions will cascade)
            db._backend.execute_query(
                "DELETE FROM profiles WHERE id = %s",
                (profile.id,)
            )

            logger.info(f"[RBAC:DB] Deleted profile: {name}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Delete profile failed: {e}")
            return False

    # =========================================================================
    # LEVEL 2: PERMISSION SET OPERATIONS
    # =========================================================================

    async def get_user_permission_sets(self, user_id: str) -> List[PermissionSet]:
        """Get all permission sets assigned to a user."""
        try:
            db = self._get_db()

            # Get user's permission set assignments (excluding expired)
            result = db._backend.execute_query(
                """SELECT ps.* FROM permission_sets ps
                   JOIN user_permission_sets ups ON ps.id = ups.permission_set_id
                   WHERE ups.user_id = %s
                   AND ps.is_active = true
                   AND (ups.expires_at IS NULL OR ups.expires_at > NOW())""",
                (user_id,)
            )

            if not result:
                return []

            permission_sets = []
            for psd in result:
                # Get permissions for each set
                perm_result = db._backend.execute_query(
                    "SELECT permission FROM permission_set_permissions WHERE permission_set_id = %s",
                    (psd["id"],)
                )
                permissions = {p["permission"] for p in perm_result} if perm_result else set()

                permission_sets.append(PermissionSet(
                    id=psd["id"],
                    name=psd["name"],
                    display_name=psd["display_name"],
                    description=psd.get("description"),
                    permissions=permissions,
                    is_active=bool(psd.get("is_active", True)),
                    created_at=psd.get("created_at"),
                    updated_at=psd.get("updated_at"),
                ))

            return permission_sets

        except Exception as e:
            logger.error(f"[RBAC:DB] Get user permission sets failed: {e}")
            return []

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Assign a permission set to a user."""
        try:
            db = self._get_db()

            # Get permission set
            ps = await self.get_permission_set(permission_set_name)
            if not ps:
                logger.warning(f"[RBAC:DB] Permission set not found: {permission_set_name}")
                return False

            now = get_uae_time().isoformat()

            # Insert or update assignment
            db._backend.execute_query(
                """INSERT INTO user_permission_sets
                   (user_id, permission_set_id, granted_by, granted_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, permission_set_id) DO UPDATE
                   SET granted_by = %s, granted_at = %s, expires_at = %s""",
                (user_id, ps.id, granted_by, now, expires_at, granted_by, now, expires_at)
            )

            logger.info(f"[RBAC:DB] Assigned permission set '{permission_set_name}' to user '{user_id}'")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Assign permission set failed: {e}")
            return False

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        """Revoke a permission set from a user."""
        try:
            db = self._get_db()

            # Get permission set ID
            ps = await self.get_permission_set(permission_set_name)
            if not ps:
                return False

            db._backend.execute_query(
                "DELETE FROM user_permission_sets WHERE user_id = %s AND permission_set_id = %s",
                (user_id, ps.id)
            )

            logger.info(f"[RBAC:DB] Revoked permission set '{permission_set_name}' from user '{user_id}'")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Revoke permission set failed: {e}")
            return False

    async def get_permission_set(self, name: str) -> Optional[PermissionSet]:
        """Get a permission set by name."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM permission_sets WHERE name = %s",
                (name,)
            )

            if not result:
                return None

            psd = result[0]

            # Get permissions
            perm_result = db._backend.execute_query(
                "SELECT permission FROM permission_set_permissions WHERE permission_set_id = %s",
                (psd["id"],)
            )

            permissions = {p["permission"] for p in perm_result} if perm_result else set()

            return PermissionSet(
                id=psd["id"],
                name=psd["name"],
                display_name=psd["display_name"],
                description=psd.get("description"),
                permissions=permissions,
                is_active=bool(psd.get("is_active", True)),
                created_at=psd.get("created_at"),
                updated_at=psd.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get permission set failed: {e}")
            return None

    async def list_permission_sets(self) -> List[PermissionSet]:
        """List all available permission sets."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM permission_sets ORDER BY name"
            )

            if not result:
                return []

            permission_sets = []
            for psd in result:
                perm_result = db._backend.execute_query(
                    "SELECT permission FROM permission_set_permissions WHERE permission_set_id = %s",
                    (psd["id"],)
                )
                permissions = {p["permission"] for p in perm_result} if perm_result else set()

                permission_sets.append(PermissionSet(
                    id=psd["id"],
                    name=psd["name"],
                    display_name=psd["display_name"],
                    description=psd.get("description"),
                    permissions=permissions,
                    is_active=bool(psd.get("is_active", True)),
                    created_at=psd.get("created_at"),
                    updated_at=psd.get("updated_at"),
                ))

            return permission_sets

        except Exception as e:
            logger.error(f"[RBAC:DB] List permission sets failed: {e}")
            return []

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[PermissionSet]:
        """Create a new permission set."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            db._backend.execute_query(
                """INSERT INTO permission_sets (name, display_name, description, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (name, display_name, description, True, now, now)
            )

            ps = await self.get_permission_set(name)
            if not ps:
                return None

            if permissions:
                for perm in permissions:
                    db._backend.execute_query(
                        """INSERT INTO permission_set_permissions (permission_set_id, permission, created_at)
                           VALUES (%s, %s, %s)""",
                        (ps.id, perm, now)
                    )

            logger.info(f"[RBAC:DB] Created permission set: {name}")
            return await self.get_permission_set(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Create permission set failed: {e}")
            return None

    async def update_permission_set(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PermissionSet]:
        """Update an existing permission set."""
        try:
            ps = await self.get_permission_set(name)
            if not ps:
                return None

            db = self._get_db()
            now = get_uae_time().isoformat()

            updates = ["updated_at = %s"]
            params = [now]

            if display_name is not None:
                updates.append("display_name = %s")
                params.append(display_name)

            if description is not None:
                updates.append("description = %s")
                params.append(description)

            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)

            params.append(ps.id)

            db._backend.execute_query(
                f"UPDATE permission_sets SET {', '.join(updates)} WHERE id = %s",
                tuple(params)
            )

            if permissions is not None:
                db._backend.execute_query(
                    "DELETE FROM permission_set_permissions WHERE permission_set_id = %s",
                    (ps.id,)
                )
                for perm in permissions:
                    db._backend.execute_query(
                        """INSERT INTO permission_set_permissions (permission_set_id, permission, created_at)
                           VALUES (%s, %s, %s)""",
                        (ps.id, perm, now)
                    )

            logger.info(f"[RBAC:DB] Updated permission set: {name}")
            return await self.get_permission_set(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Update permission set failed: {e}")
            return None

    async def delete_permission_set(self, name: str) -> bool:
        """Delete a permission set."""
        try:
            ps = await self.get_permission_set(name)
            if not ps:
                return False

            db = self._get_db()

            db._backend.execute_query(
                "DELETE FROM permission_sets WHERE id = %s",
                (ps.id,)
            )

            logger.info(f"[RBAC:DB] Deleted permission set: {name}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Delete permission set failed: {e}")
            return False

    # =========================================================================
    # LEVEL 3: TEAM OPERATIONS
    # =========================================================================

    async def get_user_teams(self, user_id: str) -> List[Team]:
        """Get all teams a user belongs to."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                """SELECT t.* FROM teams t
                   JOIN team_members tm ON t.id = tm.team_id
                   WHERE tm.user_id = %s AND t.is_active = true""",
                (user_id,)
            )

            if not result:
                return []

            return [Team(
                id=td["id"],
                name=td["name"],
                display_name=td.get("display_name"),
                description=td.get("description"),
                parent_team_id=td.get("parent_team_id"),
                is_active=bool(td.get("is_active", True)),
                created_at=td.get("created_at"),
                updated_at=td.get("updated_at"),
            ) for td in result]

        except Exception as e:
            logger.error(f"[RBAC:DB] Get user teams failed: {e}")
            return []

    async def add_user_to_team(
        self,
        user_id: str,
        team_id: int,
        role: TeamRole = TeamRole.MEMBER,
    ) -> bool:
        """Add a user to a team."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            db._backend.execute_query(
                """INSERT INTO team_members (team_id, user_id, role, joined_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (team_id, user_id) DO UPDATE SET role = %s""",
                (team_id, user_id, role.value, now, role.value)
            )

            logger.info(f"[RBAC:DB] Added user '{user_id}' to team {team_id}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Add user to team failed: {e}")
            return False

    async def remove_user_from_team(self, user_id: str, team_id: int) -> bool:
        """Remove a user from a team."""
        try:
            db = self._get_db()

            db._backend.execute_query(
                "DELETE FROM team_members WHERE team_id = %s AND user_id = %s",
                (team_id, user_id)
            )

            logger.info(f"[RBAC:DB] Removed user '{user_id}' from team {team_id}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Remove user from team failed: {e}")
            return False

    async def get_team(self, team_id: int) -> Optional[Team]:
        """Get a team by ID."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM teams WHERE id = %s",
                (team_id,)
            )

            if not result:
                return None

            td = result[0]
            return Team(
                id=td["id"],
                name=td["name"],
                display_name=td.get("display_name"),
                description=td.get("description"),
                parent_team_id=td.get("parent_team_id"),
                is_active=bool(td.get("is_active", True)),
                created_at=td.get("created_at"),
                updated_at=td.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get team failed: {e}")
            return None

    async def get_team_by_name(self, name: str) -> Optional[Team]:
        """Get a team by name."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM teams WHERE name = %s",
                (name,)
            )

            if not result:
                return None

            td = result[0]
            return Team(
                id=td["id"],
                name=td["name"],
                display_name=td.get("display_name"),
                description=td.get("description"),
                parent_team_id=td.get("parent_team_id"),
                is_active=bool(td.get("is_active", True)),
                created_at=td.get("created_at"),
                updated_at=td.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Get team by name failed: {e}")
            return None

    async def list_teams(self) -> List[Team]:
        """List all teams."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM teams WHERE is_active = true ORDER BY name"
            )

            if not result:
                return []

            return [Team(
                id=td["id"],
                name=td["name"],
                display_name=td.get("display_name"),
                description=td.get("description"),
                parent_team_id=td.get("parent_team_id"),
                is_active=bool(td.get("is_active", True)),
                created_at=td.get("created_at"),
                updated_at=td.get("updated_at"),
            ) for td in result]

        except Exception as e:
            logger.error(f"[RBAC:DB] List teams failed: {e}")
            return []

    async def get_team_members(self, team_id: int) -> List[TeamMember]:
        """Get all members of a team."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                "SELECT * FROM team_members WHERE team_id = %s",
                (team_id,)
            )

            if not result:
                return []

            return [TeamMember(
                team_id=tm["team_id"],
                user_id=tm["user_id"],
                role=TeamRole(tm["role"]),
                joined_at=tm.get("joined_at"),
            ) for tm in result]

        except Exception as e:
            logger.error(f"[RBAC:DB] Get team members failed: {e}")
            return []

    async def create_team(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
    ) -> Optional[Team]:
        """Create a new team."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            db._backend.execute_query(
                """INSERT INTO teams (name, display_name, description, parent_team_id, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (name, display_name or name, description, parent_team_id, True, now, now)
            )

            logger.info(f"[RBAC:DB] Created team: {name}")
            return await self.get_team_by_name(name)

        except Exception as e:
            logger.error(f"[RBAC:DB] Create team failed: {e}")
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
        """Update an existing team."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            updates = ["updated_at = %s"]
            params = [now]

            if name is not None:
                updates.append("name = %s")
                params.append(name)

            if display_name is not None:
                updates.append("display_name = %s")
                params.append(display_name)

            if description is not None:
                updates.append("description = %s")
                params.append(description)

            if parent_team_id is not None:
                updates.append("parent_team_id = %s")
                params.append(parent_team_id)

            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)

            params.append(team_id)

            db._backend.execute_query(
                f"UPDATE teams SET {', '.join(updates)} WHERE id = %s",
                tuple(params)
            )

            logger.info(f"[RBAC:DB] Updated team: {team_id}")
            return await self.get_team(team_id)

        except Exception as e:
            logger.error(f"[RBAC:DB] Update team failed: {e}")
            return None

    async def delete_team(self, team_id: int) -> bool:
        """Delete a team."""
        try:
            db = self._get_db()

            db._backend.execute_query(
                "DELETE FROM teams WHERE id = %s",
                (team_id,)
            )

            logger.info(f"[RBAC:DB] Deleted team: {team_id}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Delete team failed: {e}")
            return False

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
        """Share a record with a user or team."""
        try:
            if not shared_with_user_id and not shared_with_team_id:
                logger.error("[RBAC:DB] Must specify user or team to share with")
                return None

            db = self._get_db()
            now = get_uae_time().isoformat()

            db._backend.execute_query(
                """INSERT INTO record_shares
                   (object_type, record_id, shared_with_user_id, shared_with_team_id,
                    access_level, shared_by, shared_at, expires_at, reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (object_type, record_id, shared_with_user_id, shared_with_team_id,
                 access_level.value, shared_by, now, expires_at, reason)
            )

            logger.info(f"[RBAC:DB] Shared {object_type}:{record_id} by user '{shared_by}'")

            # Return the created share
            return RecordShare(
                object_type=object_type,
                record_id=record_id,
                shared_with_user_id=shared_with_user_id,
                shared_with_team_id=shared_with_team_id,
                access_level=access_level,
                shared_by=shared_by,
                shared_at=now,
                expires_at=expires_at,
                reason=reason,
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Share record failed: {e}")
            return None

    async def revoke_record_share(self, share_id: int) -> bool:
        """Revoke a record share."""
        try:
            db = self._get_db()

            db._backend.execute_query(
                "DELETE FROM record_shares WHERE id = %s",
                (share_id,)
            )

            logger.info(f"[RBAC:DB] Revoked record share: {share_id}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Revoke record share failed: {e}")
            return False

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> List[RecordShare]:
        """Get all shares for a record."""
        try:
            db = self._get_db()

            result = db._backend.execute_query(
                """SELECT * FROM record_shares
                   WHERE object_type = %s AND record_id = %s
                   AND (expires_at IS NULL OR expires_at > NOW())""",
                (object_type, record_id)
            )

            if not result:
                return []

            return [RecordShare(
                id=rs["id"],
                object_type=rs["object_type"],
                record_id=rs["record_id"],
                shared_with_user_id=rs.get("shared_with_user_id"),
                shared_with_team_id=rs.get("shared_with_team_id"),
                access_level=AccessLevel(rs["access_level"]),
                shared_by=rs["shared_by"],
                shared_at=rs.get("shared_at"),
                expires_at=rs.get("expires_at"),
                reason=rs.get("reason"),
            ) for rs in result]

        except Exception as e:
            logger.error(f"[RBAC:DB] Get record shares failed: {e}")
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

        Checks in order:
        1. Direct sharing with user
        2. Team-based sharing
        3. Sharing rules
        """
        try:
            db = self._get_db()

            # 1. Check direct user sharing
            direct_result = db._backend.execute_query(
                """SELECT access_level FROM record_shares
                   WHERE object_type = %s AND record_id = %s
                   AND shared_with_user_id = %s
                   AND (expires_at IS NULL OR expires_at > NOW())""",
                (object_type, record_id, user_id)
            )

            if direct_result:
                access = AccessLevel(direct_result[0]["access_level"])
                if self._access_level_sufficient(access, required_access):
                    return True

            # 2. Check team-based sharing
            user_teams = await self.get_user_teams(user_id)
            team_ids = [t.id for t in user_teams]

            if team_ids:
                placeholders = ", ".join(["%s"] * len(team_ids))
                team_result = db._backend.execute_query(
                    f"""SELECT access_level FROM record_shares
                       WHERE object_type = %s AND record_id = %s
                       AND shared_with_team_id IN ({placeholders})
                       AND (expires_at IS NULL OR expires_at > NOW())""",
                    (object_type, record_id, *team_ids)
                )

                if team_result:
                    for tr in team_result:
                        access = AccessLevel(tr["access_level"])
                        if self._access_level_sufficient(access, required_access):
                            return True

            # 3. Check sharing rules (TODO: implement rule evaluation)
            # For now, return False if no direct/team share found

            return False

        except Exception as e:
            logger.error(f"[RBAC:DB] Check record access failed: {e}")
            return False

    def _access_level_sufficient(self, granted: AccessLevel, required: AccessLevel) -> bool:
        """Check if granted access level is sufficient for required level."""
        access_hierarchy = {
            AccessLevel.READ: 1,
            AccessLevel.READ_WRITE: 2,
            AccessLevel.FULL: 3,
        }
        return access_hierarchy.get(granted, 0) >= access_hierarchy.get(required, 0)

    async def list_sharing_rules(self, object_type: Optional[str] = None) -> List[SharingRule]:
        """List sharing rules, optionally filtered by object type."""
        try:
            db = self._get_db()

            if object_type:
                result = db._backend.execute_query(
                    "SELECT * FROM sharing_rules WHERE object_type = %s AND is_active = true",
                    (object_type,)
                )
            else:
                result = db._backend.execute_query(
                    "SELECT * FROM sharing_rules WHERE is_active = true"
                )

            if not result:
                return []

            return [SharingRule(
                id=sr["id"],
                name=sr["name"],
                description=sr.get("description"),
                object_type=sr["object_type"],
                share_from_type=sr["share_from_type"],
                share_from_id=sr.get("share_from_id"),
                share_to_type=sr["share_to_type"],
                share_to_id=sr.get("share_to_id"),
                access_level=AccessLevel(sr["access_level"]),
                is_active=bool(sr.get("is_active", True)),
                created_at=sr.get("created_at"),
                updated_at=sr.get("updated_at"),
            ) for sr in result]

        except Exception as e:
            logger.error(f"[RBAC:DB] List sharing rules failed: {e}")
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
        """Create a sharing rule."""
        try:
            db = self._get_db()
            now = get_uae_time().isoformat()

            db._backend.execute_query(
                """INSERT INTO sharing_rules
                   (name, description, object_type, share_from_type, share_from_id,
                    share_to_type, share_to_id, access_level, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (name, description, object_type, share_from_type, share_from_id,
                 share_to_type, share_to_id, access_level.value, True, now, now)
            )

            logger.info(f"[RBAC:DB] Created sharing rule: {name}")

            # Return the created rule (simplified)
            return SharingRule(
                name=name,
                description=description,
                object_type=object_type,
                share_from_type=share_from_type,
                share_from_id=share_from_id,
                share_to_type=share_to_type,
                share_to_id=share_to_id,
                access_level=access_level,
                is_active=True,
                created_at=now,
                updated_at=now,
            )

        except Exception as e:
            logger.error(f"[RBAC:DB] Create sharing rule failed: {e}")
            return None

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        """Delete a sharing rule."""
        try:
            db = self._get_db()

            db._backend.execute_query(
                "DELETE FROM sharing_rules WHERE id = %s",
                (rule_id,)
            )

            logger.info(f"[RBAC:DB] Deleted sharing rule: {rule_id}")
            return True

        except Exception as e:
            logger.error(f"[RBAC:DB] Delete sharing rule failed: {e}")
            return False
