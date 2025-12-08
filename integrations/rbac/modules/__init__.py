"""
Module-aware RBAC system.

This module provides a registration system for RBAC permissions and roles
that can be extended by different application modules (sales, crm, etc.).

Architecture:
- Core/Platform permissions (users, system) are always available
- Module-specific permissions are registered when modules load
- Permission format: {module}:{resource}:{action}
  e.g., "sales:proposals:create", "crm:contacts:read"

Usage:
    from integrations.rbac.modules import register_module, get_all_permissions

    # Register a module's permissions
    register_module(SalesModule())

    # Get all registered permissions
    permissions = get_all_permissions()
"""

from integrations.rbac.modules.registry import (
    ModuleDefinition,
    register_module,
    unregister_module,
    get_module,
    get_all_modules,
    get_all_permissions,
    get_all_roles,
    get_permissions_for_module,
    get_roles_for_module,
    is_module_registered,
)

from integrations.rbac.modules.core import CoreModule
from integrations.rbac.modules.sales import SalesModule

__all__ = [
    # Registry functions
    "ModuleDefinition",
    "register_module",
    "unregister_module",
    "get_module",
    "get_all_modules",
    "get_all_permissions",
    "get_all_roles",
    "get_permissions_for_module",
    "get_roles_for_module",
    "is_module_registered",
    # Module definitions
    "CoreModule",
    "SalesModule",
]
