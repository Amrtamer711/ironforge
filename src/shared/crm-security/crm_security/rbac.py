"""
Role-based access control utilities.

Permission format: {module}:{resource}:{action}
Examples:
- sales:proposals:create
- assets:locations:read
- *:*:* (full admin)
- sales:*:* (all sales permissions)

Extracted from sales-module/api/auth.py for shared use.
"""

import logging

logger = logging.getLogger(__name__)


def matches_wildcard(pattern: str, permission: str) -> bool:
    """
    Check if a wildcard pattern matches a permission.

    Supports:
    - "*:*:*" matches everything
    - "sales:*:*" matches all sales permissions
    - "sales:proposals:*" matches all proposal actions
    - "manage" action implies all other actions

    Args:
        pattern: Permission pattern (may contain wildcards)
        permission: The specific permission to check

    Returns:
        True if pattern matches permission
    """
    if pattern == "*:*:*":
        return True

    pattern_parts = pattern.split(":")
    perm_parts = permission.split(":")

    if len(pattern_parts) != 3 or len(perm_parts) != 3:
        return False

    for i, (p, t) in enumerate(zip(pattern_parts, perm_parts, strict=False)):
        if p != "*" and p != t:
            # "manage" action implies all other actions
            if i == 2 and p == "manage":
                return True
            return False

    return True


def has_permission(permissions: list[str], required: str) -> bool:
    """
    Check if user has a permission (direct match or wildcard).

    Args:
        permissions: List of user's permissions
        required: The permission being checked

    Returns:
        True if user has the required permission
    """
    if required in permissions:
        return True

    return any(matches_wildcard(perm, required) for perm in permissions)


def has_any_permission(permissions: list[str], required: list[str]) -> bool:
    """
    Check if user has any of the specified permissions.

    Args:
        permissions: List of user's permissions
        required: List of permissions to check

    Returns:
        True if user has at least one of the required permissions
    """
    return any(has_permission(permissions, r) for r in required)


def has_all_permissions(permissions: list[str], required: list[str]) -> bool:
    """
    Check if user has all of the specified permissions.

    Args:
        permissions: List of user's permissions
        required: List of permissions to check

    Returns:
        True if user has all required permissions
    """
    return all(has_permission(permissions, r) for r in required)


# Common permission patterns for reference
PERMISSIONS = {
    # Core/Platform
    "core:users:read": "View users",
    "core:users:create": "Create users",
    "core:users:update": "Edit users",
    "core:users:delete": "Delete users",
    "core:users:manage": "Full control over users",
    "core:system:admin": "System administration",
    "core:system:config": "Manage system configuration",
    "core:ai_costs:read": "View AI cost reports",
    "core:ai_costs:manage": "Manage AI cost tracking",
    "core:api:access": "API access",
    "core:api_keys:read": "View API keys",
    "core:api_keys:create": "Create API keys",
    "core:api_keys:delete": "Delete API keys",
    "core:api_keys:manage": "Full control over API keys",
    "core:profiles:read": "View profiles",
    "core:profiles:create": "Create profiles",
    "core:profiles:update": "Update profiles",
    "core:profiles:delete": "Delete profiles",
    "core:profiles:manage": "Full control over profiles",
    "core:permission_sets:read": "View permission sets",
    "core:permission_sets:create": "Create permission sets",
    "core:permission_sets:update": "Update permission sets",
    "core:permission_sets:delete": "Delete permission sets",
    "core:permission_sets:manage": "Full control over permission sets",
    "core:teams:read": "View teams",
    "core:teams:create": "Create teams",
    "core:teams:update": "Update teams",
    "core:teams:delete": "Delete teams",
    "core:teams:manage": "Full control over teams",
    "core:sharing_rules:read": "View sharing rules",
    "core:sharing_rules:create": "Create sharing rules",
    "core:sharing_rules:delete": "Delete sharing rules",
    "core:sharing_rules:manage": "Full control over sharing rules",
    "core:files:read": "Read any user's files (admin)",
    "core:files:manage": "Full control over all files",

    # Asset Management
    "assets:networks:read": "View networks",
    "assets:networks:create": "Create networks",
    "assets:networks:update": "Update networks",
    "assets:networks:delete": "Delete networks",
    "assets:networks:manage": "Full control over networks",
    "assets:locations:read": "View locations",
    "assets:locations:create": "Create locations",
    "assets:locations:update": "Update locations",
    "assets:locations:delete": "Delete locations",
    "assets:locations:manage": "Full control over locations",
    "assets:packages:read": "View packages",
    "assets:packages:create": "Create packages",
    "assets:packages:update": "Update packages",
    "assets:packages:delete": "Delete packages",
    "assets:packages:manage": "Full control over packages",
    "assets:asset_types:read": "View asset types",
    "assets:asset_types:create": "Create asset types",
    "assets:asset_types:update": "Update asset types",
    "assets:asset_types:delete": "Delete asset types",
    "assets:asset_types:manage": "Full control over asset types",

    # Sales Module
    "sales:proposals:read": "View proposals",
    "sales:proposals:create": "Create proposals",
    "sales:proposals:update": "Update proposals",
    "sales:proposals:delete": "Delete proposals",
    "sales:proposals:manage": "Full control over proposals",
    "sales:booking_orders:read": "View booking orders",
    "sales:booking_orders:create": "Create booking orders",
    "sales:booking_orders:update": "Update booking orders",
    "sales:booking_orders:delete": "Delete booking orders",
    "sales:booking_orders:manage": "Full control over booking orders",
    "sales:mockups:read": "View mockups and templates",
    "sales:mockups:create": "Create mockups",
    "sales:mockups:update": "Edit mockups",
    "sales:mockups:delete": "Delete mockups",
    "sales:mockups:manage": "Full control over mockups",
    "sales:mockups:setup": "Configure mockup templates and frames",
    "sales:mockups:generate": "Generate mockup images",
    "sales:templates:read": "View templates",
    "sales:templates:create": "Create templates",
    "sales:templates:update": "Edit templates",
    "sales:templates:delete": "Delete templates",
    "sales:templates:manage": "Full control over templates",
    "sales:clients:read": "View clients",
    "sales:clients:create": "Create clients",
    "sales:clients:update": "Edit clients",
    "sales:clients:delete": "Delete clients",
    "sales:clients:manage": "Full control over clients",
    "sales:products:read": "View products",
    "sales:products:create": "Create products",
    "sales:products:update": "Edit products",
    "sales:products:delete": "Delete products",
    "sales:products:manage": "Full control over products",
    "sales:reports:read": "View reports",
    "sales:reports:export": "Export reports",
    "sales:rate_cards:read": "View rate cards",
    "sales:rate_cards:manage": "Manage rate cards",
    "sales:chat:use": "Use AI chat assistant",

    # Admin
    "admin:users:read": "View users",
    "admin:users:manage": "Manage users",
    "admin:audit:read": "View audit logs",
}


