"""
RBAC (Role-Based Access Control) Integration Layer.

Provides abstracted access to RBAC providers with a unified interface.
Follows the same pattern as integrations/llm/, integrations/auth/,
and integrations/channels/.

Enterprise RBAC Architecture (4 Levels):
- Level 1: Profiles (base permission templates - one per user)
- Level 2: Permission Sets (additive permissions - multiple per user, can expire)
- Level 3: Teams & Hierarchy (organizational structure)
- Level 4: Record-Level Sharing (manual and rule-based sharing)

Supported Providers:
- Database (DatabaseRBACProvider): Database-backed RBAC using unified schema
- Static (StaticRBACProvider): In-memory configuration (for development/testing)

IMPORTANT: Two has_permission Functions
=========================================

1. integrations.rbac.has_permission(user_id, permission) [ASYNC]
   - Fetches user permissions from database, then checks
   - Use for admin operations when you only have user_id
   - Use when permissions aren't pre-populated in context

2. security.has_permission(permissions, permission) [SYNC]
   - Takes already-fetched permissions list, checks locally
   - Use in request handlers where AuthUser.permissions is available
   - PREFERRED for performance (no DB round-trip)

Usage:
    # For management/admin operations (fetches from DB):
    from integrations.rbac import get_rbac_client

    rbac = get_rbac_client()
    permissions = await rbac.get_user_permissions(user_id)
    profile = await rbac.get_user_profile(user_id)

    # For request handlers (use pre-fetched permissions from AuthUser):
    from crm_security import has_permission

    if has_permission(user.permissions, "sales:proposals:create"):
        pass

Configuration:
    Set RBAC_PROVIDER environment variable:
    - "static" (default): Use static in-memory configuration
    - "database": Use database-backed RBAC

Permission Format:
    "{module}:{resource}:{action}" e.g., "sales:proposals:create", "core:users:manage"

    Modules: core, sales, (future: crm, etc.)
    Actions: create, read, update, delete, manage (implies all)
"""

# Import and register modules FIRST (before importing base types)
from integrations.rbac.modules import (
    CoreModule,
    SalesModule,
    get_all_permissions,
    get_permissions_for_module,
    register_module,
)

# Register default modules
register_module(CoreModule())
register_module(SalesModule())

# Now import base types (they will use the registered modules)
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
    get_default_permissions,
)
from integrations.rbac.client import (
    RBACClient,
    get_rbac_client,
    has_permission,
    require_permission,
    reset_rbac_client,
    set_rbac_client,
)
from integrations.rbac.providers import (
    DatabaseRBACProvider,
    StaticRBACProvider,
)

__all__ = [
    # Base types
    "RBACProvider",
    "Permission",
    "PermissionAction",
    "RBACContext",
    "get_default_permissions",
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
    # Module registry
    "register_module",
    "get_all_permissions",
    "get_permissions_for_module",
    "CoreModule",
    "SalesModule",
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
    "StaticRBACProvider",
]
