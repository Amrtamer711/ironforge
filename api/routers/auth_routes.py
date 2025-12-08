"""
Authentication endpoints for Unified UI.
Uses integrations/auth and integrations/rbac providers.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_auth, sync_user_from_token, require_any_role
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
                # Get roles from RBAC
                from integrations.rbac import get_rbac_client
                rbac = get_rbac_client()
                roles = await rbac.get_user_roles(result.user.id)
                role_names = [r.name for r in roles]

                logger.info(f"[AUTH] Login successful for: {request.email}, roles: {role_names}")
                return {
                    "token": token,
                    "user": {
                        "id": result.user.id,
                        "name": result.user.name,
                        "email": result.user.email,
                        "roles": role_names or [result.user.metadata.get("role", "sales_person")]
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

    # Get roles from RBAC
    from integrations.rbac import get_rbac_client
    rbac = get_rbac_client()
    roles = await rbac.get_user_roles(user.id)
    role_names = [r.name for r in roles]

    logger.info(f"[AUTH] /me returning user {user.email} with roles: {role_names}")
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
    role_name: str = Field(default="user", description="Role to assign (admin, user, viewer)")
    expires_in_days: int = Field(default=7, ge=1, le=30, description="Days until token expires")


class InviteTokenResponse(BaseModel):
    """Response model for created invite token."""
    token: str
    email: str
    role_name: str
    expires_at: str
    message: str


class InviteTokenListItem(BaseModel):
    """Response model for listing invite tokens."""
    id: int
    email: str
    role_name: str
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
    role_name: str


@router.post("/invites", response_model=InviteTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_invite_token(
    invite_data: InviteTokenCreate,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Create an invite token for a new user.

    Requires: admin role

    The token is tied to a specific email address and role.
    Users must use this token along with the matching email to sign up.
    """
    from db import get_db
    from integrations.rbac import get_rbac_client
    from utils.time import get_uae_time

    db = get_db()
    rbac = get_rbac_client()

    # Validate role exists
    role = await rbac.get_role(invite_data.role_name)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {invite_data.role_name}",
        )

    # Check if email already has a pending invite
    existing = db.execute_query(
        "SELECT * FROM invite_tokens WHERE email = ? AND used_at IS NULL AND is_revoked = 0 AND expires_at > ?",
        (invite_data.email.lower(), get_uae_time().isoformat())
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pending invite already exists for {invite_data.email}",
        )

    # Generate secure token
    token = secrets.token_urlsafe(32)

    # Calculate expiry
    now = get_uae_time()
    expires_at = now + timedelta(days=invite_data.expires_in_days)

    # Store in database
    db.execute_query(
        """
        INSERT INTO invite_tokens (token, email, role_id, created_by, created_at, expires_at)
        SELECT ?, ?, r.id, ?, ?, ?
        FROM roles r WHERE r.name = ?
        """,
        (
            token,
            invite_data.email.lower(),
            user.id,
            now.isoformat(),
            expires_at.isoformat(),
            invite_data.role_name,
        )
    )

    logger.info(f"[AUTH] Invite token created for {invite_data.email} with role {invite_data.role_name} by {user.email}")

    return InviteTokenResponse(
        token=token,
        email=invite_data.email.lower(),
        role_name=invite_data.role_name,
        expires_at=expires_at.isoformat(),
        message=f"Invite token created. Share this token with {invite_data.email} to allow them to sign up.",
    )


@router.get("/invites", response_model=List[InviteTokenListItem])
async def list_invite_tokens(
    include_used: bool = False,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List all invite tokens.

    Requires: admin role
    """
    from db import get_db
    from utils.time import get_uae_time

    db = get_db()

    if include_used:
        query = """
            SELECT it.*, r.name as role_name
            FROM invite_tokens it
            JOIN roles r ON it.role_id = r.id
            ORDER BY it.created_at DESC
        """
        tokens = db.execute_query(query)
    else:
        query = """
            SELECT it.*, r.name as role_name
            FROM invite_tokens it
            JOIN roles r ON it.role_id = r.id
            WHERE it.used_at IS NULL AND it.is_revoked = 0
            ORDER BY it.created_at DESC
        """
        tokens = db.execute_query(query)

    return [
        InviteTokenListItem(
            id=t["id"],
            email=t["email"],
            role_name=t["role_name"],
            created_by=t["created_by"],
            created_at=t["created_at"],
            expires_at=t["expires_at"],
            is_used=t["used_at"] is not None,
            is_revoked=bool(t["is_revoked"]),
        )
        for t in (tokens or [])
    ]


@router.delete("/invites/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite_token(
    token_id: int,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Revoke an invite token.

    Requires: admin role
    """
    from db import get_db

    db = get_db()

    # Check token exists
    existing = db.execute_query("SELECT * FROM invite_tokens WHERE id = ?", (token_id,))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invite token {token_id} not found",
        )

    # Revoke it
    db.execute_query(
        "UPDATE invite_tokens SET is_revoked = 1 WHERE id = ?",
        (token_id,)
    )

    logger.info(f"[AUTH] Invite token {token_id} revoked by {user.email}")


@router.post("/validate-invite", response_model=ValidateInviteResponse)
async def validate_invite_token(request: ValidateInviteRequest):
    """
    Validate an invite token for signup.

    This is a PUBLIC endpoint - no authentication required.
    Called by the frontend during signup to verify the token is valid
    before creating the user in Supabase Auth.
    """
    from db import get_db
    from utils.time import get_uae_time

    logger.info(f"[AUTH] Validating invite token for email: {request.email}")

    db = get_db()

    # Find the token
    token_data = db.execute_query(
        """
        SELECT it.*, r.name as role_name
        FROM invite_tokens it
        JOIN roles r ON it.role_id = r.id
        WHERE it.token = ?
        """,
        (request.token,)
    )

    if not token_data:
        logger.warning(f"[AUTH] Invalid invite token attempted for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite token",
        )

    token_record = token_data[0]
    logger.info(f"[AUTH] Found token for email: {token_record['email']}, role: {token_record['role_name']}")

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
    expires_at = datetime.fromisoformat(token_record["expires_at"])
    if now > expires_at:
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

    # Mark token as used (it will be fully consumed when user first logs in)
    db.execute_query(
        "UPDATE invite_tokens SET used_at = ? WHERE id = ?",
        (now.isoformat(), token_record["id"])
    )

    logger.info(f"[AUTH] Invite token validated successfully for {request.email} with role {token_record['role_name']}")

    return ValidateInviteResponse(
        valid=True,
        email=token_record["email"],
        role_name=token_record["role_name"],
    )
