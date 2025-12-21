"""
Auth router for unified-ui.

[VERIFIED] Mirrors server.js lines 862-1534:
- Invite token management (lines 872-1351)
- Session endpoints (lines 1353-1497)
- Force logout (lines 1499-1534)

12 endpoints total:
1. POST /api/base/auth/invites - Create invite token (admin)
2. GET /api/base/auth/invites - List invite tokens (admin)
3. DELETE /api/base/auth/invites/{tokenId} - Revoke invite (admin)
4. DELETE /api/base/auth/users/{userId} - Delete auth user (admin)
5. DELETE /api/base/auth/users-by-email/{email} - Delete by email (admin)
6. POST /api/base/auth/resend-confirmation - Resend email (admin)
7. POST /api/base/auth/validate-invite - Validate invite (public)
8. POST /api/base/auth/consume-invite - Consume invite (public)
9. GET /api/base/auth/session - Check session (public)
10. GET /api/base/auth/me - Get current user (auth required)
11. POST /api/base/auth/logout - Logout (auth required)
12. POST /api/base/auth/force-logout/{userId} - Force logout (admin)
"""

import contextlib
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from backend.middleware.auth import AuthUser, require_auth, require_profile
from backend.services.rbac_service import invalidate_rbac_cache
from backend.services.supabase_client import get_supabase
from crm_security import rate_limit

logger = logging.getLogger("unified-ui")

router = APIRouter(prefix="/api/base/auth", tags=["auth"])


# =============================================================================
# EMAIL VALIDATION - server.js:863-870
# =============================================================================

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

VALID_PROFILES = ["system_admin", "sales_manager", "sales_user", "coordinator", "finance", "viewer"]


def is_valid_email(email: str) -> bool:
    """Validate email format. Mirrors server.js:866-870"""
    if not email or not isinstance(email, str):
        return False
    if len(email) < 5 or len(email) > 254:
        return False
    return EMAIL_REGEX.match(email) is not None


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateInviteRequest(BaseModel):
    email: EmailStr
    profile_name: str = "sales_user"
    expires_in_days: int = Field(default=7, ge=1, le=30)
    send_email: bool = True


class ValidateInviteRequest(BaseModel):
    token: str
    email: EmailStr


class ConsumeInviteRequest(BaseModel):
    token: str
    email: EmailStr
    user_id: str | None = None
    name: str | None = None


class ResendConfirmationRequest(BaseModel):
    email: EmailStr


# =============================================================================
# INVITE TOKEN ENDPOINTS - server.js:872-1351
# =============================================================================

