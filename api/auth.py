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

    # Require specific permission (format: module:resource:action)
    @app.get("/api/admin")
    async def admin_route(user: AuthUser = Depends(require_permission("core:users:manage"))):
        return {"user_id": user.id}

    # Require specific profile
    @app.get("/api/admin-only")
    async def admin_route(user: AuthUser = Depends(require_profile("system_admin"))):
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
    print(f"[AUTH DEBUG] get_current_user called, has_token={bool(token)}")

    if not token:
        print("[AUTH DEBUG] No token provided")
        return None

    try:
        auth = get_auth_client()
        print(f"[AUTH DEBUG] Auth client provider: {auth.provider_name}")

        result = await auth.verify_token(token)
        print(f"[AUTH DEBUG] verify_token result: success={result.success}, status={result.status}, error={result.error}")

        if result.success and result.user:
            print(f"[AUTH DEBUG] User authenticated: {result.user.email}")
            # Optionally sync user to database on each request
            # await auth.sync_user_to_db(result.user)
            return result.user

        print(f"[AUTH DEBUG] Auth failed: {result.error}")
        return None

    except Exception as e:
        print(f"[AUTH DEBUG] Exception in verify_token: {type(e).__name__}: {e}")
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

    Permission format: {module}:{resource}:{action}
    e.g., "core:users:manage", "sales:proposals:create"

    Usage:
        @app.get("/api/admin")
        async def admin(user: AuthUser = Depends(require_permission("core:users:manage"))):
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


def require_profile(profile_name: str) -> Callable:
    """
    Factory for requiring a specific profile.

    Usage:
        @app.get("/api/admin-only")
        async def admin_only(user: AuthUser = Depends(require_profile("system_admin"))):
            return {"user": user.email}
    """
    async def _require_profile(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        rbac = get_rbac_client()
        profile = await rbac.get_user_profile(user.id)

        if not profile or profile.name != profile_name:
            logger.warning(
                f"[AUTH] User {user.id} ({user.email}) lacks profile: {profile_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Profile required: {profile_name}",
            )

        return user

    return _require_profile


def require_any_profile(*profile_names: str) -> Callable:
    """
    Factory for requiring any of the specified profiles.

    Usage:
        @app.get("/api/management")
        async def management(user: AuthUser = Depends(require_any_profile("system_admin", "sales_manager"))):
            return {"user": user.email}
    """
    async def _require_any_profile(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        rbac = get_rbac_client()
        profile = await rbac.get_user_profile(user.id)

        if profile and profile.name in profile_names:
            return user

        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) lacks profiles: {profile_names}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these profiles required: {', '.join(profile_names)}",
        )

    return _require_any_profile


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
