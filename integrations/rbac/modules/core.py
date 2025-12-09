"""
Core/Platform module - base permissions available across all modules.

These are platform-level permissions for user management, system administration,
and other cross-cutting concerns.
"""

from typing import List

from integrations.rbac.base import Permission
from integrations.rbac.modules.registry import ModuleDefinition


class CoreModule(ModuleDefinition):
    """
    Core platform module.

    Provides base permissions for:
    - User management (users:read, users:create, etc.)
    - System administration (system:admin)
    - AI cost tracking (ai_costs:read, ai_costs:manage)
    - RBAC management (profiles, permission sets, teams)
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

            # API Keys / API Access
            Permission.from_name("core:api:access", "API access"),
            Permission.from_name("core:api_keys:read", "View API keys"),
            Permission.from_name("core:api_keys:create", "Create API keys"),
            Permission.from_name("core:api_keys:delete", "Delete API keys"),
            Permission.from_name("core:api_keys:manage", "Full control over API keys"),

            # Profile Management
            Permission.from_name("core:profiles:read", "View profiles"),
            Permission.from_name("core:profiles:create", "Create profiles"),
            Permission.from_name("core:profiles:update", "Update profiles"),
            Permission.from_name("core:profiles:delete", "Delete profiles"),
            Permission.from_name("core:profiles:manage", "Full control over profiles"),

            # Permission Set Management
            Permission.from_name("core:permission_sets:read", "View permission sets"),
            Permission.from_name("core:permission_sets:create", "Create permission sets"),
            Permission.from_name("core:permission_sets:update", "Update permission sets"),
            Permission.from_name("core:permission_sets:delete", "Delete permission sets"),
            Permission.from_name("core:permission_sets:manage", "Full control over permission sets"),

            # Team Management
            Permission.from_name("core:teams:read", "View teams"),
            Permission.from_name("core:teams:create", "Create teams"),
            Permission.from_name("core:teams:update", "Update teams"),
            Permission.from_name("core:teams:delete", "Delete teams"),
            Permission.from_name("core:teams:manage", "Full control over teams"),

            # Sharing Rules Management
            Permission.from_name("core:sharing_rules:read", "View sharing rules"),
            Permission.from_name("core:sharing_rules:create", "Create sharing rules"),
            Permission.from_name("core:sharing_rules:delete", "Delete sharing rules"),
            Permission.from_name("core:sharing_rules:manage", "Full control over sharing rules"),
        ]
