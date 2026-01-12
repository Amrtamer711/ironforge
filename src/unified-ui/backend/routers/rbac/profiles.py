"""
RBAC Level 1: Profile and Permission endpoints.

[VERIFIED] Mirrors server.js lines 2063-2571:
1. GET /user/:userId - Get user RBAC info (lines 2069-2141)
2. GET /check - Check permission (lines 2144-2198)
3. GET /profiles - List profiles (lines 2201-2240)
4. GET /profiles/:id - Get profile (lines 2243-2276)
5. POST /profiles - Create profile (lines 2279-2346)
6. PUT /profiles/:id - Update profile (lines 2349-2440)
7. DELETE /profiles/:id - Delete profile (lines 2443-2517)
8. GET /permissions - List permissions (lines 2520-2539)
9. GET /permissions/grouped - Grouped permissions (lines 2542-2571)

9 endpoints total.
"""

import contextlib
import logging
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.middleware.auth import AuthUser, require_permission
from backend.routers.rbac.models import CreateProfileRequest, UpdateProfileRequest
from backend.services.rbac_service import invalidate_rbac_cache
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter()


# =============================================================================
# 1. GET /user/:userId - server.js:2069-2141
# =============================================================================

@router.get("/user/{user_id}")
async def get_user_rbac_info(
    user_id: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Get user's profile and permissions.
    Mirrors server.js:2069-2141
    """
    logger.info(f"[UI RBAC API] Getting RBAC info for user: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2075-2079 - Get user's profile
        user_response = (
            supabase.table("users")
            .select("id, email, name, profile_id, profiles(id, name, display_name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        user_data = user_response.data
        if not user_data:
            logger.warning(f"[UI RBAC API] User not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        profile = user_data.get("profiles")
        profile_name = profile.get("name") if profile else None

        # server.js:2090-2100 - Get user's permissions from profile
        permissions: list[str] = []
        if profile and profile.get("id"):
            perms_response = (
                supabase.table("profile_permissions")
                .select("permission")
                .eq("profile_id", profile["id"])
                .execute()
            )
            if perms_response.data:
                permissions = [p["permission"] for p in perms_response.data]

        # server.js:2103-2108 - Get user's permission sets
        user_perm_sets = (
            supabase.table("user_permission_sets")
            .select("permission_sets(id, name, display_name)")
            .eq("user_id", user_id)
            .execute()
        )

        permission_sets = []
        if user_perm_sets.data:
            for ups in user_perm_sets.data:
                ps = ups.get("permission_sets")
                if ps:
                    permission_sets.append(ps)
                    # server.js:2111-2122 - Get permissions from this set
                    ps_perms = (
                        supabase.table("permission_set_permissions")
                        .select("permission")
                        .eq("permission_set_id", ps["id"])
                        .execute()
                    )
                    if ps_perms.data:
                        permissions.extend([p["permission"] for p in ps_perms.data])

        # server.js:2125 - Deduplicate permissions
        permissions = list(set(permissions))

        # server.js:2127-2135
        return {
            "user_id": user_id,
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "profile": profile_name,
            "profile_display_name": profile.get("display_name") if profile else None,
            "permissions": permissions,
            "permission_sets": [ps.get("name") for ps in permission_sets if ps],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user RBAC: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user RBAC info")


# =============================================================================
# 2. GET /check - server.js:2144-2198
# =============================================================================

@router.get("/check")
async def check_permission(
    user_id: str = Query(...),
    permission: str = Query(...),
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Check if user has a specific permission.
    Mirrors server.js:2144-2198
    """
    logger.info(f"[UI RBAC API] Checking permission {permission} for user {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2155-2159 - Get user's profile
        user_response = (
            supabase.table("users")
            .select("profile_id, profiles(id, name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        profile = user_response.data.get("profiles") if user_response.data else None

        # server.js:2164-2174 - Get user's permissions
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

        # server.js:2177-2185 - Check permission (exact match or wildcard)
        has_permission = (
            permission in permissions or
            "*:*:*" in permissions or
            any(
                re.match(f"^{p.replace('*', '.*')}$", permission)
                for p in permissions if "*" in p
            )
        )

        # server.js:2187-2192
        return {
            "user_id": user_id,
            "permission": permission,
            "has_permission": has_permission,
            "profile": profile.get("name") if profile else None,
        }

    except Exception as e:
        logger.error(f"[UI RBAC API] Error checking permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to check permission")


# =============================================================================
# 3. GET /profiles - server.js:2201-2240
# =============================================================================

@router.get("/profiles")
async def list_profiles(
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> list[dict[str, Any]]:
    """
    List all profiles.
    Mirrors server.js:2201-2240
    """
    logger.info("[UI RBAC API] Listing profiles")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2205-2208
        profiles_response = (
            supabase.table("profiles")
            .select("*")
            .order("name")
            .execute()
        )

        # server.js:2215-2231 - Get permissions for each profile
        result = []
        for profile in profiles_response.data or []:
            perms_response = (
                supabase.table("profile_permissions")
                .select("permission")
                .eq("profile_id", profile["id"])
                .execute()
            )

            result.append({
                "id": profile["id"],
                "name": profile["name"],
                "display_name": profile.get("display_name"),
                "description": profile.get("description"),
                "is_system": profile.get("is_system"),
                "permissions": [p["permission"] for p in (perms_response.data or [])],
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at"),
            })

        return result

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing profiles: {e}")
        raise HTTPException(status_code=500, detail="Failed to list profiles")


# =============================================================================
# 4. GET /profiles/:id - server.js:2243-2276
# =============================================================================

@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Get single profile by ID.
    Mirrors server.js:2243-2276
    """
    logger.info(f"[UI RBAC API] Getting profile: {profile_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2248-2252
        profile_response = (
            supabase.table("profiles")
            .select("*")
            .eq("id", profile_id)
            .single()
            .execute()
        )

        profile = profile_response.data
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # server.js:2262-2265 - Get permissions for profile
        perms_response = (
            supabase.table("profile_permissions")
            .select("permission")
            .eq("profile_id", profile["id"])
            .execute()
        )

        # server.js:2267-2270
        return {
            **profile,
            "permissions": [p["permission"] for p in (perms_response.data or [])],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")


# =============================================================================
# 5. POST /profiles - server.js:2279-2346
# =============================================================================

@router.post("/profiles", status_code=201)
async def create_profile(
    request: CreateProfileRequest,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Create profile.
    Mirrors server.js:2279-2346
    """
    # server.js:2282-2288 - Validate
    if not request.name or not request.display_name:
        raise HTTPException(status_code=400, detail="name and display_name are required")

    if not re.match(r"^[a-z][a-z0-9_]*$", request.name):
        raise HTTPException(
            status_code=400,
            detail="name must start with lowercase letter and contain only lowercase letters, numbers, and underscores"
        )

    logger.info(f"[UI RBAC API] Creating profile: {request.name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2295-2303 - Check if profile already exists
        existing = (
            supabase.table("profiles")
            .select("id")
            .eq("name", request.name)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            raise HTTPException(status_code=409, detail="Profile with this name already exists")

        # server.js:2306-2310 - Create profile
        # Insert first, then fetch (supabase-py doesn't support chaining .select() after .insert())
        supabase.table("profiles").insert({
            "name": request.name,
            "display_name": request.display_name,
            "description": request.description,
            "is_system": False
        }).execute()
        profile_response = (
            supabase.table("profiles")
            .select("*")
            .eq("name", request.name)
            .single()
            .execute()
        )

        profile = profile_response.data

        # server.js:2315-2328 - Add permissions if provided
        if request.permissions and len(request.permissions) > 0:
            perm_inserts = [
                {"profile_id": profile["id"], "permission": p}
                for p in request.permissions
            ]
            supabase.table("profile_permissions").insert(perm_inserts).execute()

        # server.js:2331-2338 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "profile.create",
                "action_category": "rbac",
                "resource_type": "profile",
                "resource_id": str(profile["id"]),
                "new_value": {
                    "name": request.name,
                    "display_name": request.display_name,
                    "description": request.description,
                    "permissions": request.permissions or []
                }
            }).execute()

        # server.js:2340
        return {**profile, "permissions": request.permissions or []}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create profile")


# =============================================================================
# 6. PUT /profiles/:id - server.js:2349-2440
# =============================================================================

@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    request: UpdateProfileRequest,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Update profile.
    Mirrors server.js:2349-2440
    """
    logger.info(f"[UI RBAC API] Updating profile: {profile_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2357-2368 - Get current profile
        current_response = (
            supabase.table("profiles")
            .select("*")
            .eq("id", profile_id)
            .single()
            .execute()
        )

        current = current_response.data
        if not current:
            raise HTTPException(status_code=404, detail="Profile not found")

        # server.js:2370-2373 - Warning for system profile modification
        if current.get("is_system") and (request.display_name is not None or request.description is not None):
            logger.info(f"[UI RBAC API] Warning: Modifying system profile {current['name']}")

        # server.js:2376-2378 - Build updates
        updates = {"updated_at": datetime.utcnow().isoformat()}
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.description is not None:
            updates["description"] = request.description

        # server.js:2381-2386 - Update profile
        # Update first, then fetch (supabase-py doesn't support chaining .select() after .update())
        supabase.table("profiles").update(updates).eq("id", profile_id).execute()
        profile_response = (
            supabase.table("profiles")
            .select("*")
            .eq("id", profile_id)
            .single()
            .execute()
        )

        profile = profile_response.data

        # server.js:2391-2396 - Get old permissions for audit
        old_perms_response = (
            supabase.table("profile_permissions")
            .select("permission")
            .eq("profile_id", profile_id)
            .execute()
        )
        old_permissions = [p["permission"] for p in (old_perms_response.data or [])]

        # server.js:2399-2411 - Update permissions if provided
        if request.permissions is not None:
            # Delete existing
            supabase.table("profile_permissions").delete().eq("profile_id", profile_id).execute()

            # Insert new
            if len(request.permissions) > 0:
                perm_inserts = [
                    {"profile_id": profile_id, "permission": p}
                    for p in request.permissions
                ]
                supabase.table("profile_permissions").insert(perm_inserts).execute()

        # server.js:2414-2421 - Clear RBAC cache for users with this profile
        users_response = (
            supabase.table("users")
            .select("id")
            .eq("profile_id", profile_id)
            .execute()
        )
        for u in (users_response.data or []):
            invalidate_rbac_cache(u["id"])

        # server.js:2424-2432 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "profile.update",
                "action_category": "rbac",
                "resource_type": "profile",
                "resource_id": str(profile_id),
                "old_value": {
                    "display_name": current.get("display_name"),
                    "description": current.get("description"),
                    "permissions": old_permissions
                },
                "new_value": {
                    "display_name": profile.get("display_name"),
                    "description": profile.get("description"),
                    "permissions": request.permissions if request.permissions is not None else old_permissions
                }
            }).execute()

        # server.js:2434
        return {
            **profile,
            "permissions": request.permissions if request.permissions is not None else old_permissions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


# =============================================================================
# 7. DELETE /profiles/:id - server.js:2443-2517
# =============================================================================

@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Delete profile.
    Mirrors server.js:2443-2517
    """
    logger.info(f"[UI RBAC API] Deleting profile: {profile_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2450-2461 - Get profile
        profile_response = (
            supabase.table("profiles")
            .select("*")
            .eq("id", profile_id)
            .single()
            .execute()
        )

        profile = profile_response.data
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # server.js:2464-2466 - Cannot delete system profiles
        if profile.get("is_system"):
            raise HTTPException(status_code=403, detail="Cannot delete system profiles")

        # server.js:2469-2482 - Check if any users have this profile
        users_response = (
            supabase.table("users")
            .select("id, email")
            .eq("profile_id", profile_id)
            .execute()
        )

        if users_response.data and len(users_response.data) > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Cannot delete profile with assigned users",
                    "users_count": len(users_response.data),
                    "hint": "Reassign users to another profile first"
                }
            )

        # server.js:2485-2488 - Get permissions for audit log
        perms_response = (
            supabase.table("profile_permissions")
            .select("permission")
            .eq("profile_id", profile_id)
            .execute()
        )

        # server.js:2491 - Delete permissions first
        supabase.table("profile_permissions").delete().eq("profile_id", profile_id).execute()

        # server.js:2494-2497 - Delete profile
        supabase.table("profiles").delete().eq("id", profile_id).execute()

        # server.js:2502-2509 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "profile.delete",
                "action_category": "rbac",
                "resource_type": "profile",
                "resource_id": str(profile_id),
                "old_value": {
                    **profile,
                    "permissions": [p["permission"] for p in (perms_response.data or [])]
                }
            }).execute()

        # server.js:2511
        return {"success": True, "deleted": profile["name"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete profile")


# =============================================================================
# 8. GET /permissions - server.js:2520-2539
# =============================================================================

@router.get("/permissions")
async def list_permissions(
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> list[dict[str, Any]]:
    """
    List all permissions.
    Mirrors server.js:2520-2539
    """
    logger.info("[UI RBAC API] Listing permissions")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2524-2527
        response = (
            supabase.table("permissions")
            .select("*")
            .order("module, resource, action")
            .execute()
        )

        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list permissions")


# =============================================================================
# 9. GET /permissions/grouped - server.js:2542-2571
# =============================================================================

@router.get("/permissions/grouped")
async def list_permissions_grouped(
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, list[dict[str, Any]]]:
    """
    Get permissions grouped by resource.
    Mirrors server.js:2542-2571
    """
    logger.info("[UI RBAC API] Listing permissions grouped")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2546-2549
        response = (
            supabase.table("permissions")
            .select("*")
            .order("module, resource, action")
            .execute()
        )

        # server.js:2556-2563 - Group by resource
        grouped: dict[str, list[dict[str, Any]]] = {}
        for perm in (response.data or []):
            key = f"{perm['module']}:{perm['resource']}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(perm)

        return grouped

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list permissions")


# =============================================================================
# 10. POST /permissions - Create a new permission
# =============================================================================

class CreatePermissionRequest(BaseModel):
    """Request model for creating a permission."""
    name: str  # Full permission name e.g. "sales:proposals:read"
    description: str | None = None


@router.post("/permissions")
async def create_permission(
    request: CreatePermissionRequest,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Create a new permission in the database.

    The permission name should follow the format: module:resource:action
    e.g. "sales:proposals:read" or "admin:users:manage"
    """
    logger.info(f"[UI RBAC API] Creating permission: {request.name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Parse the permission name into module:resource:action
        parts = request.name.split(":")
        if len(parts) != 3:
            raise HTTPException(
                status_code=400,
                detail="Permission name must be in format 'module:resource:action'"
            )

        module, resource, action = parts

        # Check if permission already exists
        existing = (
            supabase.table("permissions")
            .select("id")
            .eq("name", request.name)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            raise HTTPException(status_code=409, detail="Permission already exists")

        # Create the permission
        result = (
            supabase.table("permissions")
            .insert({
                "name": request.name,
                "description": request.description,
                "module": module,
                "resource": resource,
                "action": action,
            })
            .execute()
        )

        logger.info(f"[UI RBAC API] Permission created: {request.name}")

        return {
            "success": True,
            "permission": result.data[0] if result.data else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to create permission")


# =============================================================================
# 11. DELETE /permissions/{permission_name} - Delete a permission
# =============================================================================

@router.delete("/permissions/{permission_name:path}")
async def delete_permission(
    permission_name: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
) -> dict[str, Any]:
    """
    Delete a permission from the database.

    Note: This will also remove the permission from any permission sets
    and profiles that reference it.
    """
    logger.info(f"[UI RBAC API] Deleting permission: {permission_name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Check if permission exists
        existing = (
            supabase.table("permissions")
            .select("id, name")
            .eq("name", permission_name)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Permission not found")

        permission_id = existing.data[0]["id"]

        # Delete from profile_permissions first (FK constraint)
        supabase.table("profile_permissions").delete().eq("permission_id", permission_id).execute()

        # Delete from permission_set_permissions (FK constraint)
        supabase.table("permission_set_permissions").delete().eq("permission_id", permission_id).execute()

        # Delete the permission itself
        supabase.table("permissions").delete().eq("id", permission_id).execute()

        logger.info(f"[UI RBAC API] Permission deleted: {permission_name}")

        return {
            "success": True,
            "deleted": permission_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete permission")
