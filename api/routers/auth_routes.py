"""
Authentication endpoints for Unified UI.
Uses integrations/auth and integrations/rbac providers.

NOTE: Invite tokens are stored in UI Supabase (not SalesBot Supabase),
so we use a separate UI Supabase client for invite operations.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_auth, sync_user_from_token, require_any_profile
from integrations.auth import AuthUser, get_auth_client
from integrations.auth.providers.local_dev import LocalDevAuthProvider
from utils.logging import get_logger

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger("api.auth")

# UI Supabase client (for invite_tokens table in UI database)
_ui_supabase_client = None

def get_ui_supabase():
    """Get the UI Supabase client for auth/RBAC operations."""
    global _ui_supabase_client
    if _ui_supabase_client is not None:
        return _ui_supabase_client

    from app_settings import settings
    if not settings.ui_supabase_url or not settings.ui_supabase_service_key:
        logger.warning("[AUTH] UI Supabase not configured, invite tokens won't work")
        return None

    try:
        from supabase import create_client
        _ui_supabase_client = create_client(
            settings.ui_supabase_url,
            settings.ui_supabase_service_key
        )
        logger.info("[AUTH] UI Supabase client initialized")
        return _ui_supabase_client
    except Exception as e:
        logger.error(f"[AUTH] Failed to create UI Supabase client: {e}")
        return None


class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str


@router.post("/login")
async def auth_login(request: LoginRequest):
    """
    Authenticate a user.

    For local dev: Uses LocalDevAuthProvider with hardcoded users
    For production: Supabase handles login client-side, this is backup
    """
    logger.info(f"[AUTH] Login attempt for: {request.email}")
    auth = get_auth_client()

    # For local dev provider, generate token
    if auth.provider_name == "local_dev":
        provider = auth.provider
        if isinstance(provider, LocalDevAuthProvider):
            # Generate dev token
            token = provider.generate_dev_token(request.email)
            result = await auth.verify_token(token)

            if result.success and result.user:
                # Get profile from RBAC
                from integrations.rbac import get_rbac_client
                rbac = get_rbac_client()
                profile = await rbac.get_user_profile(result.user.id)
                profile_name = profile.name if profile else result.user.metadata.get("role", "sales_user")

                logger.info(f"[AUTH] Login successful for: {request.email}, profile: {profile_name}")
                return {
                    "token": token,
                    "user": {
                        "id": result.user.id,
                        "name": result.user.name,
                        "email": result.user.email,
                        "profile": profile_name
                    }
                }

    logger.warning(f"[AUTH] Login failed for: {request.email}")
    raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/logout")
async def auth_logout():
    """Logout endpoint."""
    logger.info("[AUTH] User logged out")
    return {"success": True}


@router.get("/me")
async def auth_me(user: Optional[AuthUser] = Depends(get_current_user)):
    """Get current user info from token."""
    logger.info(f"[AUTH] /me request, user: {user.email if user else 'None'}")
    if not user:
        logger.warning("[AUTH] /me called without authentication")
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get profile from RBAC
    from integrations.rbac import get_rbac_client
    rbac = get_rbac_client()
    profile = await rbac.get_user_profile(user.id)
    profile_name = profile.name if profile else user.metadata.get("role", "sales_user")

    logger.info(f"[AUTH] /me returning user {user.email} with profile: {profile_name}")
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "profile": profile_name
    }


@router.post("/sync")
async def auth_sync(user: AuthUser = Depends(require_auth)):
    """
    Sync authenticated user to application database.

    Called by frontend after successful Supabase login to ensure
    user exists in our database with current profile data.
    """
    logger.info(f"[AUTH] Syncing user to database: {user.email}")
    result = await sync_user_from_token(user)
    logger.info(f"[AUTH] User sync completed for: {user.email}")
    return result


# =============================================================================
# INVITE TOKEN ENDPOINTS
# =============================================================================


class InviteTokenCreate(BaseModel):
    """Request model for creating an invite token."""
    email: str = Field(..., min_length=5, description="Email address for the invite")
    profile_name: str = Field(default="sales_user", description="Profile to assign (system_admin, sales_manager, sales_user)")
    expires_in_days: int = Field(default=7, ge=1, le=30, description="Days until token expires")


class InviteTokenResponse(BaseModel):
    """Response model for created invite token."""
    token: str
    email: str
    profile_name: str
    expires_at: str
    message: str


class InviteTokenListItem(BaseModel):
    """Response model for listing invite tokens."""
    id: int
    email: str
    profile_name: str
    created_by: str
    created_at: str
    expires_at: str
    is_used: bool
    is_revoked: bool


class ValidateInviteRequest(BaseModel):
    """Request model for validating an invite token."""
    token: str
    email: str


class ValidateInviteResponse(BaseModel):
    """Response model for validated invite token."""
    valid: bool
    email: str
    profile_name: str


@router.post("/invites", response_model=InviteTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_invite_token(
    invite_data: InviteTokenCreate,
    user: AuthUser = Depends(require_any_profile("system_admin")),
):
    """
    Create an invite token for a new user.

    Requires: system_admin profile

    The token is tied to a specific email address and profile.
    Users must use this token along with the matching email to sign up.
    """
    from integrations.rbac import get_rbac_client
    from utils.time import get_uae_time

    ui_client = get_ui_supabase()
    if not ui_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UI Supabase not configured",
        )

    rbac = get_rbac_client()

    # Validate profile exists
    profile = await rbac.get_profile(invite_data.profile_name)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile: {invite_data.profile_name}",
        )

    now = get_uae_time()

    # Check if email already has a pending invite
    existing = ui_client.table("invite_tokens").select("*").eq(
        "email", invite_data.email.lower()
    ).is_("used_at", "null").eq("is_revoked", False).gt(
        "expires_at", now.isoformat()
    ).execute()

    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pending invite already exists for {invite_data.email}",
        )

    # Generate secure token
    token = secrets.token_urlsafe(32)

    # Calculate expiry
    expires_at = now + timedelta(days=invite_data.expires_in_days)

    # Store in UI Supabase
    ui_client.table("invite_tokens").insert({
        "token": token,
        "email": invite_data.email.lower(),
        "profile_name": invite_data.profile_name,
        "created_by": user.id,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }).execute()

    logger.info(f"[AUTH] Invite token created for {invite_data.email} with profile {invite_data.profile_name} by {user.email}")

    return InviteTokenResponse(
        token=token,
        email=invite_data.email.lower(),
        profile_name=invite_data.profile_name,
        expires_at=expires_at.isoformat(),
        message=f"Invite token created. Share this token with {invite_data.email} to allow them to sign up.",
    )


@router.get("/invites", response_model=List[InviteTokenListItem])
async def list_invite_tokens(
    include_used: bool = False,
    user: AuthUser = Depends(require_any_profile("system_admin")),
):
    """
    List all invite tokens.

    Requires: system_admin profile
    """
    ui_client = get_ui_supabase()
    if not ui_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UI Supabase not configured",
        )

    if include_used:
        result = ui_client.table("invite_tokens").select("*").order("created_at", desc=True).execute()
    else:
        result = ui_client.table("invite_tokens").select("*").is_(
            "used_at", "null"
        ).eq("is_revoked", False).order("created_at", desc=True).execute()

    tokens = result.data or []

    return [
        InviteTokenListItem(
            id=t["id"],
            email=t["email"],
            profile_name=t["profile_name"],
            created_by=t["created_by"],
            created_at=t["created_at"],
            expires_at=t["expires_at"],
            is_used=t["used_at"] is not None,
            is_revoked=bool(t["is_revoked"]),
        )
        for t in tokens
    ]


@router.delete("/invites/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite_token(
    token_id: int,
    user: AuthUser = Depends(require_any_profile("system_admin")),
):
    """
    Revoke an invite token.

    Requires: system_admin profile
    """
    ui_client = get_ui_supabase()
    if not ui_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UI Supabase not configured",
        )

    # Check token exists
    existing = ui_client.table("invite_tokens").select("*").eq("id", token_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invite token {token_id} not found",
        )

    # Revoke it
    ui_client.table("invite_tokens").update({"is_revoked": True}).eq("id", token_id).execute()

    logger.info(f"[AUTH] Invite token {token_id} revoked by {user.email}")


@router.post("/validate-invite", response_model=ValidateInviteResponse)
async def validate_invite_token(request: ValidateInviteRequest):
    """
    Validate an invite token for signup.

    This is a PUBLIC endpoint - no authentication required.
    Called by the frontend during signup to verify the token is valid
    before creating the user in Supabase Auth.
    """
    from utils.time import get_uae_time

    ui_client = get_ui_supabase()
    if not ui_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UI Supabase not configured",
        )

    logger.info(f"[AUTH] Validating invite token for email: {request.email}")

    # Find the token
    result = ui_client.table("invite_tokens").select("*").eq("token", request.token).execute()

    if not result.data:
        logger.warning(f"[AUTH] Invalid invite token attempted for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invite token",
        )

    token_record = result.data[0]
    logger.info(f"[AUTH] Found token for email: {token_record['email']}, profile: {token_record['profile_name']}")

    # Check if already used
    if token_record["used_at"]:
        logger.warning(f"[AUTH] Token already used for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite token has already been used",
        )

    # Check if revoked
    if token_record["is_revoked"]:
        logger.warning(f"[AUTH] Token revoked for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite token has been revoked",
        )

    # Check expiry
    now = get_uae_time()
    expires_at_str = token_record["expires_at"]
    # Handle both ISO format with and without timezone
    if expires_at_str.endswith("Z"):
        expires_at_str = expires_at_str[:-1] + "+00:00"
    expires_at = datetime.fromisoformat(expires_at_str.replace("+00:00", ""))
    if now.replace(tzinfo=None) > expires_at:
        logger.warning(f"[AUTH] Token expired for: {request.email}, expired at: {expires_at}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite token has expired",
        )

    # Check email matches
    if request.email.lower() != token_record["email"].lower():
        logger.warning(f"[AUTH] Email mismatch: requested {request.email}, token for {token_record['email']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email does not match the invite token",
        )

    # Mark token as used
    ui_client.table("invite_tokens").update({
        "used_at": now.isoformat()
    }).eq("id", token_record["id"]).execute()

    logger.info(f"[AUTH] Invite token validated successfully for {request.email} with profile {token_record['profile_name']}")

    return ValidateInviteResponse(
        valid=True,
        email=token_record["email"],
        profile_name=token_record["profile_name"],
    )
