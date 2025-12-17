"""
RBAC User Management endpoints.

[VERIFIED] Mirrors server.js lines 3262-3625:
1. GET /my-context - Get current user's RBAC context (lines 3262-3279)
2. GET /users - List all users with pagination (lines 3286-3354)
3. PUT /users/:userId - Update user (lines 3357-3410)
4. POST /users/:userId/deactivate - Deactivate user (lines 3413-3495)
5. POST /users/:userId/reactivate - Reactivate user (lines 3498-3521)
6. GET /audit-log - Get audit log (lines 3573-3625)

6 endpoints total.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.middleware.auth import AuthUser, require_auth, require_profile
from backend.routers.rbac.models import UpdateUserRequest
from backend.services.rbac_service import get_user_rbac_data, invalidate_rbac_cache
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter()


# =============================================================================
# 1. GET /my-context - server.js:3262-3279
# =============================================================================

@router.get("/my-context")
async def get_my_context(
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Get current user's RBAC context.
    Mirrors server.js:3262-3279
    """
    try:
        # server.js:3264
        rbac = await get_user_rbac_data(user.id)

        # server.js:3266-3268
        if not rbac:
            raise HTTPException(status_code=403, detail="User not found or deactivated")

        # server.js:3270-3274
        return {
            "userId": user.id,
            "email": user.email,
            **rbac
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user context")


# =============================================================================
# 2. GET /users - server.js:3286-3354
# =============================================================================

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = None,
    profile: str | None = None,
    team: int | None = None,
    is_active: str | None = None,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    List all users with pagination and filters.
    Mirrors server.js:3286-3354
    """
    # server.js:3288
    offset = (page - 1) * limit

    logger.info(f"[UI RBAC API] Listing users (page={page}, limit={limit}, search={search})")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3293-3299
        query = (
            supabase.table("users")
            .select(
                "*, profiles(id, name, display_name), team_members(team_id, role, teams(id, name, display_name))",
                count="exact"
            )
        )

        # server.js:3301-3321 - Apply filters
        if search:
            query = query.or_(f"email.ilike.%{search}%,name.ilike.%{search}%")

        if profile:
            # server.js:3307-3316 - Get profile ID first
            profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", profile)
                .single()
                .execute()
            )
            if profile_response.data:
                query = query.eq("profile_id", profile_response.data["id"])

        if is_active is not None:
            query = query.eq("is_active", is_active == "true")

        # server.js:3324-3326 - Apply pagination
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        response = query.execute()
        users = response.data or []
        count = response.count or 0

        # server.js:3333-3339 - Filter by team (post-query filter)
        if team:
            users = [
                u for u in users
                if u.get("team_members") and any(
                    tm.get("team_id") == team for tm in u["team_members"]
                )
            ]

        # server.js:3341-3348
        return {
            "users": users,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": count,
                "totalPages": (count + limit - 1) // limit if count > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing users: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")


# =============================================================================
# 3. PUT /users/:userId - server.js:3357-3410
# =============================================================================

@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update user details.
    Mirrors server.js:3357-3410
    """
    logger.info(f"[UI RBAC API] Updating user: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3364-3367
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.avatar_url is not None:
            updates["avatar_url"] = request.avatar_url
        if request.is_active is not None:
            updates["is_active"] = request.is_active

        # server.js:3369-3384 - Handle profile assignment by name or ID
        if request.profile_name is not None:
            profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", request.profile_name)
                .single()
                .execute()
            )
            if profile_response.data:
                updates["profile_id"] = profile_response.data["id"]
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Profile '{request.profile_name}' not found"
                )
        elif request.profile_id is not None:
            updates["profile_id"] = request.profile_id

        # server.js:3386-3388
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # server.js:3390-3398
        response = (
            supabase.table("users")
            .update(updates)
            .eq("id", user_id)
            .select("*, profiles(id, name, display_name)")
            .single()
            .execute()
        )

        # server.js:3402-3403 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return response.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")


# =============================================================================
# 4. POST /users/:userId/deactivate - server.js:3413-3495
# =============================================================================

@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Deactivate user (soft delete).
    Mirrors server.js:3413-3495
    """
    logger.info(f"[UI RBAC API] Deactivating user: {user_id}")

    # server.js:3419-3422 - Prevent self-deactivation
    if user_id == user.id:
        raise HTTPException(status_code=403, detail="Cannot deactivate your own account")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3424-3436 - Get the user being deactivated
        target_response = (
            supabase.table("users")
            .select("id, email, profile_id, profiles(name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not target_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        target_user = target_response.data

        # server.js:3438-3464 - If target is system_admin, check if they're the last one
        if target_user.get("profiles", {}).get("name") == "system_admin":
            # Get the system_admin profile ID
            admin_profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", "system_admin")
                .single()
                .execute()
            )

            if admin_profile_response.data:
                # Count active system admins
                count_response = (
                    supabase.table("users")
                    .select("id", count="exact", head=True)
                    .eq("profile_id", admin_profile_response.data["id"])
                    .eq("is_active", True)
                    .execute()
                )

                if count_response.count and count_response.count <= 1:
                    raise HTTPException(
                        status_code=403,
                        detail="Cannot deactivate the last system administrator"
                    )

        # server.js:3466-3471 - Deactivate user
        response = (
            supabase.table("users")
            .update({"is_active": False})
            .eq("id", user_id)
            .select()
            .single()
            .execute()
        )

        # server.js:3475-3476 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        # server.js:3478-3488 - Audit log
        supabase.table("audit_log").insert({
            "user_id": user.id,
            "action": "user.deactivate",
            "action_category": "user_management",
            "resource_type": "user",
            "resource_id": user_id,
            "target_user_id": user_id,
            "old_value": {"is_active": True},
            "new_value": {"is_active": False}
        }).execute()

        return {"success": True, "user": response.data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deactivating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to deactivate user")


# =============================================================================
# 5. POST /users/:userId/reactivate - server.js:3498-3521
# =============================================================================

@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Reactivate user.
    Mirrors server.js:3498-3521
    """
    logger.info(f"[UI RBAC API] Reactivating user: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3503-3509
        response = (
            supabase.table("users")
            .update({"is_active": True})
            .eq("id", user_id)
            .select()
            .single()
            .execute()
        )

        # server.js:3513-3514 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return {"success": True, "user": response.data}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error reactivating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to reactivate user")


# =============================================================================
# 6. GET /audit-log - server.js:3573-3625
# =============================================================================

@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = None,
    action_category: str | None = None,
    user_id: str | None = None,
    target_user_id: str | None = None,
    resource_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Get audit log with filters.
    Mirrors server.js:3573-3625
    """
    # server.js:3585
    offset = (page - 1) * limit

    logger.info("[UI RBAC API] Fetching audit log")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3590-3592
        query = supabase.table("audit_log").select("*", count="exact")

        # server.js:3594-3601 - Apply filters
        if action:
            query = query.eq("action", action)
        if action_category:
            query = query.eq("action_category", action_category)
        if user_id:
            query = query.eq("user_id", user_id)
        if target_user_id:
            query = query.eq("target_user_id", target_user_id)
        if resource_type:
            query = query.eq("resource_type", resource_type)
        if from_date:
            query = query.gte("timestamp", from_date)
        if to_date:
            query = query.lte("timestamp", to_date)

        # server.js:3604-3606 - Apply pagination and ordering
        query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)

        response = query.execute()
        logs = response.data or []
        count = response.count or 0

        # server.js:3612-3619
        return {
            "logs": logs,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": count,
                "totalPages": (count + limit - 1) // limit if count > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"[UI RBAC API] Error fetching audit log: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch audit log")
