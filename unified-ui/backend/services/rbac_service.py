"""
RBAC (Role-Based Access Control) service for unified-ui.

[VERIFIED] Mirrors server.js lines 188-546:
- getUserRBACData() function (lines 188-466)
- getUserRecordShares() helper (lines 487-517)
- RBAC cache management (lines 519-546)

5-Level RBAC System:
1. Profiles (base permissions for job function)
2. Permission Sets (additive, can be temporary with expiration)
3. Teams & Hierarchy (team-based access, manager sees subordinates)
4. Record Sharing (share specific records with users/teams)
5. Company Access (for data filtering in proposal-bot)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.config import get_settings
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

# =============================================================================
# RBAC CACHE - server.js:519-546
# =============================================================================

# RBAC cache: {user_id: {"data": RBACContext, "ts": timestamp}}
_rbac_cache: dict[str, dict[str, Any]] = {}


def invalidate_rbac_cache(user_id: str) -> None:
    """
    Invalidate RBAC cache for a user.
    Mirrors server.js:524-529 (invalidateRBACCache)
    """
    if user_id and user_id in _rbac_cache:
        del _rbac_cache[user_id]
        logger.info(f"[RBAC CACHE] Invalidated cache for user {user_id}")


def invalidate_rbac_cache_for_users(user_ids: list[str]) -> None:
    """
    Invalidate RBAC cache for multiple users.
    Mirrors server.js:531-539 (invalidateRBACCacheForUsers)
    """
    for user_id in user_ids or []:
        if user_id in _rbac_cache:
            del _rbac_cache[user_id]
    if user_ids:
        logger.info(f"[RBAC CACHE] Invalidated cache for {len(user_ids)} users")


def clear_all_rbac_cache() -> None:
    """
    Clear all RBAC cache (use sparingly - for global permission changes).
    Mirrors server.js:541-546 (clearAllRBACCache)
    """
    count = len(_rbac_cache)
    _rbac_cache.clear()
    logger.info(f"[RBAC CACHE] Cleared all {count} cached entries")


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class TeamInfo:
    """Team membership info."""
    id: int
    name: str
    display_name: Optional[str]
    role: str  # 'member' or 'leader'
    parent_team_id: Optional[int]


@dataclass
class PermissionSetInfo:
    """Permission set assignment info."""
    id: int
    name: str
    expires_at: Optional[str]


@dataclass
class SharingRuleInfo:
    """Sharing rule info."""
    id: int
    name: str
    object_type: str
    share_from_type: str
    share_from_id: Optional[str]
    access_level: str


@dataclass
class SharedRecordInfo:
    """Shared record info."""
    record_id: str
    access_level: str  # 'read', 'read_write', 'full'
    shared_by: Optional[str]
    reason: Optional[str]


@dataclass
class RBACContext:
    """
    Complete RBAC context for a user.
    Mirrors server.js:447-460 return structure.
    """
    # Level 1: Profile
    profile: str
    # Level 1 + 2: Combined permissions
    permissions: list[str]
    # Level 2: Permission sets
    permission_sets: list[PermissionSetInfo] = field(default_factory=list)
    # Level 3: Teams
    teams: list[TeamInfo] = field(default_factory=list)
    # Level 3: Hierarchy
    manager_id: Optional[str] = None
    subordinate_ids: list[str] = field(default_factory=list)
    # Level 4: Sharing
    sharing_rules: list[SharingRuleInfo] = field(default_factory=list)
    shared_records: dict[str, list[SharedRecordInfo]] = field(default_factory=dict)
    shared_from_user_ids: list[str] = field(default_factory=list)
    # Level 5: Company access
    companies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for JSON serialization and headers)."""
        return {
            "profile": self.profile,
            "permissions": self.permissions,
            "permissionSets": [
                {"id": ps.id, "name": ps.name, "expiresAt": ps.expires_at}
                for ps in self.permission_sets
            ],
            "teams": [
                {
                    "id": t.id,
                    "name": t.name,
                    "displayName": t.display_name,
                    "role": t.role,
                    "parentTeamId": t.parent_team_id,
                }
                for t in self.teams
            ],
            "managerId": self.manager_id,
            "subordinateIds": self.subordinate_ids,
            "sharingRules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "objectType": r.object_type,
                    "shareFromType": r.share_from_type,
                    "shareFromId": r.share_from_id,
                    "accessLevel": r.access_level,
                }
                for r in self.sharing_rules
            ],
            "sharedRecords": {
                obj_type: [
                    {
                        "recordId": sr.record_id,
                        "accessLevel": sr.access_level,
                        "sharedBy": sr.shared_by,
                        "reason": sr.reason,
                    }
                    for sr in shares
                ]
                for obj_type, shares in self.shared_records.items()
            },
            "sharedFromUserIds": self.shared_from_user_ids,
            "companies": self.companies,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def get_user_record_shares(
    user_id: str, team_ids: list[int]
) -> list[dict[str, Any]]:
    """
    Get record shares for a user (records shared with them or their teams).

    Mirrors server.js:487-517 (getUserRecordShares)
    """
    supabase = get_supabase()
    if not supabase:
        return []

    try:
        now = datetime.utcnow().isoformat()

        # Get shares to this user - server.js:493-498
        user_shares_response = (
            supabase.table("record_shares")
            .select("*")
            .eq("shared_with_user_id", user_id)
            .or_(f"expires_at.is.null,expires_at.gt.{now}")
            .execute()
        )
        user_shares = user_shares_response.data or []

        # Get shares to user's teams - server.js:500-510
        team_shares = []
        if team_ids:
            team_shares_response = (
                supabase.table("record_shares")
                .select("*")
                .in_("shared_with_team_id", team_ids)
                .or_(f"expires_at.is.null,expires_at.gt.{now}")
                .execute()
            )
            team_shares = team_shares_response.data or []

        return user_shares + team_shares

    except Exception as e:
        logger.error(f"[RBAC] Error fetching record shares: {e}")
        return []


