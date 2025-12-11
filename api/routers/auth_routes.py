"""
Authentication endpoints for proposal-bot (Sales Module).

NOTE: This file only handles auth endpoints needed by the sales module.
Invite token management is handled by unified-ui (Node.js service).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user, require_auth
from integrations.auth import AuthUser, get_auth_client
from integrations.auth.providers.local_dev import LocalDevAuthProvider
from utils.logging import get_logger

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger("api.auth")


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


# NOTE: User sync is now handled by unified-ui during signup/login.
# The sales-api no longer manages users directly - it reads user context
# from trusted proxy headers set by unified-ui.
