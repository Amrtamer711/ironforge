"""
FastAPI Authentication & Authorization Dependencies.

Reads authenticated user context from trusted proxy headers.
unified-ui handles all JWT validation and RBAC - these dependencies
simply extract the pre-validated user data from request headers.

Trusted Headers (set by unified-ui proxy):
- X-Trusted-User-Id: User's UUID
- X-Trusted-User-Email: User's email
- X-Trusted-User-Name: User's display name
- X-Trusted-User-Profile: User's RBAC profile name
- X-Trusted-User-Permissions: JSON array of permission strings
- X-Trusted-User-Companies: JSON array of company schema names user can access

Usage:
    from api.auth import require_auth, require_permission

    @app.get("/api/protected")
    async def protected_route(user: AuthUser = Depends(require_auth)):
        return {"user_id": user.id}

    @app.get("/api/admin")
    async def admin_route(user: AuthUser = Depends(require_permission("core:users:manage"))):
        return {"user_id": user.id}
"""

import json
import logging
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request, status

from integrations.auth.base import AuthUser

logger = logging.getLogger("proposal-bot")


async def get_current_user(request: Request) -> Optional[AuthUser]:
    """
    Get the current authenticated user from trusted proxy headers.

    unified-ui validates the JWT and injects these headers.

    Returns:
        AuthUser if authenticated, None otherwise
    """
    user_id = request.headers.get("x-trusted-user-id")

    if not user_id:
        return None

    email = request.headers.get("x-trusted-user-email", "")
    name = request.headers.get("x-trusted-user-name")
    profile = request.headers.get("x-trusted-user-profile")
    permissions_json = request.headers.get("x-trusted-user-permissions", "[]")
    companies_json = request.headers.get("x-trusted-user-companies", "[]")

    # Parse permissions
    try:
        permissions = json.loads(permissions_json)
    except json.JSONDecodeError:
        permissions = []

    # Parse companies (schema names user can access)
    try:
        companies = json.loads(companies_json)
    except json.JSONDecodeError:
        companies = []

    return AuthUser(
        id=user_id,
        email=email,
        name=name,
        is_active=True,
        supabase_id=user_id,
        metadata={
            "profile": profile,
            "permissions": permissions,
            "companies": companies,
        },
    )


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


def _matches_wildcard(pattern: str, permission: str) -> bool:
    """Check if a wildcard pattern matches a permission."""
    if pattern == "*:*:*":
        return True

    pattern_parts = pattern.split(":")
    perm_parts = permission.split(":")

    if len(pattern_parts) != 3 or len(perm_parts) != 3:
        return False

    for i, (p, t) in enumerate(zip(pattern_parts, perm_parts)):
        if p != "*" and p != t:
            # "manage" action implies all other actions
            if i == 2 and p == "manage":
                return True
            return False

    return True


def _has_permission(permissions: List[str], required: str) -> bool:
    """Check if user has a permission (direct match or wildcard)."""
    if required in permissions:
        return True

    for perm in permissions:
        if _matches_wildcard(perm, required):
            return True

    return False


def require_permission(permission: str) -> Callable:
    """
    Factory for requiring a specific permission.

    Permissions are provided by unified-ui in the X-Trusted-User-Permissions header.
    Supports wildcard patterns like "sales:*:*" or "*:*:*".

    Permission format: {module}:{resource}:{action}
    e.g., "core:users:manage", "sales:proposals:create"

    Usage:
        @app.get("/api/admin")
        async def admin(user: AuthUser = Depends(require_permission("core:users:manage"))):
            return {"user": user.email}
    """
    async def _require_permission(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        permissions: List[str] = user.metadata.get("permissions", [])

        if not _has_permission(permissions, permission):
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

    Profile is provided by unified-ui in the X-Trusted-User-Profile header.

    Usage:
        @app.get("/api/admin-only")
        async def admin_only(user: AuthUser = Depends(require_profile("system_admin"))):
            return {"user": user.email}
    """
    async def _require_profile(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        user_profile = user.metadata.get("profile")

        if user_profile != profile_name:
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
        user_profile = user.metadata.get("profile")

        if user_profile in profile_names:
            return user

        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) lacks profiles: {profile_names}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these profiles required: {', '.join(profile_names)}",
        )

    return _require_any_profile
