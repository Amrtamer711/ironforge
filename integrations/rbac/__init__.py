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

    # Check permissions (new format: module:resource:action)
    if await rbac.has_permission(user_id, "sales:proposals:create"):
        # User can create proposals
        pass

    # Or use convenience functions
    if await has_permission(user_id, "core:users:read"):
        pass

    # Require permission (raises PermissionError if lacking)
    await require_permission(user_id, "sales:proposals:delete")

    # Get user roles
    roles = await rbac.get_user_roles(user_id)
    print(f"User has roles: {[r.name for r in roles]}")

Configuration:
    Set RBAC_PROVIDER environment variable:
    - "static" (default): Use static in-memory configuration
    - "database": Use database-backed RBAC

Permission Format:
    "{module}:{resource}:{action}" e.g., "sales:proposals:create", "core:users:manage"

    Modules: core, sales, (future: crm, etc.)
    Actions: create, read, update, delete, manage (implies all)

Roles:
    Company-wide:
    - admin: Full system access (all modules)
    - user: Basic authenticated user

    Sales module:
    - sales:admin: Full sales module access
    - sales:hos: Head of Sales - team oversight
    - sales:sales_person: Sales team member
    - sales:coordinator: Operations coordinator
    - sales:finance: Finance team member
"""

# Import and register modules FIRST (before importing base types)
from integrations.rbac.modules import (
    register_module,
    get_all_permissions,
    get_all_roles,
    get_permissions_for_module,
    get_roles_for_module,
    CoreModule,
    SalesModule,
)

# Register default modules
register_module(CoreModule())
register_module(SalesModule())

# Now import base types (they will use the registered modules)
from integrations.rbac.base import (
    RBACProvider,
    Role,
    Permission,
    PermissionAction,
    UserRole,
    RBACContext,
    DEFAULT_ROLES,
    DEFAULT_PERMISSIONS,
    get_default_permissions,
    get_default_roles,
    initialize_default_rbac,
)

# Initialize the defaults from registered modules
initialize_default_rbac()

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
    "get_default_permissions",
    "get_default_roles",
    "initialize_default_rbac",
    # Module registry
    "register_module",
    "get_all_permissions",
    "get_all_roles",
    "get_permissions_for_module",
    "get_roles_for_module",
    "CoreModule",
    "SalesModule",
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
