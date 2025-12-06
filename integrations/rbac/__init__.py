"""
RBAC (Role-Based Access Control) Integration Layer.

Provides abstracted access to RBAC providers with a unified interface.
Follows the same pattern as integrations/llm/, integrations/auth/,
and integrations/channels/.

Supported Providers:
- Database (DatabaseRBACProvider): Database-backed RBAC using unified schema
- Static (StaticRBACProvider): Static configuration (for development)

Usage:
    from integrations.rbac import get_rbac_client, has_permission, require_role

    # Get the configured RBAC client
    rbac = get_rbac_client()

    # Check permissions
    if await rbac.has_permission(user_id, "proposals:create"):
        # User can create proposals
        pass

    # Or use convenience functions
    if await has_permission(user_id, "proposals:create"):
        pass

    # Require permission (raises PermissionError if lacking)
    await require_permission(user_id, "proposals:delete")

    # Get user roles
    roles = await rbac.get_user_roles(user_id)
    print(f"User has roles: {[r.name for r in roles]}")

Configuration:
    Set RBAC_PROVIDER environment variable:
    - "static" (default): Use static in-memory configuration
    - "database": Use database-backed RBAC

Default Roles:
    - admin: Full system access
    - hos: Head of Sales - team oversight
    - sales_person: Sales team member
    - coordinator: Operations coordinator
    - finance: Finance team member

Permission Format:
    "{resource}:{action}" e.g., "proposals:create", "users:manage"

    Actions: create, read, update, delete, manage (implies all)
"""

from integrations.rbac.base import (
    RBACProvider,
    Role,
    Permission,
    PermissionAction,
    UserRole,
    RBACContext,
    DEFAULT_ROLES,
    DEFAULT_PERMISSIONS,
)

from integrations.rbac.client import (
    RBACClient,
    get_rbac_client,
    set_rbac_client,
    reset_rbac_client,
    has_permission,
    has_role,
    require_permission,
    require_role,
)

from integrations.rbac.providers import (
    DatabaseRBACProvider,
    StaticRBACProvider,
)

__all__ = [
    # Base types
    "RBACProvider",
    "Role",
    "Permission",
    "PermissionAction",
    "UserRole",
    "RBACContext",
    "DEFAULT_ROLES",
    "DEFAULT_PERMISSIONS",
    # Client
    "RBACClient",
    "get_rbac_client",
    "set_rbac_client",
    "reset_rbac_client",
    # Convenience functions
    "has_permission",
    "has_role",
    "require_permission",
    "require_role",
    # Providers
    "DatabaseRBACProvider",
    "StaticRBACProvider",
]
