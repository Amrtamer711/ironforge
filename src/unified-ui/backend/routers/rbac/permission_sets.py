"""
RBAC Level 2: Permission Set Management endpoints.

[VERIFIED] Mirrors server.js lines 2573-2839:
1. GET /permission-sets - List permission sets (lines 2578-2603)
2. POST /permission-sets - Create permission set (lines 2606-2640)
3. PUT /permission-sets/:id - Update permission set (lines 2643-2685)
4. DELETE /permission-sets/:id - Delete permission set (lines 2688-2757)
5. POST /users/:userId/permission-sets - Assign to user (lines 2760-2792)
6. DELETE /users/:userId/permission-sets/:setId - Revoke from user (lines 2795-2817)
7. GET /users/:userId/permission-sets - Get user's sets (lines 2820-2839)

7 endpoints total.
"""

import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.middleware.auth import AuthUser, require_profile
from backend.routers.rbac.models import (
    AssignPermissionSetRequest,
    CreatePermissionSetRequest,
    UpdatePermissionSetRequest,
)
from backend.services.rbac_service import invalidate_rbac_cache
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter()


# =============================================================================
# 1. GET /permission-sets - server.js:2578-2603
# =============================================================================

@router.get("/permission-sets")
async def list_permission_sets(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> list[dict[str, Any]]:
    """
    List all permission sets.
    Mirrors server.js:2578-2603
    """
    logger.info("[UI RBAC API] Listing permission sets")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2582-2588
        response = (
            supabase.table("permission_sets")
            .select("*, permission_set_permissions(permission)")
            .order("name")
            .execute()
        )

        # server.js:2593-2596 - Transform to include permissions array
        result = []
        for s in (response.data or []):
            perm_set = {k: v for k, v in s.items() if k != "permission_set_permissions"}
            perm_set["permissions"] = [
                p["permission"] for p in (s.get("permission_set_permissions") or [])
            ]
            result.append(perm_set)

        return result

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing permission sets: {e}")
        raise HTTPException(status_code=500, detail="Failed to list permission sets")


# =============================================================================
# 1b. GET /permission-sets/:id - Get single permission set
# =============================================================================

@router.get("/permission-sets/{set_id}")
async def get_permission_set(
    set_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Get a single permission set by ID.
    """
    logger.info(f"[UI RBAC API] Getting permission set: {set_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        response = (
            supabase.table("permission_sets")
            .select("*, permission_set_permissions(permission)")
            .eq("id", set_id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Permission set not found")

        perm_set = {k: v for k, v in response.data.items() if k != "permission_set_permissions"}
        perm_set["permissions"] = [
            p["permission"] for p in (response.data.get("permission_set_permissions") or [])
        ]

        return perm_set

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to get permission set")


# =============================================================================
# 2. POST /permission-sets - server.js:2606-2640
# =============================================================================

@router.post("/permission-sets", status_code=201)
async def create_permission_set(
    request: CreatePermissionSetRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Create permission set.
    Mirrors server.js:2606-2640
    """
    # server.js:2609-2611 - Validate
    if not request.name or not request.display_name:
        raise HTTPException(status_code=400, detail="name and display_name are required")

    logger.info(f"[UI RBAC API] Creating permission set: {request.name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2617-2621 - Create permission set
        set_response = (
            supabase.table("permission_sets")
            .insert({
                "name": request.name,
                "display_name": request.display_name,
                "description": request.description
            })
            .select()
            .single()
            .execute()
        )

        perm_set = set_response.data

        # server.js:2626-2633 - Add permissions if provided
        if request.permissions and len(request.permissions) > 0:
            perm_inserts = [
                {"permission_set_id": perm_set["id"], "permission": p}
                for p in request.permissions
            ]
            supabase.table("permission_set_permissions").insert(perm_inserts).execute()

        # server.js:2635
        return {**perm_set, "permissions": request.permissions or []}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to create permission set")


# =============================================================================
# 3. PUT /permission-sets/:id - server.js:2643-2685
# =============================================================================

@router.put("/permission-sets/{set_id}")
async def update_permission_set(
    set_id: int,
    request: UpdatePermissionSetRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update permission set.
    Mirrors server.js:2643-2685
    """
    logger.info(f"[UI RBAC API] Updating permission set: {set_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2651-2654 - Build updates
        updates = {}
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.description is not None:
            updates["description"] = request.description
        if request.is_active is not None:
            updates["is_active"] = request.is_active

        # server.js:2656-2661
        set_response = (
            supabase.table("permission_sets")
            .update(updates)
            .eq("id", set_id)
            .select()
            .single()
            .execute()
        )

        perm_set = set_response.data

        # server.js:2666-2678 - Update permissions if provided
        if request.permissions is not None:
            # Delete existing
            supabase.table("permission_set_permissions").delete().eq("permission_set_id", set_id).execute()

            # Insert new
            if len(request.permissions) > 0:
                perm_inserts = [
                    {"permission_set_id": set_id, "permission": p}
                    for p in request.permissions
                ]
                supabase.table("permission_set_permissions").insert(perm_inserts).execute()

        # server.js:2680
        return {**perm_set, "permissions": request.permissions or []}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to update permission set")


# =============================================================================
# 4. DELETE /permission-sets/:id - server.js:2688-2757
# =============================================================================

@router.delete("/permission-sets/{set_id}")
async def delete_permission_set(
    set_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Delete permission set.
    Mirrors server.js:2688-2757
    """
    logger.info(f"[UI RBAC API] Deleting permission set: {set_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2695-2706 - Get permission set
        perm_set_response = (
            supabase.table("permission_sets")
            .select("*")
            .eq("id", set_id)
            .single()
            .execute()
        )

        perm_set = perm_set_response.data
        if not perm_set:
            raise HTTPException(status_code=404, detail="Permission set not found")

        # server.js:2709-2722 - Check if any users have this permission set
        users_response = (
            supabase.table("user_permission_sets")
            .select("user_id")
            .eq("permission_set_id", set_id)
            .execute()
        )

        if users_response.data and len(users_response.data) > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Cannot delete permission set with assigned users",
                    "users_count": len(users_response.data),
                    "hint": "Revoke this permission set from all users first"
                }
            )

        # server.js:2725-2728 - Get permissions for audit log
        perms_response = (
            supabase.table("permission_set_permissions")
            .select("permission")
            .eq("permission_set_id", set_id)
            .execute()
        )

        # server.js:2731 - Delete permissions first
        supabase.table("permission_set_permissions").delete().eq("permission_set_id", set_id).execute()

        # server.js:2734-2737 - Delete permission set
        supabase.table("permission_sets").delete().eq("id", set_id).execute()

        # server.js:2742-2749 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "permission_set.delete",
                "action_category": "rbac",
                "resource_type": "permission_set",
                "resource_id": str(set_id),
                "old_value": {
                    **perm_set,
                    "permissions": [p["permission"] for p in (perms_response.data or [])]
                }
            }).execute()

        # server.js:2751
        return {"success": True, "deleted": perm_set["name"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete permission set")


# =============================================================================
# 5. POST /users/:userId/permission-sets - server.js:2760-2792
# =============================================================================

@router.post("/users/{user_id}/permission-sets", status_code=201)
async def assign_permission_set(
    user_id: str,
    request: AssignPermissionSetRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Assign permission set to user.
    Mirrors server.js:2760-2792
    """
    logger.info(f"[UI RBAC API] Assigning permission set {request.permission_set_id} to user {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2771-2780
        response = (
            supabase.table("user_permission_sets")
            .insert({
                "user_id": user_id,
                "permission_set_id": request.permission_set_id,
                "granted_by": user.id,
                "expires_at": request.expires_at
            })
            .select()
            .single()
            .execute()
        )

        # server.js:2785 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error assigning permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign permission set")


# =============================================================================
# 6. DELETE /users/:userId/permission-sets/:setId - server.js:2795-2817
# =============================================================================

@router.delete("/users/{user_id}/permission-sets/{set_id}")
async def revoke_permission_set(
    user_id: str,
    set_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Revoke permission set from user.
    Mirrors server.js:2795-2817
    """
    logger.info(f"[UI RBAC API] Revoking permission set {set_id} from user {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2801-2805
        supabase.table("user_permission_sets").delete().eq("user_id", user_id).eq("permission_set_id", set_id).execute()

        # server.js:2810 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return {"success": True}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error revoking permission set: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke permission set")


# =============================================================================
# 7. GET /users/:userId/permission-sets - server.js:2820-2839
# =============================================================================

@router.get("/users/{user_id}/permission-sets")
async def get_user_permission_sets(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> list[dict[str, Any]]:
    """
    Get user's permission sets.
    Mirrors server.js:2820-2839
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2824-2830
        response = (
            supabase.table("user_permission_sets")
            .select("*, permission_sets(id, name, display_name, is_active)")
            .eq("user_id", user_id)
            .execute()
        )

        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user permission sets: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user permission sets")
