"""
RBAC Level 3: Team Management endpoints.

[VERIFIED] Mirrors server.js lines 2841-3084:
1. GET /teams - List all teams (lines 2846-2865)
2. POST /teams - Create team (lines 2868-2891)
3. PUT /teams/:id - Update team (lines 2894-2922)
4. DELETE /teams/:id - Delete team (lines 2925-2943)
5. GET /teams/:id/members - Get team members (lines 2946-2965)
6. POST /teams/:id/members - Add user to team (lines 2968-2999)
7. PUT /teams/:id/members/:userId - Update member role (lines 3002-3031)
8. DELETE /teams/:id/members/:userId - Remove from team (lines 3034-3056)
9. PUT /users/:userId/manager - Set user's manager (lines 3059-3084)

9 endpoints total.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from backend.middleware.auth import AuthUser, require_profile
from backend.services.supabase_client import get_supabase
from backend.services.rbac_service import invalidate_rbac_cache
from backend.routers.rbac.models import (
    CreateTeamRequest,
    UpdateTeamRequest,
    AddTeamMemberRequest,
    UpdateTeamMemberRequest,
    SetManagerRequest,
)

logger = logging.getLogger("unified-ui")

router = APIRouter()


# =============================================================================
# 1. GET /teams - server.js:2846-2865
# =============================================================================

@router.get("/teams")
async def list_teams(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> List[Dict[str, Any]]:
    """
    List all teams.
    Mirrors server.js:2846-2865
    """
    logger.info("[UI RBAC API] Listing teams")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2850-2856
        response = (
            supabase.table("teams")
            .select("*, parent:parent_team_id(id, name, display_name)")
            .order("name")
            .execute()
        )

        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing teams: {e}")
        raise HTTPException(status_code=500, detail="Failed to list teams")


# =============================================================================
# 2. POST /teams - server.js:2868-2891
# =============================================================================

@router.post("/teams", status_code=201)
async def create_team(
    request: CreateTeamRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Create team.
    Mirrors server.js:2868-2891
    """
    # server.js:2871-2873
    if not request.name:
        raise HTTPException(status_code=400, detail="name is required")

    logger.info(f"[UI RBAC API] Creating team: {request.name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2878-2882
        response = (
            supabase.table("teams")
            .insert({
                "name": request.name,
                "display_name": request.display_name or request.name,
                "description": request.description,
                "parent_team_id": request.parent_team_id
            })
            .select()
            .single()
            .execute()
        )

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating team: {e}")
        raise HTTPException(status_code=500, detail="Failed to create team")


# =============================================================================
# 3. PUT /teams/:id - server.js:2894-2922
# =============================================================================

@router.put("/teams/{team_id}")
async def update_team(
    team_id: int,
    request: UpdateTeamRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Update team.
    Mirrors server.js:2894-2922
    """
    logger.info(f"[UI RBAC API] Updating team: {team_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2901-2906 - Build updates
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.description is not None:
            updates["description"] = request.description
        if request.parent_team_id is not None:
            updates["parent_team_id"] = request.parent_team_id
        if request.is_active is not None:
            updates["is_active"] = request.is_active

        # server.js:2908-2913
        response = (
            supabase.table("teams")
            .update(updates)
            .eq("id", team_id)
            .select()
            .single()
            .execute()
        )

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating team: {e}")
        raise HTTPException(status_code=500, detail="Failed to update team")


# =============================================================================
# 4. DELETE /teams/:id - server.js:2925-2943
# =============================================================================

@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Delete team.
    Mirrors server.js:2925-2943
    """
    logger.info(f"[UI RBAC API] Deleting team: {team_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2931-2934
        supabase.table("teams").delete().eq("id", team_id).execute()
        return {"success": True}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting team: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete team")


# =============================================================================
# 5. GET /teams/:id/members - server.js:2946-2965
# =============================================================================

@router.get("/teams/{team_id}/members")
async def get_team_members(
    team_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> List[Dict[str, Any]]:
    """
    Get team members.
    Mirrors server.js:2946-2965
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2950-2956
        response = (
            supabase.table("team_members")
            .select("*, users(id, email, name, is_active)")
            .eq("team_id", team_id)
            .execute()
        )

        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting team members: {e}")
        raise HTTPException(status_code=500, detail="Failed to get team members")


# =============================================================================
# 6. POST /teams/:id/members - server.js:2968-2999
# =============================================================================

@router.post("/teams/{team_id}/members", status_code=201)
async def add_team_member(
    team_id: int,
    request: AddTeamMemberRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Add user to team.
    Mirrors server.js:2968-2999
    """
    # server.js:2972-2974
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    logger.info(f"[UI RBAC API] Adding user {request.user_id} to team {team_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:2979-2987
        response = (
            supabase.table("team_members")
            .insert({
                "team_id": team_id,
                "user_id": request.user_id,
                "role": request.role or "member"
            })
            .select()
            .single()
            .execute()
        )

        # server.js:2992 - Clear RBAC cache
        invalidate_rbac_cache(request.user_id)

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error adding team member: {e}")
        raise HTTPException(status_code=500, detail="Failed to add team member")


# =============================================================================
# 7. PUT /teams/:id/members/:userId - server.js:3002-3031
# =============================================================================

@router.put("/teams/{team_id}/members/{member_user_id}")
async def update_team_member(
    team_id: int,
    member_user_id: str,
    request: UpdateTeamMemberRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Update team member role.
    Mirrors server.js:3002-3031
    """
    # server.js:3006-3008
    if not request.role or request.role not in ["member", "leader"]:
        raise HTTPException(status_code=400, detail="Valid role (member or leader) is required")

    logger.info(f"[UI RBAC API] Updating role for user {member_user_id} in team {team_id} to {request.role}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3013-3019
        response = (
            supabase.table("team_members")
            .update({"role": request.role})
            .eq("team_id", team_id)
            .eq("user_id", member_user_id)
            .select()
            .single()
            .execute()
        )

        # server.js:3024 - Clear RBAC cache
        invalidate_rbac_cache(member_user_id)

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating team member: {e}")
        raise HTTPException(status_code=500, detail="Failed to update team member")


# =============================================================================
# 8. DELETE /teams/:id/members/:userId - server.js:3034-3056
# =============================================================================

@router.delete("/teams/{team_id}/members/{member_user_id}")
async def remove_team_member(
    team_id: int,
    member_user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Remove user from team.
    Mirrors server.js:3034-3056
    """
    logger.info(f"[UI RBAC API] Removing user {member_user_id} from team {team_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3040-3044
        supabase.table("team_members").delete().eq("team_id", team_id).eq("user_id", member_user_id).execute()

        # server.js:3049 - Clear RBAC cache
        invalidate_rbac_cache(member_user_id)

        return {"success": True}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error removing team member: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove team member")


# =============================================================================
# 9. PUT /users/:userId/manager - server.js:3059-3084
# =============================================================================

@router.put("/users/{user_id}/manager")
async def set_user_manager(
    user_id: str,
    request: SetManagerRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> Dict[str, Any]:
    """
    Set user's manager.
    Mirrors server.js:3059-3084
    """
    logger.info(f"[UI RBAC API] Setting manager for user {user_id} to {request.manager_id or 'none'}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3066-3071
        response = (
            supabase.table("users")
            .update({"manager_id": request.manager_id})
            .eq("id", user_id)
            .select()
            .single()
            .execute()
        )

        # server.js:3076-3077 - Clear RBAC cache for user and manager
        invalidate_rbac_cache(user_id)
        if request.manager_id:
            invalidate_rbac_cache(request.manager_id)

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error setting manager: {e}")
        raise HTTPException(status_code=500, detail="Failed to set manager")
