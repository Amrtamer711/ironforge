"""
Modules API - Provides module configuration and access control.

This router handles:
- Listing accessible modules for a user
- Module configuration
- User-module assignments (admin)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user, require_auth, require_any_role
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client
from integrations.rbac.modules import get_all_modules, get_module
from utils.logging import get_logger
from utils.time import get_uae_time

router = APIRouter(prefix="/api/modules", tags=["modules"])
logger = get_logger("api.modules")


# =============================================================================
# MODELS
# =============================================================================


class ModuleInfo(BaseModel):
    """Public module information."""
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_default: bool = False
    sort_order: int = 0
    tools: List[str] = []  # Tools within this module


class AccessibleModulesResponse(BaseModel):
    """Response for accessible modules endpoint."""
    modules: List[ModuleInfo]
    default_module: Optional[str] = None
    user_default_module: Optional[str] = None


class UserModuleAssignment(BaseModel):
    """User module assignment request."""
    user_id: str
    module_name: str
    is_default: bool = False


class ModuleCreateRequest(BaseModel):
    """Request to create a new module."""
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_default: bool = False
    sort_order: int = 0
    required_permission: Optional[str] = None
    tools: List[str] = []


# =============================================================================
# MODULE DEFINITIONS
# Each module defines its tools and required permissions
# =============================================================================

# Define the module configurations with their tools
MODULE_CONFIGS = {
    "sales": {
        "display_name": "Sales Bot",
        "description": "Sales proposal generation, mockups, and booking orders",
        "icon": "chart-bar",
        "sort_order": 1,
        "is_default": True,
        "required_permission": "sales:*:read",
        "tools": [
            {
                "name": "chat",
                "display_name": "AI Chat",
                "icon": "chat",
                "description": "Chat with AI to generate proposals and mockups",
                "is_default": True,
            },
            {
                "name": "mockup",
                "display_name": "Mockup Generator",
                "icon": "mockup",
                "description": "Generate billboard mockups",
            },
            {
                "name": "proposals",
                "display_name": "Proposals",
                "icon": "document",
                "description": "View and manage proposals",
            },
        ],
    },
    "core": {
        "display_name": "Administration",
        "description": "System administration and user management",
        "icon": "shield",
        "sort_order": 100,  # Show last
        "is_default": False,
        "required_permission": "core:*:read",
        "tools": [
            {
                "name": "admin",
                "display_name": "Admin Panel",
                "icon": "shield",
                "description": "User management, AI costs, and system settings",
                "is_default": True,
            },
        ],
    },
}


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/accessible", response_model=AccessibleModulesResponse)
async def get_accessible_modules(user: AuthUser = Depends(require_auth)):
    """
    Get all modules accessible to the current user.

    Returns modules the user has permission to access, along with
    their default module (if set).
    """
    logger.info(f"[MODULES] Getting accessible modules for user: {user.email}")

    rbac = get_rbac_client()
    accessible_modules = []
    default_module = None
    user_default_module = None

    # Get user's roles to check permissions
    user_roles = await rbac.get_user_roles(user.id)
    role_names = [r.name for r in user_roles]
    logger.debug(f"[MODULES] User {user.email} has roles: {role_names}")

    # Check if user is admin (has access to everything)
    is_admin = "admin" in role_names

    # Check each module
    for module_name, config in MODULE_CONFIGS.items():
        has_access = False

        if is_admin:
            # Admins have access to all modules
            has_access = True
        elif config.get("required_permission"):
            # Check if user has the required permission
            # For wildcard permissions like "sales:*:read", check if user has any sales permission
            req_perm = config["required_permission"]
            module_prefix = req_perm.split(":")[0]

            # Check if user has any role that grants access to this module
            for role in user_roles:
                for perm in role.permissions:
                    if perm.name.startswith(f"{module_prefix}:"):
                        has_access = True
                        break
                if has_access:
                    break
        else:
            # No permission required, everyone can access
            has_access = True

        if has_access:
            module_info = ModuleInfo(
                name=module_name,
                display_name=config["display_name"],
                description=config.get("description"),
                icon=config.get("icon"),
                is_default=config.get("is_default", False),
                sort_order=config.get("sort_order", 0),
                tools=[t["name"] for t in config.get("tools", [])],
            )
            accessible_modules.append(module_info)

            if config.get("is_default") and not default_module:
                default_module = module_name

    # Sort modules by sort_order
    accessible_modules.sort(key=lambda m: m.sort_order)

    # Check if user has a custom default module set
    from db import get_db
    db = get_db()

    try:
        user_pref = db.execute_query(
            """
            SELECT m.name FROM user_modules um
            JOIN modules m ON um.module_id = m.id
            WHERE um.user_id = ? AND um.is_default = 1
            """,
            (user.id,)
        )
        if user_pref:
            user_default_module = user_pref[0]["name"]
    except Exception as e:
        logger.debug(f"[MODULES] Could not get user default module: {e}")

    logger.info(f"[MODULES] User {user.email} has access to {len(accessible_modules)} modules")

    return AccessibleModulesResponse(
        modules=accessible_modules,
        default_module=default_module,
        user_default_module=user_default_module,
    )


@router.get("/config/{module_name}")
async def get_module_config(
    module_name: str,
    user: AuthUser = Depends(require_auth),
):
    """
    Get detailed configuration for a specific module.

    Returns tool configurations, settings, and permissions for the module.
    """
    logger.info(f"[MODULES] Getting config for module: {module_name}")

    if module_name not in MODULE_CONFIGS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found",
        )

    config = MODULE_CONFIGS[module_name]

    # Verify user has access to this module
    rbac = get_rbac_client()
    user_roles = await rbac.get_user_roles(user.id)
    role_names = [r.name for r in user_roles]

    has_access = "admin" in role_names
    if not has_access and config.get("required_permission"):
        module_prefix = config["required_permission"].split(":")[0]
        for role in user_roles:
            for perm in role.permissions:
                if perm.name.startswith(f"{module_prefix}:"):
                    has_access = True
                    break
            if has_access:
                break

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to module '{module_name}'",
        )

    return {
        "name": module_name,
        "display_name": config["display_name"],
        "description": config.get("description"),
        "icon": config.get("icon"),
        "tools": config.get("tools", []),
        "is_default": config.get("is_default", False),
    }


@router.get("/all")
async def list_all_modules(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List all modules (admin only).

    Returns all configured modules regardless of user access.
    """
    logger.info(f"[MODULES] Admin {user.email} listing all modules")

    modules = []
    for name, config in MODULE_CONFIGS.items():
        modules.append({
            "name": name,
            "display_name": config["display_name"],
            "description": config.get("description"),
            "icon": config.get("icon"),
            "is_default": config.get("is_default", False),
            "sort_order": config.get("sort_order", 0),
            "required_permission": config.get("required_permission"),
            "tools": config.get("tools", []),
        })

    modules.sort(key=lambda m: m["sort_order"])
    return {"modules": modules}


