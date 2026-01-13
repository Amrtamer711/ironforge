"""
Admin router for unified-ui.

[VERIFIED] Mirrors server.js lines 1540-1921:
- User management endpoints (lines 1540-1887)
- Profile/team lookup endpoints (lines 1889-1921)

10 endpoints total:
1. GET /api/admin/users - Get all users
2. GET /api/admin/users/pending - Get pending users awaiting approval
3. POST /api/admin/users/create - Pre-create a user for SSO
4. POST /api/admin/users/{userId}/approve - Approve a pending user
5. POST /api/admin/users/{userId}/deactivate - Deactivate a user
6. PATCH /api/admin/users/{userId} - Update user's profile/role
7. GET /api/admin/profiles - Get available profiles
8. GET /api/admin/teams - Get available teams
9. GET /api/admin/service-visibility - Get service visibility settings (public)
10. PUT /api/admin/service-visibility - Update service visibility (admin only)
"""

import contextlib
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from backend.middleware.auth import AuthUser, require_auth, require_profile
from backend.services.rbac_service import invalidate_rbac_cache
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    profile_name: str | None = None
    team_id: int | None = None


class ApproveUserRequest(BaseModel):
    profile_name: str | None = None


class UpdateUserRequest(BaseModel):
    profile_name: str | None = None
    name: str | None = None
    team_id: int | None = None


class ServiceVisibilityRequest(BaseModel):
    """Request model for updating service visibility settings."""
    chat: bool = True
    video_critique: bool = True
    mockup_setup: bool = True
    mockup_generate: bool = True
    proposals: bool = True
    asset_management: bool = True


# Default service visibility (all enabled)
DEFAULT_SERVICE_VISIBILITY = {
    "chat": True,
    "video_critique": True,
    "mockup_setup": True,
    "mockup_generate": True,
    "proposals": True,
    "asset_management": True,
}

SERVICE_VISIBILITY_KEY = "service_visibility"


# =============================================================================
# USER MANAGEMENT ENDPOINTS - server.js:1540-1887
# =============================================================================

@router.get("/users")
async def get_all_users(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, list[dict[str, Any]]]:
    """
    Get all users.
    Mirrors server.js:1541-1559
    """
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
            .order("created_at", desc=True)
            .execute()
        )

        return {"users": response.data or []}

    except Exception as e:
        logger.error(f"[UI Admin] Error fetching users: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch users")


