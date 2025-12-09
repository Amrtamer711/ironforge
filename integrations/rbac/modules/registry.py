"""
Module registration system for RBAC.

Provides a central registry for modules to register their permissions.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from integrations.rbac.base import Permission

logger = logging.getLogger("proposal-bot")

# Global module registry
_registered_modules: Dict[str, "ModuleDefinition"] = {}


@dataclass
class ModuleDefinition(ABC):
    """
    Abstract base class for module definitions.

    Each module (sales, crm, etc.) should subclass this and define
    their permissions.
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
        f"{len(module.get_permissions())} permissions"
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


def clear_registry() -> None:
    """Clear all registered modules (mainly for testing)."""
    global _registered_modules
    _registered_modules = {}
    logger.info("[RBAC:MODULES] Registry cleared")
