"""
RBAC Level 4: Record Sharing endpoints.

[VERIFIED] Mirrors server.js lines 3086-3950:
1. GET /sharing-rules - List sharing rules (lines 3091-3112)
2. POST /sharing-rules - Create sharing rule (lines 3115-3138)
3. PUT /sharing-rules/:id - Update sharing rule (lines 3141-3172)
4. DELETE /sharing-rules/:id - Delete sharing rule (lines 3175-3193)
5. GET /record-shares/:objectType/:recordId - List record shares (lines 3199-3221)
6. DELETE /record-shares/:id - Revoke record share (lines 3224-3259)
7. PUT /record-shares/:id - Update record share (lines 3524-3569)
8. POST /shares - Create share (lines 3632-3718)
9. GET /shares/:objectType/:recordId - Get shares for record (lines 3721-3749)
10. GET /shares/shared-with-me - Get shares for current user (lines 3752-3812)
11. DELETE /shares/:id - Delete share (lines 3815-3872)
12. GET /check-access/:objectType/:recordId - Check access (lines 3875-3950)

12 endpoints total.
"""

import contextlib
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.middleware.auth import AuthUser, require_auth, require_profile
from backend.routers.rbac.models import (
    CreateShareRequest,
    CreateSharingRuleRequest,
    UpdateRecordShareRequest,
    UpdateSharingRuleRequest,
)
from backend.services.rbac_service import invalidate_rbac_cache
from backend.services.supabase_client import get_supabase

logger = logging.getLogger("unified-ui")

router = APIRouter()


# =============================================================================
# 1. GET /sharing-rules - server.js:3091-3112
# =============================================================================

