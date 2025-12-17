"""
Channel Identity router for unified-ui.

[VERIFIED] Mirrors server.js lines 3952-4146:
1. POST /record - Record channel user interaction (lines 3960-4005)
2. GET /check/{provider}/{provider_id} - Check authorization (lines 4008-4024)
3. GET /list - List all identities (lines 4027-4046)
4. GET /pending-links - Get pending links (lines 4049-4057)
5. POST /link - Link identity to user (lines 4060-4078)
6. POST /auto-link - Auto-link by email (lines 4081-4089)
7. POST /block - Block/unblock user (lines 4092-4111)
8. GET /settings - Get settings (lines 4114-4126)
9. PUT /settings - Update settings (lines 4128-4146)

9 endpoints total.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.middleware.auth import AuthUser, require_profile
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter(prefix="/api/channel-identity", tags=["channel-identity"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class RecordInteractionRequest(BaseModel):
    provider: str
    provider_user_id: str
    provider_team_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    avatar_url: str | None = None


class LinkIdentityRequest(BaseModel):
    provider_user_id: str
    platform_user_id: str


class BlockIdentityRequest(BaseModel):
    provider_user_id: str
    blocked: bool
    reason: str | None = None


class UpdateSettingsRequest(BaseModel):
    require_platform_auth: bool


# =============================================================================
# 1. POST /record - server.js:3960-4005
# =============================================================================

@router.post("/record")
async def record_interaction(
    request: RecordInteractionRequest,
) -> dict[str, Any]:
    """
    Record a channel user interaction.
    Called by bot services internally - no auth required.
    Mirrors server.js:3960-4005
    """
    # server.js:3971-3973
    if not request.provider or not request.provider_user_id:
        raise HTTPException(
            status_code=400,
            detail="provider and provider_user_id are required"
        )

    logger.info(f"[Channel Identity] Recording {request.provider} user: {request.provider_user_id}")

    supabase = get_supabase()
    if not supabase:
        return {"recorded": False, "is_authorized": True}

    try:
        # server.js:3978-3985
        response = supabase.rpc("record_slack_interaction", {
            "p_slack_user_id": request.provider_user_id,
            "p_slack_workspace_id": request.provider_team_id or "unknown",
            "p_slack_email": request.email,
            "p_slack_display_name": request.display_name,
            "p_slack_real_name": request.real_name,
            "p_slack_avatar_url": request.avatar_url
        }).execute()

        # server.js:3992-4000
        result = response.data[0] if response.data else {}
        return {
            "recorded": True,
            "identity_id": result.get("identity_id"),
            "platform_user_id": result.get("platform_user_id"),
            "is_linked": result.get("is_linked", False),
            "is_blocked": result.get("is_blocked", False),
            "is_authorized": not result.get("is_blocked") and (
                not result.get("require_auth") or result.get("is_linked")
            )
        }

    except Exception as e:
        logger.warning(f"[Channel Identity] DB error: {e}")
        return {"recorded": False, "is_authorized": True}


# =============================================================================
# 2. GET /check/{provider}/{provider_id} - server.js:4008-4024
# =============================================================================

@router.get("/check/{provider}/{provider_id}")
async def check_authorization(
    provider: str,
    provider_id: str,
) -> dict[str, Any]:
    """
    Check authorization status.
    No auth required - called by bot services.
    Mirrors server.js:4008-4024
    """
    supabase = get_supabase()
    if not supabase:
        return {"is_authorized": True, "reason": "check_failed"}

    try:
        # server.js:4012-4014
        response = supabase.rpc("check_slack_authorization", {
            "p_slack_user_id": provider_id
        }).execute()

        # server.js:4020
        return response.data[0] if response.data else {"is_authorized": True, "reason": "open_access"}

    except Exception as e:
        logger.error(f"[Channel Identity] Check error: {e}")
        return {"is_authorized": True, "reason": "check_failed"}


# =============================================================================
# 3. GET /list - server.js:4027-4046
# =============================================================================

@router.get("/list")
async def list_identities(
    linked: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    List all channel identities.
    Admin only.
    Mirrors server.js:4027-4046
    """
    offset = (page - 1) * limit

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4032
        query = supabase.table("slack_identities_full").select("*", count="exact")

        # server.js:4034-4035
        if linked == "true":
            query = query.not_.is_("user_id", "null")
        elif linked == "false":
            query = query.is_("user_id", "null")

        # server.js:4037-4039
        response = (
            query.order("last_seen_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "identities": response.data or [],
            "total": response.count or 0,
            "page": page,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"[Channel Identity] List error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list identities")


# =============================================================================
# 4. GET /pending-links - server.js:4049-4057
# =============================================================================

@router.get("/pending-links")
async def get_pending_links(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> list[dict[str, Any]]:
    """
    Get pending links.
    Admin only.
    Mirrors server.js:4049-4057
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4051
        response = supabase.table("slack_pending_links").select("*").execute()
        return response.data or []

    except Exception as e:
        logger.error(f"[Channel Identity] Pending links error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pending links")


# =============================================================================
# 5. POST /link - server.js:4060-4078
# =============================================================================

@router.post("/link")
async def link_identity(
    request: LinkIdentityRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Link identity to platform user.
    Admin only.
    Mirrors server.js:4060-4078
    """
    # server.js:4063-4065
    if not request.provider_user_id or not request.platform_user_id:
        raise HTTPException(
            status_code=400,
            detail="provider_user_id and platform_user_id required"
        )

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4068-4072
        supabase.rpc("link_slack_identity", {
            "p_slack_user_id": request.provider_user_id,
            "p_platform_user_id": request.platform_user_id,
            "p_linked_by": user.id
        }).execute()

        return {"success": True}

    except Exception as e:
        logger.error(f"[Channel Identity] Link error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 6. POST /auto-link - server.js:4081-4089
# =============================================================================

@router.post("/auto-link")
async def auto_link_by_email(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Auto-link identities by email.
    Admin only.
    Mirrors server.js:4081-4089
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4083
        response = supabase.rpc("auto_link_slack_by_email").execute()
        linked = response.data or []

        return {"linked": linked, "count": len(linked)}

    except Exception as e:
        logger.error(f"[Channel Identity] Auto-link error: {e}")
        raise HTTPException(status_code=500, detail="Failed to auto-link")


# =============================================================================
# 7. POST /block - server.js:4092-4111
# =============================================================================

@router.post("/block")
async def block_identity(
    request: BlockIdentityRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Block/unblock channel user.
    Admin only.
    Mirrors server.js:4092-4111
    """
    # server.js:4095-4097
    if not request.provider_user_id or request.blocked is None:
        raise HTTPException(
            status_code=400,
            detail="provider_user_id and blocked required"
        )

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4100-4105
        supabase.rpc("set_slack_blocked", {
            "p_slack_user_id": request.provider_user_id,
            "p_blocked": request.blocked,
            "p_reason": request.reason,
            "p_blocked_by": user.id
        }).execute()

        return {"success": True, "blocked": request.blocked}

    except Exception as e:
        logger.error(f"[Channel Identity] Block error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update block status")


# =============================================================================
# 8. GET /settings - server.js:4114-4126
# =============================================================================

@router.get("/settings")
async def get_settings(
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Get channel identity settings.
    Admin only.
    Mirrors server.js:4114-4126
    """
    supabase = get_supabase()
    if not supabase:
        return {"require_platform_auth": False}

    try:
        # server.js:4116-4120
        response = (
            supabase.table("system_settings")
            .select("*")
            .eq("key", "slack_require_platform_auth")
            .single()
            .execute()
        )

        value = response.data.get("value") if response.data else None
        return {"require_platform_auth": value is True or value == "true"}

    except Exception:
        return {"require_platform_auth": False}


# =============================================================================
# 9. PUT /settings - server.js:4128-4146
# =============================================================================

@router.put("/settings")
async def update_settings(
    request: UpdateSettingsRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update channel identity settings.
    Admin only.
    Mirrors server.js:4128-4146
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:4132-4139
        supabase.table("system_settings").upsert({
            "key": "slack_require_platform_auth",
            "value": request.require_platform_auth,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": user.id
        }).execute()

        return {"success": True, "require_platform_auth": request.require_platform_auth}

    except Exception as e:
        logger.error(f"[Channel Identity] Settings update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")
