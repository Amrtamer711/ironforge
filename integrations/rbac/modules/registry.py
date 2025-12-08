"""
Module registration system for RBAC.

Provides a central registry for modules to register their permissions and roles.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from integrations.rbac.base import Permission, Role

logger = logging.getLogger("proposal-bot")

# Global module registry
_registered_modules: Dict[str, "ModuleDefinition"] = {}


@dataclass
class ModuleDefinition(ABC):
    """
    Abstract base class for module definitions.

    Each module (sales, crm, etc.) should subclass this and define
    their permissions and roles.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Module identifier (e.g., 'sales', 'crm', 'core')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable module name."""
        pass

    @property
    def description(self) -> str:
        """Module description."""
        return ""

    @abstractmethod
    def get_permissions(self) -> List[Permission]:
        """
        Return all permissions for this module.

        Permission names should follow format: {module}:{resource}:{action}
        e.g., "sales:proposals:create"
        """
        pass

    @abstractmethod
    def get_roles(self) -> List[Role]:
        """
        Return all roles for this module.

        Role names should be prefixed with module name for module-specific roles.
        e.g., "sales:admin", "sales:sales_person"

        Or be generic company roles like "admin", "user".
        """
        pass

    def get_default_role(self) -> Optional[str]:
        """
        Return the default role name for new users in this module.
        Returns None if no default.
        """
        return None


def register_module(module: ModuleDefinition) -> None:
    """
    Register a module with the RBAC system.

    Args:
        module: ModuleDefinition instance to register
    """
    if module.name in _registered_modules:
        logger.warning(f"[RBAC:MODULES] Module '{module.name}' already registered, updating")

    _registered_modules[module.name] = module
    logger.info(
        f"[RBAC:MODULES] Registered module '{module.name}' with "
        f"{len(module.get_permissions())} permissions, {len(module.get_roles())} roles"
    )


def unregister_module(module_name: str) -> bool:
    """
    Unregister a module.

    Args:
        module_name: Name of module to unregister

    Returns:
        True if module was unregistered
    """
    if module_name in _registered_modules:
        del _registered_modules[module_name]
        logger.info(f"[RBAC:MODULES] Unregistered module '{module_name}'")
        return True
    return False


def get_module(module_name: str) -> Optional[ModuleDefinition]:
    """Get a registered module by name."""
    return _registered_modules.get(module_name)


def get_all_modules() -> Dict[str, ModuleDefinition]:
    """Get all registered modules."""
    return dict(_registered_modules)


def is_module_registered(module_name: str) -> bool:
    """Check if a module is registered."""
    return module_name in _registered_modules


def get_all_permissions() -> List[Permission]:
    """
    Get all permissions from all registered modules.

    Returns:
        Combined list of all permissions
    """
    permissions = []
    for module in _registered_modules.values():
        permissions.extend(module.get_permissions())
    return permissions


def get_all_roles() -> List[Role]:
    """
    Get all roles from all registered modules.

    Returns:
        Combined list of all roles
    """
    roles = []
    for module in _registered_modules.values():
        roles.extend(module.get_roles())
    return roles


def get_permissions_for_module(module_name: str) -> List[Permission]:
    """
    Get permissions for a specific module.

    Args:
        module_name: Module name

    Returns:
        List of permissions for the module, empty if not found
    """
    module = _registered_modules.get(module_name)
    if module:
        return module.get_permissions()
    return []


def get_roles_for_module(module_name: str) -> List[Role]:
    """
    Get roles for a specific module.

    Args:
        module_name: Module name

    Returns:
        List of roles for the module, empty if not found
    """
    module = _registered_modules.get(module_name)
    if module:
        return module.get_roles()
    return []


def get_permissions_grouped_by_module() -> Dict[str, List[Permission]]:
    """
    Get all permissions grouped by module.

    Returns:
        Dict mapping module name to list of permissions
    """
    return {
        module_name: module.get_permissions()
        for module_name, module in _registered_modules.items()
    }


def get_roles_grouped_by_module() -> Dict[str, List[Role]]:
    """
    Get all roles grouped by module.

    Returns:
        Dict mapping module name to list of roles
    """
    return {
        module_name: module.get_roles()
        for module_name, module in _registered_modules.items()
    }


def clear_registry() -> None:
    """Clear all registered modules (mainly for testing)."""
    global _registered_modules
    _registered_modules = {}
    logger.info("[RBAC:MODULES] Registry cleared")