@router.get("/sharing-rules")
async def list_sharing_rules(
    object_type: str | None = None,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> list[dict[str, Any]]:
    """
    List sharing rules.
    Mirrors server.js:3091-3112
    """
    logger.info("[UI RBAC API] Listing sharing rules")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3097-3101
        query = supabase.table("sharing_rules").select("*").order("object_type, name")

        if object_type:
            query = query.eq("object_type", object_type)

        response = query.execute()
        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing sharing rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to list sharing rules")


# =============================================================================
# 2. POST /sharing-rules - server.js:3115-3138
# =============================================================================

@router.post("/sharing-rules", status_code=201)
async def create_sharing_rule(
    request: CreateSharingRuleRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Create sharing rule.
    Mirrors server.js:3115-3138
    """
    # server.js:3118-3120
    if not request.name or not request.object_type or not request.share_from_type or not request.share_to_type or not request.access_level:
        raise HTTPException(
            status_code=400,
            detail="name, object_type, share_from_type, share_to_type, and access_level are required"
        )

    logger.info(f"[UI RBAC API] Creating sharing rule: {request.name}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3125-3129
        response = (
            supabase.table("sharing_rules")
            .insert({
                "name": request.name,
                "description": request.description,
                "object_type": request.object_type,
                "share_from_type": request.share_from_type,
                "share_from_id": request.share_from_id,
                "share_to_type": request.share_to_type,
                "share_to_id": request.share_to_id,
                "access_level": request.access_level
            })
            .select()
            .single()
            .execute()
        )

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating sharing rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to create sharing rule")


# =============================================================================
# 3. PUT /sharing-rules/:id - server.js:3141-3172
# =============================================================================

@router.put("/sharing-rules/{rule_id}")
async def update_sharing_rule(
    rule_id: int,
    request: UpdateSharingRuleRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Update sharing rule.
    Mirrors server.js:3141-3172
    """
    logger.info(f"[UI RBAC API] Updating sharing rule: {rule_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3148-3156
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.share_from_type is not None:
            updates["share_from_type"] = request.share_from_type
        if request.share_from_id is not None:
            updates["share_from_id"] = request.share_from_id
        if request.share_to_type is not None:
            updates["share_to_type"] = request.share_to_type
        if request.share_to_id is not None:
            updates["share_to_id"] = request.share_to_id
        if request.access_level is not None:
            updates["access_level"] = request.access_level
        if request.is_active is not None:
            updates["is_active"] = request.is_active

        # server.js:3158-3163
        response = (
            supabase.table("sharing_rules")
            .update(updates)
            .eq("id", rule_id)
            .select()
            .single()
            .execute()
        )

        return response.data

    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating sharing rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to update sharing rule")


# =============================================================================
# 4. DELETE /sharing-rules/:id - server.js:3175-3193
# =============================================================================

@router.delete("/sharing-rules/{rule_id}")
async def delete_sharing_rule(
    rule_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Delete sharing rule.
    Mirrors server.js:3175-3193
    """
    logger.info(f"[UI RBAC API] Deleting sharing rule: {rule_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3181-3184
        supabase.table("sharing_rules").delete().eq("id", rule_id).execute()
        return {"success": True}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting sharing rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete sharing rule")


# =============================================================================
# 5. GET /record-shares/:objectType/:recordId - server.js:3199-3221
# =============================================================================

@router.get("/record-shares/{object_type}/{record_id}")
async def list_record_shares(
    object_type: str,
    record_id: str,
    user: AuthUser = Depends(require_auth),
) -> list[dict[str, Any]]:
    """
    List shares for a record.
    Mirrors server.js:3199-3221
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3203-3212
        response = (
            supabase.table("record_shares")
            .select("""
                *,
                shared_with_user:shared_with_user_id(id, email, name),
                shared_with_team:shared_with_team_id(id, name, display_name),
                sharer:shared_by(id, email, name)
            """)
            .eq("object_type", object_type)
            .eq("record_id", record_id)
            .execute()
        )

        return response.data or []

    except Exception as e:
        logger.error(f"[UI RBAC API] Error listing record shares: {e}")
        raise HTTPException(status_code=500, detail="Failed to list record shares")


# =============================================================================
# 6. DELETE /record-shares/:id - server.js:3224-3259
# =============================================================================

@router.delete("/record-shares/{share_id}")
async def revoke_record_share(
    share_id: int,
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Revoke a record share.
    Mirrors server.js:3224-3259
    """
    logger.info(f"[UI RBAC API] Revoking record share: {share_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3231-3235 - Check permissions
        share_response = (
            supabase.table("record_shares")
            .select("shared_by")
            .eq("id", share_id)
            .single()
            .execute()
        )

        share = share_response.data
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # server.js:3240-3245
        is_admin = user.profile == "system_admin"
        is_owner = share["shared_by"] == user.id

        if not is_admin and not is_owner:
            raise HTTPException(status_code=403, detail="Not authorized to revoke this share")

        # server.js:3247-3250
        supabase.table("record_shares").delete().eq("id", share_id).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error revoking record share: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke record share")


# =============================================================================
# 7. PUT /record-shares/:id - server.js:3524-3569
# =============================================================================

@router.put("/record-shares/{share_id}")
async def update_record_share(
    share_id: int,
    request: UpdateRecordShareRequest,
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Update record share.
    Mirrors server.js:3524-3569
    """
    logger.info(f"[UI RBAC API] Updating record share: {share_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3532-3536 - Check permissions
        share_response = (
            supabase.table("record_shares")
            .select("shared_by")
            .eq("id", share_id)
            .single()
            .execute()
        )

        share = share_response.data
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # server.js:3541-3546
        is_admin = user.profile == "system_admin"
        is_owner = share["shared_by"] == user.id

        if not is_admin and not is_owner:
            raise HTTPException(status_code=403, detail="Not authorized to update this share")

        # server.js:3548-3554
        updates = {}
        if request.access_level is not None:
            updates["access_level"] = request.access_level
        if request.expires_at is not None:
            updates["expires_at"] = request.expires_at

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # server.js:3556-3561
        response = (
            supabase.table("record_shares")
            .update(updates)
            .eq("id", share_id)
            .select()
            .single()
            .execute()
        )

        return response.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error updating record share: {e}")
        raise HTTPException(status_code=500, detail="Failed to update record share")


# =============================================================================
# 8. POST /shares - server.js:3632-3718
# =============================================================================

@router.post("/shares", status_code=201)
async def create_share(
    request: CreateShareRequest,
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Share a record with a user or team.
    Mirrors server.js:3632-3718
    """
    # server.js:3636-3651 - Validate
    if not request.object_type or not request.record_id:
        raise HTTPException(status_code=400, detail="object_type and record_id are required")

    if not request.shared_with_user_id and not request.shared_with_team_id:
        raise HTTPException(status_code=400, detail="Either shared_with_user_id or shared_with_team_id is required")

    if request.shared_with_user_id and request.shared_with_team_id:
        raise HTTPException(status_code=400, detail="Cannot share with both user and team at the same time")

    valid_access_levels = ["read", "read_write", "full"]
    if request.access_level and request.access_level not in valid_access_levels:
        raise HTTPException(status_code=400, detail=f"access_level must be one of: {', '.join(valid_access_levels)}")

    logger.info(
        f"[UI RBAC API] Creating share: {request.object_type}/{request.record_id} -> "
        f"{request.shared_with_user_id or f'team:{request.shared_with_team_id}'}"
    )

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3657-3677 - Check if share already exists
        existing_query = (
            supabase.table("record_shares")
            .select("id")
            .eq("object_type", request.object_type)
            .eq("record_id", request.record_id)
        )

        if request.shared_with_user_id:
            existing_query = existing_query.eq("shared_with_user_id", request.shared_with_user_id)
        else:
            existing_query = existing_query.eq("shared_with_team_id", request.shared_with_team_id)

        existing_response = existing_query.execute()

        if existing_response.data and len(existing_response.data) > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Share already exists",
                    "existing_share_id": existing_response.data[0]["id"],
                    "hint": "Use PUT /api/rbac/record-shares/:id to update"
                }
            )

        # server.js:3680-3693 - Create the share
        response = (
            supabase.table("record_shares")
            .insert({
                "object_type": request.object_type,
                "record_id": request.record_id,
                "shared_with_user_id": request.shared_with_user_id,
                "shared_with_team_id": request.shared_with_team_id,
                "access_level": request.access_level or "read",
                "shared_by": user.id,
                "expires_at": request.expires_at,
                "reason": request.reason
            })
            .select()
            .single()
            .execute()
        )

        share = response.data

        # server.js:3698-3706 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "record.share",
                "action_category": "sharing",
                "resource_type": request.object_type,
                "resource_id": request.record_id,
                "target_user_id": request.shared_with_user_id,
                "new_value": {
                    "access_level": share["access_level"],
                    "shared_with_team_id": request.shared_with_team_id,
                    "expires_at": request.expires_at
                }
            }).execute()

        # server.js:3709-3711 - Clear RBAC cache
        if request.shared_with_user_id:
            invalidate_rbac_cache(request.shared_with_user_id)

        return share

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error creating share: {e}")
        raise HTTPException(status_code=500, detail="Failed to create share")


# =============================================================================
# 9. GET /shares/:objectType/:recordId - server.js:3721-3749
# =============================================================================

@router.get("/shares/{object_type}/{record_id}")
async def get_shares_for_record(
    object_type: str,
    record_id: str,
    user: AuthUser = Depends(require_auth),
) -> list[dict[str, Any]]:
    """
    Get shares for a specific record.
    Mirrors server.js:3721-3749
    """
    logger.info(f"[UI RBAC API] Getting shares for {object_type}/{record_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3727-3736
        response = (
            supabase.table("record_shares")
            .select("""
                *,
                shared_with_user:users!record_shares_shared_with_user_id_fkey(id, email, name),
                shared_with_team:teams!record_shares_shared_with_team_id_fkey(id, name, display_name),
                sharer:users!record_shares_shared_by_fkey(id, email, name)
            """)
            .eq("object_type", object_type)
            .eq("record_id", record_id)
            .execute()
        )

        # server.js:3741-3742 - Filter out expired shares
        now = datetime.utcnow()
        active_shares = []
        for s in (response.data or []):
            if not s.get("expires_at"):
                active_shares.append(s)
            else:
                try:
                    expires = datetime.fromisoformat(s["expires_at"].replace("Z", "+00:00").replace("+00:00", ""))
                    if expires > now:
                        active_shares.append(s)
                except Exception:
                    active_shares.append(s)

        return active_shares

    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting shares: {e}")
        raise HTTPException(status_code=500, detail="Failed to get shares")


# =============================================================================
# 10. GET /shares/shared-with-me - server.js:3752-3812
# =============================================================================

@router.get("/shares/shared-with-me")
async def get_shares_shared_with_me(
    object_type: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Get all shares for the current user.
    Mirrors server.js:3752-3812
    """
    offset = (page - 1) * limit
    logger.info(f"[UI RBAC API] Getting shares for user {user.id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3760-3765 - Get user's team IDs
        team_response = (
            supabase.table("team_members")
            .select("team_id")
            .eq("user_id", user.id)
            .execute()
        )

        team_ids = [tm["team_id"] for tm in (team_response.data or [])]

        # server.js:3768-3773 - Build query
        query = (
            supabase.table("record_shares")
            .select("*, sharer:users!record_shares_shared_by_fkey(id, email, name)", count="exact")
        )

        if object_type:
            query = query.eq("object_type", object_type)

        # server.js:3781-3785 - User shares OR team shares
        if team_ids:
            query = query.or_(f"shared_with_user_id.eq.{user.id},shared_with_team_id.in.({','.join(map(str, team_ids))})")
        else:
            query = query.eq("shared_with_user_id", user.id)

        # server.js:3791-3793 - Pagination
        query = query.order("shared_at", desc=True).range(offset, offset + limit - 1)

        response = query.execute()
        shares = response.data or []
        count = response.count or 0

        return {
            "shares": shares,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": count,
                "totalPages": (count + limit - 1) // limit if count > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"[UI RBAC API] Error getting user shares: {e}")
        raise HTTPException(status_code=500, detail="Failed to get shares")


# =============================================================================
# 11. DELETE /shares/:id - server.js:3815-3872
# =============================================================================

@router.delete("/shares/{share_id}")
async def delete_share(
    share_id: int,
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Delete a share.
    Mirrors server.js:3815-3872
    """
    logger.info(f"[UI RBAC API] Deleting share: {share_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:3822-3833 - Get share first
        share_response = (
            supabase.table("record_shares")
            .select("*")
            .eq("id", share_id)
            .single()
            .execute()
        )

        share = share_response.data
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # server.js:3836-3841 - Check permissions
        is_admin = user.profile == "system_admin"
        is_owner = share["shared_by"] == user.id

        if not is_admin and not is_owner:
            raise HTTPException(status_code=403, detail="Not authorized to delete this share")

        # server.js:3844-3847 - Delete the share
        supabase.table("record_shares").delete().eq("id", share_id).execute()

        # server.js:3852-3860 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "action": "record.unshare",
                "action_category": "sharing",
                "resource_type": share["object_type"],
                "resource_id": share["record_id"],
                "target_user_id": share.get("shared_with_user_id"),
                "old_value": {
                    "access_level": share["access_level"],
                    "shared_with_team_id": share.get("shared_with_team_id")
                }
            }).execute()

        # server.js:3863-3865 - Clear RBAC cache
        if share.get("shared_with_user_id"):
            invalidate_rbac_cache(share["shared_with_user_id"])

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI RBAC API] Error deleting share: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete share")


# =============================================================================
# 12. GET /check-access/:objectType/:recordId - server.js:3875-3950
# =============================================================================

@router.get("/check-access/{object_type}/{record_id}")
async def check_access(
    object_type: str,
    record_id: str,
    required_level: str | None = None,
    user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """
    Check if user has access to a specific record.
    Mirrors server.js:3875-3950
    """
    logger.info(f"[UI RBAC API] Checking access: {object_type}/{record_id} for user {user.id}")

    # server.js:3883-3885 - System admin has full access
    if user.profile == "system_admin":
        return {"has_access": True, "access_level": "full", "reason": "system_admin"}

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        access_level_rank = {"read": 1, "read_write": 2, "full": 3}
        required_rank = access_level_rank.get(required_level, 1)
        now = datetime.utcnow().isoformat()

        # server.js:3888-3893 - Get user's team IDs
        team_response = (
            supabase.table("team_members")
            .select("team_id")
            .eq("user_id", user.id)
            .execute()
        )

        team_ids = [tm["team_id"] for tm in (team_response.data or [])]

        # server.js:3896-3914 - Check for direct user share
        user_share_response = (
            supabase.table("record_shares")
            .select("access_level, expires_at")
            .eq("object_type", object_type)
            .eq("record_id", record_id)
            .eq("shared_with_user_id", user.id)
            .execute()
        )

        for share in (user_share_response.data or []):
            if not share.get("expires_at") or share["expires_at"] > now:
                has_rank = access_level_rank.get(share["access_level"], 0)
                return {
                    "has_access": has_rank >= required_rank,
                    "access_level": share["access_level"],
                    "reason": "user_share"
                }

        # server.js:3918-3941 - Check for team share
        if team_ids:
            team_share_response = (
                supabase.table("record_shares")
                .select("access_level, expires_at, shared_with_team_id")
                .eq("object_type", object_type)
                .eq("record_id", record_id)
                .in_("shared_with_team_id", team_ids)
                .order("access_level", desc=True)
                .limit(1)
                .execute()
            )

            for share in (team_share_response.data or []):
                if not share.get("expires_at") or share["expires_at"] > now:
                    has_rank = access_level_rank.get(share["access_level"], 0)
                    return {
                        "has_access": has_rank >= required_rank,
                        "access_level": share["access_level"],
                        "reason": "team_share",
                        "team_id": share["shared_with_team_id"]
                    }

        # server.js:3945 - No share found
        return {"has_access": False, "access_level": None, "reason": "no_share"}

    except Exception as e:
        logger.error(f"[UI RBAC API] Error checking access: {e}")
        raise HTTPException(status_code=500, detail="Failed to check access")
