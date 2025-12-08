"""
Core/Platform module - base permissions available across all modules.

These are platform-level permissions for user management, system administration,
and other cross-cutting concerns.
"""

from typing import List, Optional

from integrations.rbac.base import Permission, Role
from integrations.rbac.modules.registry import ModuleDefinition


class CoreModule(ModuleDefinition):
    """
    Core platform module.

    Provides base permissions for:
    - User management (users:read, users:create, etc.)
    - System administration (system:admin)
    - AI cost tracking (ai_costs:read, ai_costs:manage)

    Also provides generic company-level roles:
    - admin: Full system access
    - user: Basic authenticated user (default)
    """

    @property
    def name(self) -> str:
        return "core"

    @property
    def display_name(self) -> str:
        return "Core Platform"

    @property
    def description(self) -> str:
        return "Base platform permissions for user management and system administration"

    def get_permissions(self) -> List[Permission]:
        return [
            # User Management
            Permission.from_name("core:users:read", "View users"),
            Permission.from_name("core:users:create", "Create users"),
            Permission.from_name("core:users:update", "Edit users"),
            Permission.from_name("core:users:delete", "Delete users"),
            Permission.from_name("core:users:manage", "Full control over users"),

            # System Administration
            Permission.from_name("core:system:admin", "System administration"),
            Permission.from_name("core:system:config", "Manage system configuration"),

            # AI Cost Tracking (platform-wide)
            Permission.from_name("core:ai_costs:read", "View AI cost reports"),
            Permission.from_name("core:ai_costs:manage", "Manage AI cost tracking"),

            # API Keys
            Permission.from_name("core:api_keys:read", "View API keys"),
            Permission.from_name("core:api_keys:create", "Create API keys"),
            Permission.from_name("core:api_keys:delete", "Delete API keys"),
            Permission.from_name("core:api_keys:manage", "Full control over API keys"),

            # Roles & Permissions
            Permission.from_name("core:roles:read", "View roles"),
            Permission.from_name("core:roles:create", "Create roles"),
            Permission.from_name("core:roles:update", "Update roles"),
            Permission.from_name("core:roles:delete", "Delete roles"),
            Permission.from_name("core:roles:manage", "Full control over roles"),
        ]

    def get_roles(self) -> List[Role]:
        return [
            Role(
                name="admin",
                description="Full system access - all modules",
                permissions=[
                    Permission.from_name("*:*:manage", "All permissions"),
                ],
                is_system=True,
            ),
            Role(
                name="user",
                description="Basic authenticated user",
                permissions=[
                    # Users can read their own profile (enforced via ownership checks)
                    Permission.from_name("core:users:read", "View users"),
                ],
                is_system=True,
            ),
        ]

    def get_default_role(self) -> Optional[str]:
        return "user"


