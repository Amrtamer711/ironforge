"""
Authentication endpoints for Unified UI.
Uses integrations/auth and integrations/rbac providers.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user, require_auth, sync_user_from_token
from integrations.auth import AuthUser, get_auth_client
from integrations.auth.providers.local_dev import LocalDevAuthProvider

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    auth = get_auth_client()

    # For local dev provider, generate token
    if auth.provider_name == "local_dev":
        provider = auth.provider
        if isinstance(provider, LocalDevAuthProvider):
            # Generate dev token
            token = provider.generate_dev_token(request.email)
            result = await auth.verify_token(token)

            if result.success and result.user:
                # Get roles from RBAC
                from integrations.rbac import get_rbac_client
                rbac = get_rbac_client()
                roles = await rbac.get_user_roles(result.user.id)
                role_names = [r.name for r in roles]

                return {
                    "token": token,
                    "user": {
                        "id": result.user.id,
                        "name": result.user.name,
                        "email": result.user.email,
                        "roles": role_names or [result.user.metadata.get("role", "sales_person")]
                    }
                }

    raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/logout")
async def auth_logout():
    """Logout endpoint."""
    return {"success": True}


@router.get("/me")
async def auth_me(user: Optional[AuthUser] = Depends(get_current_user)):
    """Get current user info from token."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get roles from RBAC
    from integrations.rbac import get_rbac_client
    rbac = get_rbac_client()
    roles = await rbac.get_user_roles(user.id)
    role_names = [r.name for r in roles]

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "roles": role_names or [user.metadata.get("role", "sales_person")]
    }


@router.post("/sync")
async def auth_sync(user: AuthUser = Depends(require_auth)):
    """
    Sync authenticated user to application database.

    Called by frontend after successful Supabase login to ensure
    user exists in our database with current profile data.
    """
    return await sync_user_from_token(user)