@router.get("/users/pending")
async def get_pending_users(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, list[dict[str, Any]]]:
    """
    Get pending users awaiting approval.
    Mirrors server.js:1561-1580
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        response = (
            supabase.table("users")
            .select("""
                id, email, name, is_active, created_at, metadata_json,
                profile_id, profiles(id, name, display_name)
            """)
            .eq("is_active", False)
            .order("created_at", desc=True)
            .execute()
        )

        return {"users": response.data or []}

    except Exception as e:
        logger.error(f"[UI Admin] Error fetching pending users: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pending users")


@router.post("/users/create")
async def create_user(
    request: CreateUserRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Pre-create a user for SSO approval flow.
    Mirrors server.js:1582-1670
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    email = request.email.lower()

    try:
        # server.js:1591-1600 - Check if user already exists
        existing = (
            supabase.table("users")
            .select("id")
            .eq("email", email)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            raise HTTPException(status_code=409, detail="User with this email already exists")

        # server.js:1602-1612 - Get profile ID
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

        # server.js:1614-1615 - Generate pending ID
        pending_id = f"pending-{uuid.uuid4()}"

        # server.js:1617-1635 - Create the pending user
        # Insert first, then fetch (supabase-py doesn't support chaining .select() after .insert())
        supabase.table("users").insert({
            "id": pending_id,
            "email": email,
            "name": request.name,
            "profile_id": profile_response.data["id"],
            "is_active": True,  # Pre-created users are active
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

        # server.js:1637-1645 - Add to team if specified
        if request.team_id:
            supabase.table("team_members").insert({
                "team_id": request.team_id,
                "user_id": pending_id,
                "role": "member",
                "joined_at": datetime.utcnow().isoformat()
            }).execute()

        # server.js:1647-1657 - Audit log
        try:
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "admin.user_created",
                "action_category": "admin",
                "resource_type": "user",
                "resource_id": pending_id,
                "details": {"email": email, "profile_name": profile_to_use, "team_id": request.team_id},
                "success": True
            }).execute()
        except Exception:
            pass  # Don't fail for audit log issues

        logger.info(f"[UI Admin] User pre-created: {email} by {user.email}")

        return {
            "success": True,
            "user": new_user_response.data,
            "message": f"User {email} created. They can now sign in with Microsoft SSO."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI Admin] Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    request: ApproveUserRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Approve a pending user.
    Mirrors server.js:1672-1753
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1677-1691 - Get the user
        user_response = (
            supabase.table("users")
            .select("id, email, is_active, metadata_json")
            .eq("id", user_id)
            .single()
            .execute()
        )

        target_user = user_response.data
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        if target_user.get("is_active"):
            raise HTTPException(status_code=400, detail="User is already active")

        # server.js:1693-1705 - Get new profile if specified
        profile_id = None
        if request.profile_name:
            profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", request.profile_name)
                .single()
                .execute()
            )

            if profile_response.data:
                profile_id = profile_response.data["id"]

        # server.js:1718-1728 - Approve the user
        now = datetime.utcnow()

        # server.js:1707-1716 - Update metadata_json with approval info
        current_metadata = target_user.get("metadata_json") or {}
        updated_metadata = {
            **current_metadata,
            "approved_by": user.id,
            "approved_by_email": user.email,
            "approved_at": now.isoformat()
        }

        update_data = {
            "is_active": True,
            "updated_at": now.isoformat(),
            "metadata_json": updated_metadata
        }
        if profile_id:
            update_data["profile_id"] = profile_id

        supabase.table("users").update(update_data).eq("id", user_id).execute()

        # server.js:1730-1741 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "admin.user_approved",
                "action_category": "admin",
                "resource_type": "user",
                "resource_id": user_id,
                "target_user_id": user_id,
                "details": {"profile_name": request.profile_name},
                "success": True
            }).execute()

        logger.info(f"[UI Admin] User approved: {target_user['email']} by {user.email}")

        return {
            "success": True,
            "message": f"User {target_user['email']} has been approved and can now access the platform."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI Admin] Error approving user: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve user")


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Deactivate a user.
    Mirrors server.js:1755-1812
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # server.js:1760-1763 - Prevent self-deactivation
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    try:
        # server.js:1765-1773 - Get the user
        user_response = (
            supabase.table("users")
            .select("id, email")
            .eq("id", user_id)
            .single()
            .execute()
        )

        target_user = user_response.data
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # server.js:1775-1784 - Deactivate
        supabase.table("users").update({
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()

        # server.js:1786-1788 - Force logout the user
        invalidate_rbac_cache(user_id)
        with contextlib.suppress(Exception):
            supabase.auth.admin.sign_out(user_id)

        # server.js:1790-1800 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "admin.user_deactivated",
                "action_category": "admin",
                "resource_type": "user",
                "resource_id": user_id,
                "target_user_id": user_id,
                "success": True
            }).execute()

        logger.info(f"[UI Admin] User deactivated: {target_user['email']} by {user.email}")

        return {
            "success": True,
            "message": f"User {target_user['email']} has been deactivated."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI Admin] Error deactivating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to deactivate user")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update user's profile/role.
    Mirrors server.js:1814-1887
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1819-1822 - Build updates
        updates = {
            "updated_at": datetime.utcnow().isoformat()
        }

        if request.name is not None:
            updates["name"] = request.name

        # server.js:1828-1839 - Get profile if specified
        if request.profile_name:
            profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", request.profile_name)
                .single()
                .execute()
            )

            if not profile_response.data:
                raise HTTPException(status_code=400, detail=f"Profile not found: {request.profile_name}")

            updates["profile_id"] = profile_response.data["id"]

        # server.js:1841-1846 - Update user
        supabase.table("users").update(updates).eq("id", user_id).execute()

        # server.js:1848-1862 - Update team membership if specified
        if request.team_id is not None:
            # Remove from all teams first
            supabase.table("team_members").delete().eq("user_id", user_id).execute()

            # Add to new team if specified
            if request.team_id:
                supabase.table("team_members").insert({
                    "team_id": request.team_id,
                    "user_id": user_id,
                    "role": "member",
                    "joined_at": datetime.utcnow().isoformat()
                }).execute()

        # server.js:1864-1865 - Invalidate RBAC cache
        invalidate_rbac_cache(user_id)

        # server.js:1867-1878 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "admin.user_updated",
                "action_category": "admin",
                "resource_type": "user",
                "resource_id": user_id,
                "target_user_id": user_id,
                "details": {
                    "profile_name": request.profile_name,
                    "name": request.name,
                    "team_id": request.team_id
                },
                "success": True
            }).execute()

        logger.info(f"[UI Admin] User updated: {user_id} by {user.email}")
        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI Admin] Error updating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")


# =============================================================================
# LOOKUP ENDPOINTS - server.js:1889-1921
# =============================================================================

@router.get("/profiles")
async def get_profiles(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, list[dict[str, Any]]]:
    """
    Get available profiles for admin UI dropdowns.
    Mirrors server.js:1889-1904
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        response = (
            supabase.table("profiles")
            .select("id, name, display_name, description")
            .order("display_name")
            .execute()
        )

        return {"profiles": response.data or []}

    except Exception as e:
        logger.error(f"[UI Admin] Error fetching profiles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch profiles")


