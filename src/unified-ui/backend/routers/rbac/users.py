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

from backend.middleware.auth import AuthUser, require_auth, require_permission
from backend.routers.rbac.models import (
    AssignUserProfileRequest,
    CreateUserRequest,
    SetUserPermissionsRequest,
    UpdateUserRequest,
)
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
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
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
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
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
        # Update first, then fetch (supabase-py doesn't support chaining .select() after .update())
        supabase.table("users").update(updates).eq("id", user_id).execute()
        response = (
            supabase.table("users")
            .select("*, profiles(id, name, display_name)")
            .eq("id", user_id)
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
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
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
        # Update first, then fetch (supabase-py doesn't support chaining .select() after .update())
        supabase.table("users").update({"is_active": False}).eq("id", user_id).execute()
        response = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
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
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
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
        # Update first, then fetch (supabase-py doesn't support chaining .select() after .update())
        supabase.table("users").update({"is_active": True}).eq("id", user_id).execute()
        response = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
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
# 6. PUT /users/:userId/profile - Assign profile to user
# =============================================================================

@router.put("/users/{user_id}/profile")
async def assign_user_profile(
    user_id: str,
    request: AssignUserProfileRequest,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Assign a profile to a user by profile name.
    """
    logger.info(f"[UI RBAC API] Assigning profile '{request.profile_name}' to user {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Get profile ID by name
        profile_response = (
            supabase.table("profiles")
            .select("id, name, display_name")
            .eq("name", request.profile_name)
            .single()
            .execute()
        )

        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{request.profile_name}' not found"
            )

        profile = profile_response.data

        # Update user's profile
        # Update first, then fetch (supabase-py doesn't support chaining .select() after .update())
        supabase.table("users").update({"profile_id": profile["id"]}).eq("id", user_id).execute()
        response = (
            supabase.table("users")
            .select("*, profiles(id, name, display_name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return {
            "success": True,
            "user": response.data,
            "profile": profile
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error assigning profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign profile")


# =============================================================================
# 7. GET /users/:userId/permissions - Get user's permissions
# =============================================================================

@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Get all permissions for a user (from profile + permission sets).
    """
    logger.info(f"[UI RBAC API] Getting permissions for user {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Get user with profile
        user_response = (
            supabase.table("users")
            .select("id, email, name, profile_id, profiles(id, name, display_name)")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = user_response.data
        profile = user_data.get("profiles")

        # Get permissions from profile
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

        # Get permission sets and their permissions
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
                    # Get permissions from this set
                    ps_perms = (
                        supabase.table("permission_set_permissions")
                        .select("permission")
                        .eq("permission_set_id", ps["id"])
                        .execute()
                    )
                    if ps_perms.data:
                        permissions.extend([p["permission"] for p in ps_perms.data])

        # Deduplicate
        permissions = list(set(permissions))

        return {
            "user_id": user_id,
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "profile": profile.get("name") if profile else None,
            "profile_display_name": profile.get("display_name") if profile else None,
            "permissions": sorted(permissions),
            "permission_sets": [ps.get("name") for ps in permission_sets],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user permissions")


# =============================================================================
# 8. GET /audit-log - server.js:3573-3625
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
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
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


# =============================================================================
# 9. GET /user/:userId - Get single user
# =============================================================================

@router.get("/user/{user_id}")
async def get_user(
    user_id: str,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Get a single user by ID with profile and team info.
    """
    logger.info(f"[UI RBAC API] Getting user: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        response = (
            supabase.table("users")
            .select("""
                id, email, name, is_active, created_at, updated_at, last_login_at,
                profile_id, profiles(id, name, display_name),
                team_members(team_id, role, teams(id, name))
            """)
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        return response.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user")


# =============================================================================
# 10. POST /users - Create user (pre-create for SSO)
# =============================================================================

@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Pre-create a user for SSO approval flow.
    Creates a pending user that will be activated on first SSO login.
    """
    import uuid
    from datetime import datetime

    logger.info(f"[UI RBAC API] Creating user: {request.email}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    email = request.email.lower()

    try:
        # Check if user already exists
        existing = (
            supabase.table("users")
            .select("id")
            .eq("email", email)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            raise HTTPException(status_code=409, detail="User with this email already exists")

        # Get profile ID
        profile_to_use = request.profile_name or "sales_user"
        profile_response = (
            supabase.table("profiles")
            .select("id")
            .eq("name", profile_to_use)
            .single()
            .execute()
        )

        if not profile_response.data:
            raise HTTPException(status_code=400, detail=f"Profile not found: {profile_to_use}")

        # Generate pending ID
        pending_id = f"pending-{uuid.uuid4()}"

        # Create the pending user
        supabase.table("users").insert({
            "id": pending_id,
            "email": email,
            "name": request.name,
            "profile_id": profile_response.data["id"],
            "is_active": True,
            "metadata_json": {
                "created_by": user.id,
                "created_by_email": user.email,
                "pending_sso": True
            }
        }).execute()

        new_user_response = (
            supabase.table("users")
            .select("*")
            .eq("id", pending_id)
            .single()
            .execute()
        )

        if not new_user_response.data:
            raise HTTPException(status_code=500, detail="Failed to create user")

        # Add to team if specified
        if request.team_id:
            supabase.table("team_members").insert({
                "team_id": request.team_id,
                "user_id": pending_id,
                "role": "member",
                "joined_at": datetime.utcnow().isoformat()
            }).execute()

        # Audit log
        try:
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "user.create",
                "action_category": "user_management",
                "resource_type": "user",
                "resource_id": pending_id,
                "details": {"email": email, "profile_name": profile_to_use, "team_id": request.team_id},
                "success": True
            }).execute()
        except Exception:
            pass

        logger.info(f"[UI RBAC API] User pre-created: {email} by {user.email}")

        return {
            "success": True,
            "user": new_user_response.data,
            "message": f"User {email} created. They can now sign in with Microsoft SSO."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


# =============================================================================
# 11. DELETE /users/:userId - Delete user (hard delete)
# =============================================================================

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Permanently delete a user.
    Note: For most cases, deactivate is preferred over delete.
    """
    logger.info(f"[UI RBAC API] Deleting user: {user_id}")

    # Prevent self-deletion
    if user_id == user.id:
        raise HTTPException(status_code=403, detail="Cannot delete your own account")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Get user to verify exists
        user_response = (
            supabase.table("users")
            .select("id, email")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        target_email = user_response.data.get("email")

        # Delete team memberships first (FK constraint)
        supabase.table("team_members").delete().eq("user_id", user_id).execute()

        # Delete user permission sets (FK constraint)
        supabase.table("user_permission_sets").delete().eq("user_id", user_id).execute()

        # Delete record shares (FK constraint)
        supabase.table("record_shares").delete().eq("shared_by_user_id", user_id).execute()
        supabase.table("record_shares").delete().eq("shared_with_user_id", user_id).execute()

        # Delete the user
        supabase.table("users").delete().eq("id", user_id).execute()

        # Clear RBAC cache
        invalidate_rbac_cache(user_id)

        # Audit log
        try:
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "user.delete",
                "action_category": "user_management",
                "resource_type": "user",
                "resource_id": user_id,
                "target_user_id": user_id,
                "details": {"deleted_email": target_email},
                "success": True
            }).execute()
        except Exception:
            pass

        logger.info(f"[UI RBAC API] User deleted: {target_email} by {user.email}")

        return {"success": True, "deleted": user_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user")


# =============================================================================
# 12. PUT /users/:userId/permissions - Set user's direct permissions
# =============================================================================

@router.put("/users/{user_id}/permissions")
async def set_user_permissions(
    user_id: str,
    request: SetUserPermissionsRequest,
    user: AuthUser = Depends(require_permission("admin:rbac:manage")),
) -> dict[str, Any]:
    """
    Set direct permissions for a user (via a custom permission set).
    This creates/updates a user-specific permission set.
    """
    logger.info(f"[UI RBAC API] Setting permissions for user: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Verify user exists
        user_response = (
            supabase.table("users")
            .select("id, email")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Find or create a user-specific permission set
        set_name = f"user_{user_id}_custom"
        set_display_name = f"Custom permissions for {user_response.data['email']}"

        existing_set = (
            supabase.table("permission_sets")
            .select("id")
            .eq("name", set_name)
            .execute()
        )

        if existing_set.data and len(existing_set.data) > 0:
            set_id = existing_set.data[0]["id"]
            # Clear existing permissions
            supabase.table("permission_set_permissions").delete().eq("permission_set_id", set_id).execute()
        else:
            # Create new permission set
            new_set = (
                supabase.table("permission_sets")
                .insert({
                    "name": set_name,
                    "display_name": set_display_name,
                    "description": "Auto-generated custom permissions",
                    "is_active": True
                })
                .execute()
            )
            set_id = new_set.data[0]["id"]

            # Assign to user
            supabase.table("user_permission_sets").insert({
                "user_id": user_id,
                "permission_set_id": set_id
            }).execute()

        # Add new permissions
        if request.permissions:
            for perm in request.permissions:
                supabase.table("permission_set_permissions").insert({
                    "permission_set_id": set_id,
                    "permission": perm
                }).execute()

        # Clear RBAC cache
        invalidate_rbac_cache(user_id)

        return {
            "success": True,
            "user_id": user_id,
            "permissions": request.permissions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error setting user permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to set user permissions")
