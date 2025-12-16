"""
Static configuration-based RBAC provider.

Implements RBACProvider using in-memory static configuration.
Useful for development and testing without database dependencies.

Supports full 4-level enterprise RBAC:
- Level 1: Profiles
- Level 2: Permission Sets
- Level 3: Teams & Hierarchy
- Level 4: Record-Level Sharing
"""

import logging
from datetime import datetime
from typing import Optional

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
)

logger = logging.getLogger("proposal-bot")


class StaticRBACProvider(RBACProvider):
    """
    Static RBAC provider using in-memory configuration.

    Implements full 4-level enterprise RBAC for development/testing.
    All data is stored in memory and lost on restart.

    Usage:
        provider = StaticRBACProvider()

        # Assign profile
        await provider.assign_profile("user-123", "sales_user")

        # Add permission set
        await provider.assign_permission_set("user-123", "api_access")

        # Add to team
        await provider.add_user_to_team("user-123", 1)

        # Share a record
        await provider.share_record("proposal", "prop-1", "user-123",
                                     shared_with_user_id="user-456")
    """

    def __init__(self):
        """Initialize static RBAC provider with empty in-memory stores."""
        # Level 1: Profiles
        self._profiles: dict[str, Profile] = {}
        self._user_profiles: dict[str, str] = {}  # user_id -> profile_name

        # Level 2: Permission Sets
        self._permission_sets: dict[str, PermissionSet] = {}
        self._user_permission_sets: dict[str, list[str]] = {}  # user_id -> [ps_names]

        # Level 3: Teams
        self._teams: dict[int, Team] = {}
        self._team_members: dict[int, list[TeamMember]] = {}  # team_id -> [members]
        self._next_team_id: int = 1

        # Level 4: Record Sharing
        self._sharing_rules: dict[int, SharingRule] = {}
        self._record_shares: dict[int, RecordShare] = {}
        self._next_share_id: int = 1
        self._next_rule_id: int = 1

        # Record ownership tracking (object_type:record_id -> owner_user_id)
        self._record_owners: dict[str, str] = {}

        # Available permissions
        self._permissions: list[Permission] = []

        logger.info("[RBAC:STATIC] Provider initialized")

    @property
    def name(self) -> str:
        return "static"

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def set_record_owner(self, object_type: str, record_id: str, owner_id: str) -> None:
        """Set the owner of a record (for testing)."""
        key = f"{object_type}:{record_id}"
        self._record_owners[key] = owner_id

    def get_record_owner(self, object_type: str, record_id: str) -> Optional[str]:
        """Get the owner of a record."""
        key = f"{object_type}:{record_id}"
        return self._record_owners.get(key)

    def _check_permission_match(self, granted: str, requested: str) -> bool:
        """Check if a granted permission matches a requested permission."""
        if granted == requested:
            return True

        # Wildcard matching
        granted_parts = granted.split(":")
        requested_parts = requested.split(":")

        if len(granted_parts) != 3 or len(requested_parts) != 3:
            return False

        for g, r in zip(granted_parts, requested_parts, strict=False):
            if g != "*" and g != r:
                # "manage" implies all actions
                if granted_parts[2] == "manage":
                    return True
                return False

        return True

    def _access_level_sufficient(self, granted: AccessLevel, required: AccessLevel) -> bool:
        """Check if granted access level is sufficient for required level."""
        levels = {AccessLevel.READ: 1, AccessLevel.READ_WRITE: 2, AccessLevel.FULL: 3}
        return levels.get(granted, 0) >= levels.get(required, 0)

    # =========================================================================
    # LEVEL 1: PROFILE OPERATIONS
    # =========================================================================

    async def get_user_profile(self, user_id: str) -> Optional[Profile]:
        """Get the profile assigned to a user."""
        profile_name = self._user_profiles.get(user_id)
        if profile_name:
            return self._profiles.get(profile_name)
        return None

    async def assign_profile(self, user_id: str, profile_name: str) -> bool:
        """Assign a profile to a user."""
        if profile_name not in self._profiles:
            logger.warning(f"[RBAC:STATIC] Unknown profile: {profile_name}")
            return False

        self._user_profiles[user_id] = profile_name
        logger.info(f"[RBAC:STATIC] Assigned profile '{profile_name}' to user '{user_id}'")
        return True

    async def get_profile(self, profile_name: str) -> Optional[Profile]:
        """Get a profile by name."""
        return self._profiles.get(profile_name)

    async def list_profiles(self) -> list[Profile]:
        """List all available profiles."""
        return list(self._profiles.values())

    async def create_profile(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[list[str]] = None,
    ) -> Optional[Profile]:
        """Create a new profile."""
        if name in self._profiles:
            logger.warning(f"[RBAC:STATIC] Profile already exists: {name}")
            return None

        profile = Profile(
            id=len(self._profiles) + 1,
            name=name,
            display_name=display_name,
            description=description,
            permissions=set(permissions or []),
            is_system=False,
            created_at=datetime.utcnow().isoformat(),
        )

        self._profiles[name] = profile
        logger.info(f"[RBAC:STATIC] Created profile: {name}")
        return profile

    async def update_profile(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[list[str]] = None,
    ) -> Optional[Profile]:
        """Update an existing profile."""
        profile = self._profiles.get(name)
        if not profile:
            return None

        if profile.is_system:
            logger.warning(f"[RBAC:STATIC] Cannot update system profile: {name}")
            return None

        if display_name is not None:
            profile.display_name = display_name
        if description is not None:
            profile.description = description
        if permissions is not None:
            profile.permissions = set(permissions)

        profile.updated_at = datetime.utcnow().isoformat()
        logger.info(f"[RBAC:STATIC] Updated profile: {name}")
        return profile

    async def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        profile = self._profiles.get(name)
        if not profile:
            return False

        if profile.is_system:
            logger.warning(f"[RBAC:STATIC] Cannot delete system profile: {name}")
            return False

        del self._profiles[name]
        # Remove profile assignments
        for user_id, pname in list(self._user_profiles.items()):
            if pname == name:
                del self._user_profiles[user_id]

        logger.info(f"[RBAC:STATIC] Deleted profile: {name}")
        return True

    # =========================================================================
    # LEVEL 2: PERMISSION SET OPERATIONS
    # =========================================================================

    async def get_user_permission_sets(self, user_id: str) -> list[PermissionSet]:
        """Get all permission sets assigned to a user."""
        ps_names = self._user_permission_sets.get(user_id, [])
        result = []
        for name in ps_names:
            ps = self._permission_sets.get(name)
            if ps and ps.is_active:
                result.append(ps)
        return result

    async def assign_permission_set(
        self,
        user_id: str,
        permission_set_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Assign a permission set to a user."""
        if permission_set_name not in self._permission_sets:
            logger.warning(f"[RBAC:STATIC] Unknown permission set: {permission_set_name}")
            return False

        if user_id not in self._user_permission_sets:
            self._user_permission_sets[user_id] = []

        if permission_set_name not in self._user_permission_sets[user_id]:
            self._user_permission_sets[user_id].append(permission_set_name)

        logger.info(f"[RBAC:STATIC] Assigned permission set '{permission_set_name}' to user '{user_id}'")
        return True

    async def revoke_permission_set(self, user_id: str, permission_set_name: str) -> bool:
        """Revoke a permission set from a user."""
        if user_id not in self._user_permission_sets:
            return False

        if permission_set_name in self._user_permission_sets[user_id]:
            self._user_permission_sets[user_id].remove(permission_set_name)
            logger.info(f"[RBAC:STATIC] Revoked permission set '{permission_set_name}' from user '{user_id}'")
            return True

        return False

    async def get_permission_set(self, name: str) -> Optional[PermissionSet]:
        """Get a permission set by name."""
        return self._permission_sets.get(name)

    async def list_permission_sets(self) -> list[PermissionSet]:
        """List all available permission sets."""
        return list(self._permission_sets.values())

    async def create_permission_set(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        permissions: Optional[list[str]] = None,
    ) -> Optional[PermissionSet]:
        """Create a new permission set."""
        if name in self._permission_sets:
            logger.warning(f"[RBAC:STATIC] Permission set already exists: {name}")
            return None

        ps = PermissionSet(
            id=len(self._permission_sets) + 1,
            name=name,
            display_name=display_name,
            description=description,
            permissions=set(permissions or []),
            is_active=True,
            created_at=datetime.utcnow().isoformat(),
        )

        self._permission_sets[name] = ps
        logger.info(f"[RBAC:STATIC] Created permission set: {name}")
        return ps

    async def update_permission_set(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[list[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PermissionSet]:
        """Update an existing permission set."""
        ps = self._permission_sets.get(name)
        if not ps:
            return None

        if display_name is not None:
            ps.display_name = display_name
        if description is not None:
            ps.description = description
        if permissions is not None:
            ps.permissions = set(permissions)
        if is_active is not None:
            ps.is_active = is_active

        ps.updated_at = datetime.utcnow().isoformat()
        logger.info(f"[RBAC:STATIC] Updated permission set: {name}")
        return ps

    async def delete_permission_set(self, name: str) -> bool:
        """Delete a permission set."""
        if name not in self._permission_sets:
            return False

        del self._permission_sets[name]
        # Remove assignments
        for user_id in self._user_permission_sets:
            if name in self._user_permission_sets[user_id]:
                self._user_permission_sets[user_id].remove(name)

        logger.info(f"[RBAC:STATIC] Deleted permission set: {name}")
        return True

    # =========================================================================
    # LEVEL 3: TEAM OPERATIONS
    # =========================================================================

    async def get_user_teams(self, user_id: str) -> list[Team]:
        """Get all teams a user belongs to."""
        teams = []
        for team_id, members in self._team_members.items():
            for member in members:
                if member.user_id == user_id:
                    team = self._teams.get(team_id)
                    if team and team.is_active:
                        teams.append(team)
                    break
        return teams

    async def add_user_to_team(
        self,
        user_id: str,
        team_id: int,
        role: TeamRole = TeamRole.MEMBER,
    ) -> bool:
        """Add a user to a team."""
        if team_id not in self._teams:
            logger.warning(f"[RBAC:STATIC] Unknown team: {team_id}")
            return False

        if team_id not in self._team_members:
            self._team_members[team_id] = []

        # Check if already a member
        for member in self._team_members[team_id]:
            if member.user_id == user_id:
                logger.info(f"[RBAC:STATIC] User '{user_id}' already in team {team_id}")
                return True

        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            role=role,
            joined_at=datetime.utcnow().isoformat(),
        )
        self._team_members[team_id].append(member)
        logger.info(f"[RBAC:STATIC] Added user '{user_id}' to team {team_id}")
        return True

    async def remove_user_from_team(self, user_id: str, team_id: int) -> bool:
        """Remove a user from a team."""
        if team_id not in self._team_members:
            return False

        for i, member in enumerate(self._team_members[team_id]):
            if member.user_id == user_id:
                self._team_members[team_id].pop(i)
                logger.info(f"[RBAC:STATIC] Removed user '{user_id}' from team {team_id}")
                return True

        return False

    async def get_team(self, team_id: int) -> Optional[Team]:
        """Get a team by ID."""
        return self._teams.get(team_id)

    async def get_team_by_name(self, name: str) -> Optional[Team]:
        """Get a team by name."""
        for team in self._teams.values():
            if team.name == name:
                return team
        return None

    async def list_teams(self) -> list[Team]:
        """List all teams."""
        return list(self._teams.values())

    async def get_team_members(self, team_id: int) -> list[TeamMember]:
        """Get all members of a team."""
        return self._team_members.get(team_id, [])

    async def create_team(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_team_id: Optional[int] = None,
    ) -> Optional[Team]:
        """Create a new team."""
        # Check for duplicate name
        for team in self._teams.values():
            if team.name == name:
                logger.warning(f"[RBAC:STATIC] Team already exists: {name}")
                return None

        team_id = self._next_team_id
        self._next_team_id += 1

        team = Team(
            id=team_id,
            name=name,
            display_name=display_name or name,
            description=description,
            parent_team_id=parent_team_id,
            is_active=True,
            created_at=datetime.utcnow().isoformat(),
        )

        self._teams[team_id] = team
        self._team_members[team_id] = []
        logger.info(f"[RBAC:STATIC] Created team: {name} (id={team_id})")
        return team

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
        team = self._teams.get(team_id)
        if not team:
            return None

        if name is not None:
            team.name = name
        if display_name is not None:
            team.display_name = display_name
        if description is not None:
            team.description = description
        if parent_team_id is not None:
            team.parent_team_id = parent_team_id
        if is_active is not None:
            team.is_active = is_active

        team.updated_at = datetime.utcnow().isoformat()
        logger.info(f"[RBAC:STATIC] Updated team: {team_id}")
        return team

    async def delete_team(self, team_id: int) -> bool:
        """Delete a team."""
        if team_id not in self._teams:
            return False

        del self._teams[team_id]
        if team_id in self._team_members:
            del self._team_members[team_id]

        logger.info(f"[RBAC:STATIC] Deleted team: {team_id}")
        return True

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
        if not shared_with_user_id and not shared_with_team_id:
            logger.warning("[RBAC:STATIC] Must share with user or team")
            return None

        share_id = self._next_share_id
        self._next_share_id += 1

        share = RecordShare(
            id=share_id,
            object_type=object_type,
            record_id=record_id,
            shared_with_user_id=shared_with_user_id,
            shared_with_team_id=shared_with_team_id,
            access_level=access_level,
            shared_by=shared_by,
            shared_at=datetime.utcnow().isoformat(),
            expires_at=expires_at,
            reason=reason,
        )

        self._record_shares[share_id] = share
        logger.info(f"[RBAC:STATIC] Created record share: {share_id}")
        return share

    async def revoke_record_share(self, share_id: int) -> bool:
        """Revoke a record share."""
        if share_id not in self._record_shares:
            return False

        del self._record_shares[share_id]
        logger.info(f"[RBAC:STATIC] Revoked record share: {share_id}")
        return True

    async def get_record_shares(
        self,
        object_type: str,
        record_id: str,
    ) -> list[RecordShare]:
        """Get all shares for a record."""
        shares = []
        for share in self._record_shares.values():
            if share.object_type == object_type and share.record_id == record_id:
                shares.append(share)
        return shares

    async def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        required_access: AccessLevel = AccessLevel.READ,
    ) -> bool:
        """Check if user has access to a specific record."""
        # 1. Check ownership
        owner = self.get_record_owner(object_type, record_id)
        if owner == user_id:
            return True

        # 2. Check direct user share
        for share in self._record_shares.values():
            if (share.object_type == object_type and
                share.record_id == record_id and
                share.shared_with_user_id == user_id):
                if self._access_level_sufficient(share.access_level, required_access):
                    return True

        # 3. Check team-based sharing
        user_teams = await self.get_user_teams(user_id)
        user_team_ids = {t.id for t in user_teams}

        for share in self._record_shares.values():
            if (share.object_type == object_type and
                share.record_id == record_id and
                share.shared_with_team_id in user_team_ids):
                if self._access_level_sufficient(share.access_level, required_access):
                    return True

        # 4. Check sharing rules
        for rule in self._sharing_rules.values():
            if rule.object_type != object_type or not rule.is_active:
                continue

            # Check if user matches share_to criteria
            matches_share_to = False
            if rule.share_to_type == "all":
                matches_share_to = True
            elif rule.share_to_type == "team" and rule.share_to_id:
                matches_share_to = int(rule.share_to_id) in user_team_ids
            elif rule.share_to_type == "profile" and rule.share_to_id:
                profile = await self.get_user_profile(user_id)
                if profile:
                    matches_share_to = str(profile.id) == rule.share_to_id

            if matches_share_to and self._access_level_sufficient(rule.access_level, required_access):
                return True

        return False

    async def list_sharing_rules(self, object_type: Optional[str] = None) -> list[SharingRule]:
        """List sharing rules, optionally filtered by object type."""
        rules = list(self._sharing_rules.values())
        if object_type:
            rules = [r for r in rules if r.object_type == object_type]
        return rules

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
        rule_id = self._next_rule_id
        self._next_rule_id += 1

        rule = SharingRule(
            id=rule_id,
            name=name,
            description=description,
            object_type=object_type,
            share_from_type=share_from_type,
            share_from_id=share_from_id,
            share_to_type=share_to_type,
            share_to_id=share_to_id,
            access_level=access_level,
            is_active=True,
            created_at=datetime.utcnow().isoformat(),
        )

        self._sharing_rules[rule_id] = rule
        logger.info(f"[RBAC:STATIC] Created sharing rule: {name} (id={rule_id})")
        return rule

    async def delete_sharing_rule(self, rule_id: int) -> bool:
        """Delete a sharing rule."""
        if rule_id not in self._sharing_rules:
            return False

        del self._sharing_rules[rule_id]
        logger.info(f"[RBAC:STATIC] Deleted sharing rule: {rule_id}")
        return True

    # =========================================================================
    # UNIFIED PERMISSION OPERATIONS
    # =========================================================================

    async def get_user_permissions(self, user_id: str) -> set[str]:
        """Get all permissions for a user from profile and permission sets."""
        permissions: set[str] = set()

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
        """Check if user has a specific permission."""
        # Check profile permissions
        profile = await self.get_user_profile(user_id)
        if profile and profile.has_permission(permission):
            return True

        # Check permission sets
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

    async def list_permissions(self) -> list[Permission]:
        """List all available permissions."""
        if not self._permissions:
            # Lazy load from modules
            from integrations.rbac.modules import get_all_permissions
            self._permissions = get_all_permissions()
        return list(self._permissions)

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize_defaults(self) -> bool:
        """Initialize default profiles and permission sets."""
        logger.info("[RBAC:STATIC] Initializing default configuration")

        # Create default profiles
        admin_profile = await self.create_profile(
            name="system_admin",
            display_name="System Administrator",
            description="Full system access",
            permissions=["*:*:*"],
        )
        if admin_profile:
            admin_profile.is_system = True

        sales_profile = await self.create_profile(
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
        if sales_profile:
            sales_profile.is_system = True

        readonly_profile = await self.create_profile(
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
        if readonly_profile:
            readonly_profile.is_system = True

        # Create default permission sets
        await self.create_permission_set(
            name="api_access",
            display_name="API Access",
            description="Allows API token generation and usage",
            permissions=["core:api:access"],
        )

        await self.create_permission_set(
            name="export_reports",
            display_name="Export Reports",
            description="Allows exporting reports to various formats",
            permissions=["sales:reports:export"],
        )

        await self.create_permission_set(
            name="admin_users",
            display_name="User Administration",
            description="Allows managing users",
            permissions=["core:users:manage"],
        )

        logger.info("[RBAC:STATIC] Default configuration initialized")
        return True
