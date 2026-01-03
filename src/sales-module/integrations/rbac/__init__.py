"""
RBAC (Role-Based Access Control) Integration Layer.

Provides permission checking using trusted headers from unified-ui.
All RBAC management (profiles, teams, permissions) is handled by unified-ui.

Enterprise RBAC Architecture (4 Levels):
- Level 1: Profiles (base permission templates - one per user)
- Level 2: Permission Sets (additive permissions - multiple per user, can expire)
- Level 3: Teams & Hierarchy (organizational structure)
- Level 4: Record-Level Sharing (manual and rule-based sharing)

IMPORTANT: Two has_permission Functions
=========================================

1. integrations.rbac.has_permission(user_id, permission) [ASYNC]
   - Fetches user permissions from context, then checks
   - Use for admin operations when you only have user_id

2. crm_security.has_permission(permissions, permission) [SYNC]
   - Takes already-fetched permissions list, checks locally
   - Use in request handlers where AuthUser.permissions is available
   - PREFERRED for performance (no DB round-trip)

Usage:
    # For request handlers (use pre-fetched permissions from AuthUser):
    from crm_security import has_permission

    if has_permission(user.permissions, "sales:proposals:create"):
        pass

Permission Format:
    "{module}:{resource}:{action}" e.g., "sales:proposals:create", "core:users:manage"

    Modules: core, sales
    Actions: create, read, update, delete, manage (implies all)
"""

# Import base types
from integrations.rbac.base import (
    AccessLevel,
    Permission,
    PermissionAction,
    PermissionSet,
    # Enterprise RBAC models
    Profile,
    RBACContext,
    RBACProvider,
    RecordShare,
    SharingRule,
    Team,
    TeamMember,
    TeamRole,
    UserPermissionSet,
)
from integrations.rbac.client import (
    RBACClient,
    get_rbac_client,
    has_permission,
    require_permission,
    reset_rbac_client,
    set_rbac_client,
)
from integrations.rbac.providers import DatabaseRBACProvider

__all__ = [
    # Base types
    "RBACProvider",
    "Permission",
    "PermissionAction",
    "RBACContext",
    # Enterprise RBAC models
    "Profile",
    "PermissionSet",
    "UserPermissionSet",
    "Team",
    "TeamMember",
    "TeamRole",
    "SharingRule",
    "RecordShare",
    "AccessLevel",
    # Client
    "RBACClient",
    "get_rbac_client",
    "set_rbac_client",
    "reset_rbac_client",
    # Convenience functions
    "has_permission",
    "require_permission",
    # Providers
    "DatabaseRBACProvider",
]
