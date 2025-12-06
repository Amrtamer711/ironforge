"""
FastAPI Authentication & Authorization Dependencies.

Provides FastAPI dependencies for protecting endpoints using the
integrations/auth and integrations/rbac providers.

Usage:
    from api.auth import get_current_user, require_auth, require_permission

    # Require authentication
    @app.get("/api/protected")
    async def protected_route(user: AuthUser = Depends(require_auth)):
        return {"user_id": user.id}

    # Require specific permission
    @app.get("/api/admin")
    async def admin_route(user: AuthUser = Depends(require_permission("users:manage"))):
        return {"user_id": user.id}

    # Require specific role
    @app.get("/api/hos-only")
    async def hos_route(user: AuthUser = Depends(require_role("hos"))):
        return {"user_id": user.id}

    # Optional auth (user may be None)
    @app.get("/api/public")
    async def public_route(user: Optional[AuthUser] = Depends(get_current_user)):
        if user:
            return {"authenticated": True, "user_id": user.id}
        return {"authenticated": False}
"""

import logging
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from integrations.auth import (
    AuthUser,
    AuthResult,
    AuthStatus,
    get_auth_client,
)
from integrations.rbac import (
    get_rbac_client,
    RBACContext,
)

logger = logging.getLogger("proposal-bot")

# HTTP Bearer scheme for extracting tokens
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[str]:
    """
    Extract JWT token from request.

    Checks in order:
    1. Authorization: Bearer <token> header
    2. X-Request-User-ID header (from proxy for tracing)

    Returns:
        Token string or None
    """
    # Primary: Bearer token from Authorization header
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fallback: Check raw Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> Optional[AuthUser]:
    """
    Get the current authenticated user (if any).

    This dependency does NOT raise an exception if unauthenticated.
    Use require_auth for protected endpoints.

    Returns:
        AuthUser if authenticated, None otherwise
    """
    if not token:
        return None

    try:
        auth = get_auth_client()
        result = await auth.verify_token(token)

        if result.success and result.user:
            # Optionally sync user to database on each request
            # await auth.sync_user_to_db(result.user)
            return result.user

        return None

    except Exception as e:
        logger.warning(f"[AUTH] Error verifying token: {e}")
        return None


async def require_auth(
    user: Optional[AuthUser] = Depends(get_current_user),
) -> AuthUser:
    """
    Require authentication for an endpoint.

    Raises HTTPException 401 if not authenticated.

    Usage:
        @app.get("/api/protected")
        async def protected(user: AuthUser = Depends(require_auth)):
            return {"user": user.email}
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(permission: str) -> Callable:
    """
    Factory for requiring a specific permission.

    Usage:
        @app.get("/api/admin")
        async def admin(user: AuthUser = Depends(require_permission("users:manage"))):
            return {"user": user.email}
    """
    async def _require_permission(
        request: Request,
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        rbac = get_rbac_client()

        # Build context for ownership checks
        context = None
        if request:
            # Extract resource info from path if available
            path_params = getattr(request, "path_params", {})
            resource_id = path_params.get("id") or path_params.get("resource_id")
            if resource_id:
                context = RBACContext(
                    user_id=user.id,
                    resource_id=resource_id,
                )

        has_perm = await rbac.has_permission(user.id, permission, context)

        if not has_perm:
            logger.warning(
                f"[AUTH] User {user.id} ({user.email}) lacks permission: {permission}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )

        return user

    return _require_permission


def require_role(role_name: str) -> Callable:
    """
    Factory for requiring a specific role.

    Usage:
        @app.get("/api/hos-only")
        async def hos_only(user: AuthUser = Depends(require_role("hos"))):
            return {"user": user.email}
    """
    async def _require_role(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        rbac = get_rbac_client()
        has_role = await rbac.has_role(user.id, role_name)

        if not has_role:
            logger.warning(
                f"[AUTH] User {user.id} ({user.email}) lacks role: {role_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role_name}",
            )

        return user

    return _require_role


def require_any_role(*role_names: str) -> Callable:
    """
    Factory for requiring any of the specified roles.

    Usage:
        @app.get("/api/management")
        async def management(user: AuthUser = Depends(require_any_role("admin", "hos"))):
            return {"user": user.email}
    """
    async def _require_any_role(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        rbac = get_rbac_client()

        for role_name in role_names:
            if await rbac.has_role(user.id, role_name):
                return user

        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) lacks roles: {role_names}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these roles required: {', '.join(role_names)}",
        )

    return _require_any_role


# =============================================================================
# AUTH SYNC ENDPOINT
# =============================================================================


async def sync_user_from_token(
    user: AuthUser = Depends(require_auth),
) -> dict:
    """
    Sync authenticated user to the application database.

    Called by frontend after successful Supabase login to ensure
    user exists in our database with current profile data.
    """
    try:
        auth = get_auth_client()
        success = await auth.sync_user_to_db(user)

        return {
            "success": success,
            "user": user.to_dict(),
        }

    except Exception as e:
        logger.error(f"[AUTH] Sync user failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync user",
        )