@router.post("/user-access")
async def grant_module_access(
    assignment: UserModuleAssignment,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Grant a user access to a module (admin only).
    """
    from db import get_db

    logger.info(f"[MODULES] Admin {user.email} granting {assignment.user_id} access to {assignment.module_name}")

    if assignment.module_name not in MODULE_CONFIGS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{assignment.module_name}' not found",
        )

    db = get_db()
    now = get_uae_time().isoformat()

    # Get or create module in database
    module_record = db.execute_query(
        "SELECT id FROM modules WHERE name = ?",
        (assignment.module_name,)
    )

    if not module_record:
        # Create module record
        config = MODULE_CONFIGS[assignment.module_name]
        db.execute_query(
            """
            INSERT INTO modules (name, display_name, description, icon, is_active, is_default, sort_order, required_permission, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                assignment.module_name,
                config["display_name"],
                config.get("description"),
                config.get("icon"),
                1 if config.get("is_default") else 0,
                config.get("sort_order", 0),
                config.get("required_permission"),
                now,
            )
        )
        module_record = db.execute_query(
            "SELECT id FROM modules WHERE name = ?",
            (assignment.module_name,)
        )

    module_id = module_record[0]["id"]

    # If setting as default, clear other defaults for this user
    if assignment.is_default:
        db.execute_query(
            "UPDATE user_modules SET is_default = 0 WHERE user_id = ?",
            (assignment.user_id,)
        )

    # Insert or update user-module assignment
    db.execute_query(
        """
        INSERT INTO user_modules (user_id, module_id, is_default, granted_by, granted_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, module_id) DO UPDATE SET
            is_default = excluded.is_default,
            granted_by = excluded.granted_by,
            granted_at = excluded.granted_at
        """,
        (
            assignment.user_id,
            module_id,
            1 if assignment.is_default else 0,
            user.id,
            now,
        )
    )

    logger.info(f"[MODULES] Granted {assignment.user_id} access to {assignment.module_name}")

    return {"success": True, "message": f"Access granted to {assignment.module_name}"}


@router.delete("/user-access/{user_id}/{module_name}")
async def revoke_module_access(
    user_id: str,
    module_name: str,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Revoke a user's access to a module (admin only).
    """
    from db import get_db

    logger.info(f"[MODULES] Admin {user.email} revoking {user_id} access to {module_name}")

    db = get_db()

    # Get module ID
    module_record = db.execute_query(
        "SELECT id FROM modules WHERE name = ?",
        (module_name,)
    )

    if not module_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found",
        )

    module_id = module_record[0]["id"]

    # Delete assignment
    db.execute_query(
        "DELETE FROM user_modules WHERE user_id = ? AND module_id = ?",
        (user_id, module_id)
    )

    logger.info(f"[MODULES] Revoked {user_id} access to {module_name}")

    return {"success": True, "message": f"Access revoked from {module_name}"}


@router.get("/user/{user_id}/modules")
async def get_user_modules(
    user_id: str,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Get all modules a specific user has explicit access to (admin only).
    """
    from db import get_db

    logger.info(f"[MODULES] Admin {user.email} getting modules for user {user_id}")

    db = get_db()

    assignments = db.execute_query(
        """
        SELECT m.name, m.display_name, um.is_default, um.granted_at, um.granted_by
        FROM user_modules um
        JOIN modules m ON um.module_id = m.id
        WHERE um.user_id = ?
        """,
        (user_id,)
    )

    return {
        "user_id": user_id,
        "modules": [
            {
                "name": a["name"],
                "display_name": a["display_name"],
                "is_default": bool(a["is_default"]),
                "granted_at": a["granted_at"],
                "granted_by": a["granted_by"],
            }
            for a in (assignments or [])
        ],
    }