# =============================================================================
# DATA ACCESS HELPERS (5-Level RBAC)
# =============================================================================

def can_access_user_data(target_user_id: str) -> bool:
    """
    Check if current user can access another user's data.

    Returns True if:
    - Current user is system_admin
    - Target is current user (self)
    - Target is a subordinate (direct report or team member)
    - Target is accessible via sharing rules (sharedFromUserIds)
    - Current user has '*:*:*' permission

    Args:
        target_user_id: The user ID whose data is being accessed

    Returns:
        True if access is allowed
    """
    from .context import get_user_context

    ctx = get_user_context()
    if not ctx:
        return False

    current_user_id = ctx.get("user_id")
    profile = ctx.get("profile")
    permissions = ctx.get("permissions", [])
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


def can_access_record(
    object_type: str,
    record_id: str,
    record_owner_id: str | None = None,
) -> bool:
    """
    Check if current user can access a specific record.

    Returns True if:
    - User can access the owner's data (via can_access_user_data)
    - Record is directly shared with user (via sharedRecords)

    Args:
        object_type: Type of record (e.g., "proposal", "booking_order")
        record_id: The record's ID
        record_owner_id: The record owner's user ID

    Returns:
        True if access is allowed
    """
    from .context import get_user_context

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

    Args:
        object_type: Type of record (e.g., "proposal", "booking_order")

    Returns:
        List of record IDs that have been explicitly shared
    """
    from .context import get_user_context

    ctx = get_user_context()
    if not ctx:
        return []

    shared_records = ctx.get("shared_records", {})
    if object_type in shared_records:
        return [str(share.get("recordId")) for share in shared_records[object_type]]

    return []


def get_accessible_user_ids() -> list[str] | None:
    """
    Get list of user IDs the current user can access data for.

    Returns:
        - [current_user_id] for regular users
        - [current_user_id, ...subordinate_ids, ...sharedFromUserIds] for managers/users with sharing
        - None for admins (access to all users)
    """
    from .context import get_user_context

    ctx = get_user_context()
    if not ctx:
        return []

    current_user_id = ctx.get("user_id")
    profile = ctx.get("profile")
    permissions = ctx.get("permissions", [])
    subordinate_ids = ctx.get("subordinate_ids", [])
    shared_from_user_ids = ctx.get("shared_from_user_ids", [])

    # System admin can access all - return None to indicate "all"
    if profile == "system_admin" or "*:*:*" in permissions:
        return None

    # Return self + subordinates + sharing rule users
    accessible = [current_user_id] if current_user_id else []
    accessible.extend(subordinate_ids)
    accessible.extend(shared_from_user_ids)
    return list(set(accessible))