@router.post("/invites", dependencies=[Depends(rate_limit(20))])
async def create_invite(
    request: CreateInviteRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Create invite token.
    Mirrors server.js:872-978
    """
    logger.info("[UI] Create invite request")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    email = request.email.lower()

    # server.js:878-880
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Valid email address is required")

    # server.js:887-891
    if request.profile_name not in VALID_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid profile. Valid profiles: {', '.join(VALID_PROFILES)}"
        )

    try:
        now = datetime.utcnow()

        # server.js:896-907 - Check for existing pending invite
        existing_response = (
            supabase.table("invite_tokens")
            .select("*")
            .eq("email", email)
            .is_("used_at", "null")
            .eq("is_revoked", False)
            .gt("expires_at", now.isoformat())
            .execute()
        )

        if existing_response.data and len(existing_response.data) > 0:
            raise HTTPException(
                status_code=409,
                detail=f"A pending invite already exists for {email}"
            )

        # server.js:909-910 - Generate secure token
        token = secrets.token_urlsafe(32)

        # server.js:912-913 - Calculate expiry
        expires_at = now + timedelta(days=request.expires_in_days)

        # server.js:915-930 - Store invite
        insert_response = supabase.table("invite_tokens").insert({
            "token": token,
            "email": email,
            "profile_name": request.profile_name,
            "created_by": user.id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }).execute()

        if not insert_response.data:
            logger.error("[UI] Failed to create invite")
            raise HTTPException(status_code=500, detail="Failed to create invite")

        logger.info(f"[UI] Invite token created for {email} with profile {request.profile_name} by {user.email}")

        # server.js:934-955 - Send email (placeholder - would need email service)
        email_sent = False
        email_error = None

        if request.send_email:
            # TODO: Implement email sending
            logger.info(f"[UI] Email sending not implemented - invite created for {email}")
            email_error = "Email service not configured"

        # server.js:957-973 - Return response

        return {
            "token": token,
            "email": email,
            "profile_name": request.profile_name,
            "expires_at": expires_at.isoformat(),
            "email_sent": email_sent,
            "email_error": email_error,
            "email_requested": request.send_email,
            "warning": "Invite created but email delivery not configured. Share the invite link manually." if (request.send_email and not email_sent) else None,
            "message": f"Invite token created. Share this token with {email} to allow them to sign up.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error creating invite: {e}")
        raise HTTPException(status_code=500, detail="Failed to create invite")


@router.get("/invites", dependencies=[Depends(rate_limit(30))])
async def list_invites(
    include_used: bool = False,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> list[dict[str, Any]]:
    """
    List invite tokens.
    Mirrors server.js:980-1020
    """
    logger.info("[UI] List invites request")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        query = (
            supabase.table("invite_tokens")
            .select("*")
            .order("created_at", desc=True)
        )

        if not include_used:
            query = query.is_("used_at", "null").eq("is_revoked", False)

        response = query.execute()

        # server.js:1003-1013 - Format response
        return [
            {
                "id": t.get("id"),
                "email": t.get("email"),
                "profile_name": t.get("profile_name"),
                "token": t.get("token"),
                "created_by": t.get("created_by"),
                "created_at": t.get("created_at"),
                "expires_at": t.get("expires_at"),
                "is_used": t.get("used_at") is not None,
                "is_revoked": bool(t.get("is_revoked")),
            }
            for t in (response.data or [])
        ]

    except Exception as e:
        logger.error(f"[UI] Error listing invites: {e}")
        raise HTTPException(status_code=500, detail="Failed to list invites")


@router.delete("/invites/{token_id}", dependencies=[Depends(rate_limit(20))])
async def revoke_invite(
    token_id: int,
    user: AuthUser = Depends(require_profile("system_admin")),
):
    """
    Revoke invite token.
    Mirrors server.js:1022-1059
    """
    logger.info(f"[UI] Revoke invite request for ID: {token_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1032-1040 - Check token exists
        existing = supabase.table("invite_tokens").select("*").eq("id", token_id).execute()

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail=f"Invite token {token_id} not found")

        # server.js:1042-1046 - Revoke it
        supabase.table("invite_tokens").update({"is_revoked": True}).eq("id", token_id).execute()

        logger.info(f"[UI] Invite token {token_id} revoked by {user.email}")
        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error revoking invite: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke invite")


@router.delete("/users/{user_id}", dependencies=[Depends(rate_limit(10))])
async def delete_auth_user(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Delete a user from auth.users.
    Mirrors server.js:1061-1094
    """
    logger.info(f"[UI] Delete auth user request for: {user_id}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # server.js:1071-1074
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    try:
        # server.js:1077-1082 - Delete from auth.users
        supabase.auth.admin.delete_user(user_id)

        # server.js:1085-1086 - Also delete from users table
        supabase.table("users").delete().eq("id", user_id).execute()

        logger.info(f"[UI] Auth user {user_id} deleted by {user.email}")
        return {"success": True, "message": f"User {user_id} deleted from auth.users"}

    except Exception as e:
        logger.error(f"[UI] Error deleting auth user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users-by-email/{email}", dependencies=[Depends(rate_limit(10))])
async def delete_auth_user_by_email(
    email: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Delete a user by email from auth.users.
    Mirrors server.js:1096-1142
    """
    decoded_email = unquote(email)
    logger.info(f"[UI] Delete auth user by email request for: {decoded_email}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # server.js:1106-1109
    if decoded_email.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    try:
        # server.js:1112-1123 - Find user in auth.users
        users_response = supabase.auth.admin.list_users()
        target_user = None

        for u in users_response:
            if hasattr(u, "email") and u.email and u.email.lower() == decoded_email.lower():
                target_user = u
                break

        if not target_user:
            raise HTTPException(status_code=404, detail=f"No user found with email: {decoded_email}")

        # server.js:1125-1131 - Delete the user
        supabase.auth.admin.delete_user(target_user.id)

        # server.js:1133-1134 - Also delete from users table
        supabase.table("users").delete().eq("id", target_user.id).execute()

        logger.info(f"[UI] Auth user {decoded_email} ({target_user.id}) deleted by {user.email}")
        return {
            "success": True,
            "message": f"User {decoded_email} deleted from auth.users",
            "userId": target_user.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error deleting auth user by email: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user")


@router.post("/resend-confirmation", dependencies=[Depends(rate_limit(5))])
async def resend_confirmation(
    request: ResendConfirmationRequest,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Resend confirmation email for a user.
    Mirrors server.js:1144-1179
    """
    email = request.email.lower()
    logger.info(f"[UI] Resend confirmation request for: {email}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1155-1159
        supabase.auth.resend(type="signup", email=email)

        logger.info(f"[UI] Confirmation email resent to {email}")
        return {"success": True, "message": f"Confirmation email resent to {email}"}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[UI] Failed to resend confirmation: {error_msg}")

        if "already confirmed" in error_msg.lower():
            raise HTTPException(status_code=400, detail="User has already confirmed their email")
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="No pending signup found for this email")

        raise HTTPException(status_code=500, detail=error_msg)


# =============================================================================
# PUBLIC INVITE ENDPOINTS - server.js:1181-1351
# =============================================================================

@router.post("/validate-invite", dependencies=[Depends(rate_limit(5))])
async def validate_invite(request: ValidateInviteRequest) -> dict[str, Any]:
    """
    Validate invite token (PUBLIC).
    Mirrors server.js:1181-1251
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    email = request.email.lower()

    try:
        # server.js:1192-1202
        response = supabase.table("invite_tokens").select("*").eq("token", request.token).execute()

        if not response.data or len(response.data) == 0:
            logger.warning(f"[UI] Invalid invite token attempted for: {email}")
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")

        token_record = response.data[0]

        # server.js:1206-1211 - Check if already used
        if token_record.get("used_at"):
            logger.warning(f"[UI] Token already used for: {email}")
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")

        # server.js:1213-1218 - Check if revoked
        if token_record.get("is_revoked"):
            logger.warning(f"[UI] Token revoked for: {email}")
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")

        # server.js:1220-1227 - Check expiry
        expires_at = datetime.fromisoformat(token_record["expires_at"].replace("Z", "+00:00"))
        if datetime.utcnow() > expires_at.replace(tzinfo=None):
            logger.warning(f"[UI] Token expired for: {email}, expired at: {expires_at}")
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")

        # server.js:1229-1234 - Check email matches
        if email != token_record["email"].lower():
            logger.warning(f"[UI] Email mismatch: requested {email}, token for {token_record['email']}")
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")

        logger.info(f"[UI] Invite token validated successfully for {email} with profile {token_record['profile_name']}")

        return {
            "valid": True,
            "email": token_record["email"],
            "profile_name": token_record["profile_name"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error validating invite: {e}")
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")


@router.post("/consume-invite", dependencies=[Depends(rate_limit(5))])
async def consume_invite(request: ConsumeInviteRequest) -> dict[str, Any]:
    """
    Consume invite token after successful signup.
    Mirrors server.js:1253-1351
    """
    email = request.email.lower()
    logger.info(f"[UI] Consuming invite token for email: {email}, user_id: {request.user_id or 'not provided'}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        now = datetime.utcnow()

        # server.js:1267-1277
        response = (
            supabase.table("invite_tokens")
            .select("*")
            .eq("token", request.token)
            .eq("email", email)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            logger.warning(f"[UI] Token not found for consume: {email}")
            raise HTTPException(status_code=400, detail="Token not found")

        token_record = response.data[0]

        # server.js:1281-1285 - If already used, return success
        if token_record.get("used_at"):
            logger.info(f"[UI] Token already consumed for: {email}")
            return {"success": True, "already_used": True}

        # server.js:1287-1296 - Mark token as used
        supabase.table("invite_tokens").update({
            "used_at": now.isoformat(),
            "used_by_user_id": request.user_id,
        }).eq("id", token_record["id"]).execute()

        # server.js:1298-1328 - Create user in users table with profile
        if request.user_id:
            profile_response = (
                supabase.table("profiles")
                .select("id")
                .eq("name", token_record["profile_name"])
                .single()
                .execute()
            )

            if profile_response.data:
                supabase.table("users").upsert({
                    "id": request.user_id,
                    "email": email,
                    "name": request.name or email.split("@")[0],
                    "profile_id": profile_response.data["id"],
                    "created_at": now.isoformat(),
                }, on_conflict="id").execute()

                logger.info(f"[UI] Created user {email} with profile {token_record['profile_name']}")
            else:
                logger.error(f"[UI] Profile not found: {token_record['profile_name']}")
        else:
            logger.warning(f"[UI] No user_id provided for {email} - user will need manual profile assignment")

        logger.info(f"[UI] Invite token consumed for {email}")
        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error consuming invite: {e}")
        raise HTTPException(status_code=500, detail="Failed to consume token")


# =============================================================================
# SESSION ENDPOINTS - server.js:1353-1497
# =============================================================================

@router.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    """
    Verify session endpoint.
    Mirrors server.js:1358-1394
    """
    logger.debug("[UI] Session check requested")

    supabase = get_supabase()
    if not supabase:
        logger.error("[UI] Session check failed: Supabase not configured")
        raise HTTPException(status_code=500, detail="Supabase not configured")

    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.debug("[UI] Session check: No token provided")
        return {"authenticated": False}

    token = auth_header[7:]

    try:
        response = supabase.auth.get_user(token)
        user = response.user

        if not user:
            logger.debug("[UI] Session check: Invalid token")
            return {"authenticated": False}

        logger.debug(f"[UI] Session check: Valid session for {user.email}")
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
            }
        }

    except Exception as e:
        logger.error(f"[UI] Session check error: {e}")
        return {"authenticated": False}


@router.get("/me")
async def get_me(user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    """
    Get current user's profile and permissions.
    Mirrors server.js:1396-1454
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1400-1404
        response = (
            supabase.table("users")
            .select("id, email, name, profile_id, is_active, profiles(id, name, display_name)")
            .eq("id", user.id)
            .single()
            .execute()
        )

        user_data = response.data

        # server.js:1406-1413
        if not user_data:
            logger.warning(f"[UI] User {user.email} not found in users table - rejecting")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Account not found",
                    "code": "USER_NOT_FOUND",
                    "requiresLogout": True
                }
            )

        # server.js:1415-1437 - Check if user is inactive
        if user_data.get("is_active") is False:
            is_pending_sso = (
                user_data.get("id", "").startswith("pending-") or
                not user_data.get("profile_id") or
                user_data.get("profiles", {}).get("name") == "viewer"
            )

            if is_pending_sso:
                logger.warning(f"[UI] User {user.email} is pending admin approval")
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "Your account is pending administrator approval. Please contact your administrator.",
                        "code": "USER_PENDING_APPROVAL",
                        "requiresLogout": True
                    }
                )
            else:
                logger.warning(f"[UI] User {user.email} has been deactivated")
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "Your account has been deactivated. Please contact your administrator.",
                        "code": "USER_DEACTIVATED",
                        "requiresLogout": True
                    }
                )

        # server.js:1439-1440 - Clear RBAC cache
        invalidate_rbac_cache(user.id)

        # Fetch permissions from profile
        permissions: list[str] = []
        profile_id = user_data.get("profiles", {}).get("id")
        if profile_id:
            perms_response = (
                supabase.table("profile_permissions")
                .select("permission")
                .eq("profile_id", profile_id)
                .execute()
            )
            if perms_response.data:
                permissions = [p["permission"] for p in perms_response.data]

        logger.info(f"[UI] User profile fetched: {user_data['email']} -> {user_data.get('profiles', {}).get('name')} with {len(permissions)} permissions")

        return {
            "id": user_data["id"],
            "email": user_data["email"],
            "name": user_data.get("name"),
            "profile_name": user_data.get("profiles", {}).get("name"),
            "profile_display_name": user_data.get("profiles", {}).get("display_name"),
            "permissions": permissions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UI] Error fetching user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile")