@router.get("/teams")
async def get_teams(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, list[dict[str, Any]]]:
    """
    Get available teams for admin UI dropdowns.
    Mirrors server.js:1906-1921
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        response = (
            supabase.table("teams")
            .select("id, name, description")
            .order("name")
            .execute()
        )

        return {"teams": response.data or []}

    except Exception as e:
        logger.error(f"[UI Admin] Error fetching teams: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch teams")


# =============================================================================
# SERVICE VISIBILITY ENDPOINTS
# =============================================================================

@router.get("/service-visibility")
async def get_service_visibility() -> dict[str, Any]:
    """
    Get service visibility settings.

    This endpoint is PUBLIC (no auth required) so the frontend can
    determine which services to show in the sidebar even when auth
    is slow or timing out. This prevents the page from being stuck
    on "Loading" when Supabase is having issues.

    Returns defaults if no settings are stored or on any error.

    When DEV_ALL_SERVICES_VISIBLE env var is set, returns all services as visible
    (dev mode bypass for testing).
    """
    import os

    # Dev mode bypass - when running with --dev-all-services flag
    if os.environ.get("DEV_ALL_SERVICES_VISIBLE") == "true":
        logger.debug("[UI Admin] Dev mode: forcing all services visible")
        return {**DEFAULT_SERVICE_VISIBILITY, "_dev_mode": True}

    supabase = get_supabase()
    if not supabase:
        # Return defaults if Supabase not configured
        return DEFAULT_SERVICE_VISIBILITY

    try:
        response = (
            supabase.table("system_settings")
            .select("value")
            .eq("key", SERVICE_VISIBILITY_KEY)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0 and response.data[0].get("value"):
            # Merge with defaults to handle any new services added later
            stored = response.data[0]["value"]
            merged = {**DEFAULT_SERVICE_VISIBILITY, **stored}
            return merged

        return DEFAULT_SERVICE_VISIBILITY

    except Exception as e:
        logger.error(f"[UI Admin] Error fetching service visibility: {e}")
        # Return defaults on error
        return DEFAULT_SERVICE_VISIBILITY


@router.put("/service-visibility")
async def update_service_visibility(
    request: ServiceVisibilityRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update service visibility settings.

    Admin-only endpoint to toggle which services are visible in the sidebar.
    Settings persist in the system_settings table.
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        visibility = {
            "chat": request.chat,
            "video_critique": request.video_critique,
            "mockup_setup": request.mockup_setup,
            "mockup_generate": request.mockup_generate,
            "proposals": request.proposals,
            "asset_management": request.asset_management,
        }

        # Upsert to system_settings table
        supabase.table("system_settings").upsert({
            "key": SERVICE_VISIBILITY_KEY,
            "value": visibility,
            "description": "Service visibility settings for sidebar",
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": user.email,
        }, on_conflict="key").execute()

        # Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "admin.service_visibility_updated",
                "action_category": "admin",
                "resource_type": "system_settings",
                "resource_id": SERVICE_VISIBILITY_KEY,
                "details": visibility,
                "success": True
            }).execute()

        logger.info(f"[UI Admin] Service visibility updated by {user.email}: {visibility}")

        return {"success": True, "visibility": visibility}

    except Exception as e:
        logger.error(f"[UI Admin] Error updating service visibility: {e}")
        raise HTTPException(status_code=500, detail="Failed to update service visibility")
