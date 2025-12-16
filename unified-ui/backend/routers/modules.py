"""
Modules router for unified-ui.

[VERIFIED] Mirrors server.js lines 1927-2061:
- GET /api/modules/accessible - Get accessible modules for user (1 endpoint)

This endpoint returns the modules a user can access based on their
profile permissions. Used by frontend to show available navigation items.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.middleware.auth import AuthUser, require_auth
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter(prefix="/api/modules", tags=["modules"])


def _check_permission_match(user_permissions: set, required_perm: str) -> bool:
    """
    Check if user has the required permission.

    Mirrors server.js:1997-2007 permission matching logic:
    - Exact match
    - Wildcard match (e.g., 'sales:*:*' matches 'sales:proposals:read')
    """
    # Exact match
    if required_perm in user_permissions:
        return True

    # Admin wildcard
    if "*:*:*" in user_permissions:
        return True

    # Check wildcard patterns
    for perm in user_permissions:
        if "*" in perm:
            # Convert wildcard to regex pattern
            pattern = perm.replace("*", ".*")
            if re.match(f"^{pattern}$", required_perm):
                return True

    return False


@router.get("/accessible")
async def get_accessible_modules(
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Get accessible modules for the authenticated user.

    Mirrors server.js:1927-2061 (GET /api/modules/accessible)

    Returns modules filtered by user's permissions, plus default module info.
    """
    logger.info(f"[UI RBAC] Getting accessible modules for user: {user.email}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1931-1943 - Get user's profile from users table
        user_response = (
            supabase.table("users")
            .select("id, email, profile_id, profiles(id, name, display_name)")
            .eq("id", user.id)
            .single()
            .execute()
        )

        user_data = user_response.data
        profile = user_data.get("profiles") if user_data else None
        profile_name = profile.get("name") if profile else None

        logger.info(f"[UI RBAC] User profile: {profile_name or 'none'}")

        # server.js:1947-1960 - Get user's permissions from profile_permissions
        permissions: set = set()
        if profile and profile.get("id"):
            perms_response = (
                supabase.table("profile_permissions")
                .select("permission")
                .eq("profile_id", profile["id"])
                .execute()
            )

            if perms_response.data:
                for p in perms_response.data:
                    permissions.add(p["permission"])

        logger.info(f"[UI RBAC] User permissions: {', '.join(permissions) or 'none'}")

        # server.js:1964-1965 - Check if user is admin
        is_admin = "*:*:*" in permissions or profile_name == "system_admin"

        # server.js:1967-1977 - Get all active modules
        modules_response = (
            supabase.table("modules")
            .select("*")
            .eq("is_active", True)
            .order("sort_order")
            .execute()
        )

        if not modules_response.data:
            logger.warning("[UI RBAC] No active modules found in database")

        all_modules = modules_response.data or []

        # server.js:1979-2012 - Filter modules based on permissions
        accessible_modules: list[dict[str, Any]] = []

        for module in all_modules:
            # server.js:1983-1987 - Admins can access everything
            if is_admin:
                accessible_modules.append(module)
                continue

            # server.js:1989-1995 - Check required permission
            required_perm = module.get("required_permission")
            if not required_perm:
                # No permission required, module is accessible
                accessible_modules.append(module)
                continue

            # server.js:1997-2011 - Check if user has the required permission
            if _check_permission_match(permissions, required_perm):
                accessible_modules.append(module)

        logger.info(
            f"[UI RBAC] Accessible modules: "
            f"{', '.join(m.get('name', '') for m in accessible_modules) or 'none'}"
        )

        # server.js:2016-2028 - Fallback if no modules found
        if not accessible_modules:
            logger.warning(f"[UI RBAC] No modules found for user {user.email}, providing fallback")
            accessible_modules.append({
                "name": "sales",
                "display_name": "Sales Bot",
                "description": "Sales proposal generation, mockups, and booking orders",
                "icon": "chart-bar",
                "is_default": True,
                "sort_order": 1,
                "config_json": {"tools": ["chat", "mockup", "proposals"]},
            })

        # server.js:2030-2031 - Determine default module
        default_module = None
        for m in accessible_modules:
            if m.get("is_default"):
                default_module = m.get("name")
                break
        if not default_module and accessible_modules:
            default_module = accessible_modules[0].get("name")

        # server.js:2033-2041 - Check for user-specific default module
        user_default_module = None
        try:
            user_module_response = (
                supabase.table("user_modules")
                .select("modules(name)")
                .eq("user_id", user.id)
                .eq("is_default", True)
                .single()
                .execute()
            )

            if user_module_response.data:
                modules_data = user_module_response.data.get("modules")
                if modules_data:
                    user_default_module = modules_data.get("name")
        except Exception:
            # User might not have a specific default module set
            pass

        # server.js:2043-2055 - Format response
        return {
            "modules": [
                {
                    "name": m.get("name"),
                    "display_name": m.get("display_name"),
                    "description": m.get("description"),
                    "icon": m.get("icon"),
                    "is_default": m.get("is_default"),
                    "sort_order": m.get("sort_order"),
                    # server.js:2051 - tools from config_json or fallback
                    "tools": (
                        m.get("config_json", {}).get("tools")
                        if m.get("config_json")
                        else (
                            ["chat", "mockup", "proposals"]
                            if m.get("name") == "sales"
                            else ["admin"]
                        )
                    ),
                }
                for m in accessible_modules
            ],
            "default_module": default_module,
            "user_default_module": user_default_module,
        }

    except HTTPException:
        raise
    except Exception as e:
        # server.js:2057-2059
        logger.error(f"[UI RBAC] Error getting modules: {e}")
        raise HTTPException(status_code=500, detail="Failed to get accessible modules")