@router.post("/logout")
async def logout(user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    """
    Logout endpoint.
    Mirrors server.js:1459-1497
    """
    logger.info(f"[UI AUTH] Logout requested for user: {user.email}")

    supabase = get_supabase()

    try:
        # server.js:1466-1467 - Clear RBAC cache
        invalidate_rbac_cache(user.id)

        # server.js:1469-1475 - Sign out from Supabase
        if supabase:
            try:
                supabase.auth.admin.sign_out(user.id)
            except Exception as e:
                logger.warning(f"[UI AUTH] Supabase signOut warning: {e}")

            # server.js:1477-1485 - Audit log
            try:
                supabase.table("audit_log").insert({
                    "user_id": user.id,
                    "user_email": user.email,
                    "action": "auth.logout",
                    "action_category": "auth",
                    "resource_type": "session",
                    "success": True
                }).execute()
            except Exception:
                pass  # Don't fail logout for audit log issues

        logger.info(f"[UI AUTH] User {user.email} logged out successfully")
        return {"success": True, "message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"[UI AUTH] Logout error: {e}")
        # Still return success - user wants to log out
        invalidate_rbac_cache(user.id)
        return {"success": True, "message": "Logged out (with warnings)"}


@router.post("/force-logout/{user_id}")
async def force_logout(
    user_id: str,
    user: AuthUser = Depends(require_profile("system_admin")),
) -> dict[str, Any]:
    """
    Force logout a user (admin only).
    Mirrors server.js:1499-1534
    """
    logger.info(f"[UI AUTH] Force logout requested for user: {user_id} by admin: {user.email}")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:1506-1507 - Clear RBAC cache
        invalidate_rbac_cache(user_id)

        # server.js:1509-1514 - Sign out from Supabase
        try:
            supabase.auth.admin.sign_out(user_id)
        except Exception as e:
            logger.warning(f"[UI AUTH] Supabase force signOut warning: {e}")

        # server.js:1516-1525 - Audit log
        with contextlib.suppress(Exception):
            supabase.table("audit_log").insert({
                "user_id": user.id,
                "user_email": user.email,
                "action": "auth.force_logout",
                "action_category": "admin",
                "resource_type": "session",
                "target_user_id": user_id,
                "success": True
            }).execute()

        logger.info(f"[UI AUTH] User {user_id} force logged out by {user.email}")
        return {"success": True}

    except Exception as e:
        logger.error(f"[UI AUTH] Force logout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to force logout user")