# =============================================================================
# MAIN RBAC FUNCTION
# =============================================================================

async def get_user_rbac_data(user_id: str, use_cache: bool = True) -> Optional[RBACContext]:
    """
    Fetch complete RBAC context for a user.

    Mirrors server.js:188-466 (getUserRBACData)

    5 Levels:
    1. Profile (base role)
    2. Permission sets (additive, with expiration)
    3. Teams & hierarchy
    4. Sharing rules & record shares
    5. Company access

    Args:
        user_id: The user's ID
        use_cache: Whether to use cached data (default True)

    Returns:
        RBACContext if user exists and is active, None otherwise
    """
    settings = get_settings()
    supabase = get_supabase()

    # Dev mode fallback - server.js:189-198
    if not supabase:
        return RBACContext(
            profile="sales_user",
            permissions=["sales:*:*"],
            teams=[],
            manager_id=None,
            subordinate_ids=[],
        )

    # Check cache - mirrors server.js:570-578
    if use_cache and user_id in _rbac_cache:
        cached = _rbac_cache[user_id]
        cache_age = (datetime.utcnow() - cached["ts"]).total_seconds()
        if cache_age < settings.RBAC_CACHE_TTL_SECONDS:
            return cached["data"]

    try:
        # =====================================================================
        # LEVEL 1: Get user with profile - server.js:201-235
        # =====================================================================
        user_response = (
            supabase.table("users")
            .select("id, email, name, profile_id, is_active, manager_id, profiles(id, name, display_name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        user_data = user_response.data
        if not user_data:
            logger.warning(f"[RBAC] User {user_id} not found in users table - ACCESS DENIED")
            return None

        # Check if user is active - server.js:215-219
        if user_data.get("is_active") is False:
            logger.warning(f"[RBAC] User {user_id} is deactivated - ACCESS DENIED")
            return None

        profile = user_data.get("profiles") or {}
        profile_name = profile.get("name") or "sales_user"

        # Get permissions from profile - server.js:224-235
        permissions: list[str] = []
        profile_id = profile.get("id")
        if profile_id:
            perms_response = (
                supabase.table("profile_permissions")
                .select("permission")
                .eq("profile_id", profile_id)
                .execute()
            )
            if perms_response.data:
                permissions = [p["permission"] for p in perms_response.data]

        # =====================================================================
        # LEVEL 2: Permission Sets (with expiration check) - server.js:237-274
        # =====================================================================
        now = datetime.utcnow().isoformat()
        perm_sets_response = (
            supabase.table("user_permission_sets")
            .select("permission_set_id, expires_at, permission_sets(id, name, is_active)")
            .eq("user_id", user_id)
            .execute()
        )

        active_permission_sets: list[PermissionSetInfo] = []
        if perm_sets_response.data:
            for ups in perm_sets_response.data:
                perm_set = ups.get("permission_sets") or {}

                # Skip if permission set is inactive - server.js:250
                if not perm_set.get("is_active"):
                    continue

                # Skip if expired - server.js:252-256
                expires_at = ups.get("expires_at")
                if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.utcnow():
                    logger.info(f"[RBAC] Permission set {perm_set.get('name')} expired for user {user_id}")
                    continue

                active_permission_sets.append(
                    PermissionSetInfo(
                        id=perm_set.get("id"),
                        name=perm_set.get("name"),
                        expires_at=expires_at,
                    )
                )

                # Get permissions from this permission set - server.js:264-272
                ps_perms_response = (
                    supabase.table("permission_set_permissions")
                    .select("permission")
                    .eq("permission_set_id", perm_set.get("id"))
                    .execute()
                )
                if ps_perms_response.data:
                    permissions.extend([p["permission"] for p in ps_perms_response.data])

        # =====================================================================
        # LEVEL 3: Teams & Hierarchy - server.js:276-327
        # =====================================================================

        # Get user's teams - server.js:280-299
        teams_response = (
            supabase.table("team_members")
            .select("role, teams(id, name, display_name, parent_team_id, is_active)")
            .eq("user_id", user_id)
            .execute()
        )

        teams: list[TeamInfo] = []
        if teams_response.data:
            for tm in teams_response.data:
                team = tm.get("teams") or {}
                if team.get("is_active"):
                    teams.append(
                        TeamInfo(
                            id=team.get("id"),
                            name=team.get("name"),
                            display_name=team.get("display_name"),
                            role=tm.get("role"),
                            parent_team_id=team.get("parent_team_id"),
                        )
                    )

        # Get subordinates (users where this user is their manager) - server.js:301-308
        subordinates_response = (
            supabase.table("users")
            .select("id")
            .eq("manager_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        subordinate_ids = [s["id"] for s in subordinates_response.data or []]

        # Get team members for teams where user is leader - server.js:310-324
        led_team_ids = [t.id for t in teams if t.role == "leader"]
        team_member_ids: list[str] = []

        if led_team_ids:
            team_members_response = (
                supabase.table("team_members")
                .select("user_id")
                .in_("team_id", led_team_ids)
                .neq("user_id", user_id)
                .execute()
            )
            if team_members_response.data:
                team_member_ids = [tm["user_id"] for tm in team_members_response.data]

        # Combine subordinates - server.js:326-327
        all_subordinate_ids = list(set(subordinate_ids + team_member_ids))

        # =====================================================================
        # LEVEL 4: Sharing Rules & Record Shares - server.js:329-388
        # =====================================================================

        user_team_ids = [t.id for t in teams]

        # Get record shares - server.js:336-353
        record_shares = await get_user_record_shares(user_id, user_team_ids)
        shared_records: dict[str, list[SharedRecordInfo]] = {}
        for share in record_shares:
            obj_type = share.get("object_type")
            if obj_type not in shared_records:
                shared_records[obj_type] = []
            shared_records[obj_type].append(
                SharedRecordInfo(
                    record_id=share.get("record_id"),
                    access_level=share.get("access_level"),
                    shared_by=share.get("shared_by"),
                    reason=share.get("reason"),
                )
            )

        # Get sharing rules - server.js:355-388
        rules_response = (
            supabase.table("sharing_rules")
            .select("*")
            .eq("is_active", True)
            .execute()
        )

        applicable_rules: list[SharingRuleInfo] = []
        if rules_response.data:
            for rule in rules_response.data:
                applies = False

                # Check if rule shares TO this user - server.js:368-375
                share_to_type = rule.get("share_to_type")
                share_to_id = rule.get("share_to_id")

                if share_to_type == "all":
                    applies = True
                elif share_to_type == "profile" and share_to_id == profile_name:
                    applies = True
                elif share_to_type == "team":
                    try:
                        if int(share_to_id) in user_team_ids:
                            applies = True
                    except (ValueError, TypeError):
                        pass

                if applies:
                    applicable_rules.append(
                        SharingRuleInfo(
                            id=rule.get("id"),
                            name=rule.get("name"),
                            object_type=rule.get("object_type"),
                            share_from_type=rule.get("share_from_type"),
                            share_from_id=rule.get("share_from_id"),
                            access_level=rule.get("access_level"),
                        )
                    )

        # =====================================================================
        # LEVEL 5: Company Access - server.js:390-413
        # =====================================================================
        companies_response = (
            supabase.table("user_companies")
            .select("company_id, companies(id, code, is_group)")
            .eq("user_id", user_id)
            .execute()
        )

        companies: list[str] = []
        if companies_response.data:
            assigned_company_ids = [
                uc.get("company_id")
                for uc in companies_response.data
                if uc.get("company_id")
            ]

            if assigned_company_ids:
                # Use recursive CTE to get accessible schemas - server.js:405-412
                schemas_response = supabase.rpc(
                    "get_accessible_schemas",
                    {"p_company_ids": assigned_company_ids}
                ).execute()

                if schemas_response.data:
                    companies = [
                        s.get("schema_name")
                        for s in schemas_response.data
                        if s.get("schema_name")
                    ]

        # Get user IDs accessible via sharing rules - server.js:415-442
        shared_from_user_ids: list[str] = []
        for rule in applicable_rules:
            if rule.share_from_type == "profile":
                # Get all users with this profile - server.js:420-429
                profile_users_response = (
                    supabase.table("users")
                    .select("id, profiles!inner(name)")
                    .eq("profiles.name", rule.share_from_id)
                    .eq("is_active", True)
                    .execute()
                )
                if profile_users_response.data:
                    shared_from_user_ids.extend([u["id"] for u in profile_users_response.data])

            elif rule.share_from_type == "team":
                # Get all users in this team - server.js:430-439
                try:
                    team_users_response = (
                        supabase.table("team_members")
                        .select("user_id")
                        .eq("team_id", int(rule.share_from_id))
                        .execute()
                    )
                    if team_users_response.data:
                        shared_from_user_ids.extend([u["user_id"] for u in team_users_response.data])
                except (ValueError, TypeError):
                    pass

        # =====================================================================
        # Build and cache result - server.js:444-460
        # =====================================================================
        rbac_context = RBACContext(
            profile=profile_name,
            permissions=list(set(permissions)),  # Deduplicate
            permission_sets=active_permission_sets,
            teams=teams,
            manager_id=user_data.get("manager_id"),
            subordinate_ids=all_subordinate_ids,
            sharing_rules=applicable_rules,
            shared_records=shared_records,
            shared_from_user_ids=list(set(shared_from_user_ids)),
            companies=companies,
        )

        # Cache the result
        _rbac_cache[user_id] = {
            "data": rbac_context,
            "ts": datetime.utcnow(),
        }

        return rbac_context

    except Exception as e:
        # Error fetching - reject access for safety - server.js:462-465
        logger.error(f"[RBAC] Error fetching RBAC for {user_id}: {e}")
        return None
