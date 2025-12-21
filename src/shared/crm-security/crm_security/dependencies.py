"""
FastAPI Authentication & Authorization Dependencies.

Reads authenticated user context from trusted proxy headers.
unified-ui handles all JWT validation and RBAC - these dependencies
simply extract the pre-validated user data from request headers.

Two Return Types Available:
- TrustedUserContext (TypedDict): Dict-like access, e.g., user["id"], user.get("companies")
- AuthUser (dataclass): Property access, e.g., user.id, user.companies

Usage with TrustedUserContext (dict-style):
    from shared.security import require_auth, require_permission

    @app.get("/api/protected")
    async def protected_route(user: TrustedUserContext = Depends(require_auth)):
        return {"user_id": user["id"]}

Usage with AuthUser (dataclass-style):
    from shared.security import require_auth_user, require_permission_user, AuthUser

    @app.get("/api/protected")
    async def protected_route(user: AuthUser = Depends(require_auth_user)):
        return {"user_id": user.id, "companies": user.companies}
"""

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from .trusted_headers import TrustedUserContext, parse_user_context, verify_proxy_secret
from .models import AuthUser
from .rbac import has_permission
from .config import security_config

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> TrustedUserContext | None:
    """
    Get the current authenticated user from trusted proxy headers.

    unified-ui validates the JWT and injects these headers.

    Returns:
        TrustedUserContext if authenticated, None otherwise
    """
    # First verify proxy secret if configured
    if security_config.trust_proxy_headers and security_config.proxy_secret:
        headers_dict = dict(request.headers)
        if not verify_proxy_secret(headers_dict, security_config.proxy_secret):
            logger.warning(f"[AUTH] Invalid proxy secret for {request.url.path}")
            return None

    return parse_user_context(dict(request.headers))


async def require_auth(
    user: TrustedUserContext | None = Depends(get_current_user),
) -> TrustedUserContext:
    """
    Require authentication for an endpoint.

    Raises HTTPException 401 if not authenticated.

    Usage:
        @app.get("/api/protected")
        async def protected(user: TrustedUserContext = Depends(require_auth)):
            return {"user": user["email"]}
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

    Permissions are provided by unified-ui in the X-Trusted-User-Permissions header.
    Supports wildcard patterns like "sales:*:*" or "*:*:*".

    Permission format: {module}:{resource}:{action}
    e.g., "core:users:manage", "sales:proposals:create"

    Usage:
        @app.get("/api/admin")
        async def admin(user: TrustedUserContext = Depends(require_permission("core:users:manage"))):
            return {"user": user["email"]}
    """
    async def _require_permission(
        user: TrustedUserContext = Depends(require_auth),
    ) -> TrustedUserContext:
        permissions: list[str] = user.get("permissions", [])

        if not has_permission(permissions, permission):
            logger.warning(
                f"[AUTH] User {user.get('id')} ({user.get('email')}) lacks permission: {permission}"
            )
            # Detailed error for debugging (only shows first 10 permissions to avoid huge responses)
            user_perms_sample = permissions[:10]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Permission denied",
                    "code": "PERMISSION_DENIED",
                    "required_permission": permission,
                    "user_profile": user.get("profile"),
                    "user_permissions_count": len(permissions),
                    "user_permissions_sample": user_perms_sample,
                    "reason": f"User with profile '{user.get('profile')}' does not have '{permission}'"
                },
            )

        return user

    return _require_permission


def require_any_permission(permissions: list[str]) -> Callable:
    """
    Factory for requiring any of the specified permissions.

    Usage:
        @app.get("/api/data")
        async def get_data(user: TrustedUserContext = Depends(require_any_permission(["sales:*:read", "assets:*:read"]))):
            return {"user": user["email"]}
    """
    async def _require_any_permission(
        user: TrustedUserContext = Depends(require_auth),
    ) -> TrustedUserContext:
        user_permissions: list[str] = user.get("permissions", [])

        for required in permissions:
            if has_permission(user_permissions, required):
                return user

        logger.warning(
            f"[AUTH] User {user.get('id')} ({user.get('email')}) lacks any permission: {permissions}"
        )
        user_perms_sample = user_permissions[:10]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Permission denied",
                "code": "PERMISSION_DENIED",
                "required_permissions": permissions,
                "requires": "any",
                "user_profile": user.get("profile"),
                "user_permissions_count": len(user_permissions),
                "user_permissions_sample": user_perms_sample,
                "reason": f"User with profile '{user.get('profile')}' does not have any of: {permissions}"
            },
        )

    return _require_any_permission


def require_profile(profile_name: str) -> Callable:
    """
    Factory for requiring a specific profile.

    Profile is provided by unified-ui in the X-Trusted-User-Profile header.

    Usage:
        @app.get("/api/admin-only")
        async def admin_only(user: TrustedUserContext = Depends(require_profile("system_admin"))):
            return {"user": user["email"]}
    """
    async def _require_profile(
        user: TrustedUserContext = Depends(require_auth),
    ) -> TrustedUserContext:
        user_profile = user.get("profile")

        if user_profile != profile_name:
            logger.warning(
                f"[AUTH] User {user.get('id')} ({user.get('email')}) lacks profile: {profile_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Profile required",
                    "code": "PROFILE_REQUIRED",
                    "required_profile": profile_name,
                    "user_profile": user_profile,
                    "reason": f"User has profile '{user_profile}' but '{profile_name}' is required"
                },
            )

        return user

    return _require_profile


def require_any_profile(*profile_names: str) -> Callable:
    """
    Factory for requiring any of the specified profiles.

    Usage:
        @app.get("/api/management")
        async def management(user: TrustedUserContext = Depends(require_any_profile("system_admin", "sales_manager"))):
            return {"user": user["email"]}
    """
    async def _require_any_profile(
        user: TrustedUserContext = Depends(require_auth),
    ) -> TrustedUserContext:
        user_profile = user.get("profile")

        if user_profile in profile_names:
            return user

        logger.warning(
            f"[AUTH] User {user.get('id')} ({user.get('email')}) lacks profiles: {profile_names}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Profile required",
                "code": "PROFILE_REQUIRED",
                "required_profiles": list(profile_names),
                "requires": "any",
                "user_profile": user_profile,
                "reason": f"User has profile '{user_profile}' but one of {list(profile_names)} is required"
            },
        )

    return _require_any_profile


def require_company_access(company_param: str = "company") -> Callable:
    """
    Factory for verifying user can access a specific company.

    Usage:
        @app.get("/api/{company}/locations")
        async def get_locations(
            company: str,
            user: TrustedUserContext = Depends(require_company_access("company"))
        ):
            ...
    """
    async def _require_company_access(
        request: Request,
        user: TrustedUserContext = Depends(require_auth),
    ) -> TrustedUserContext:
        company = request.path_params.get(company_param)
        companies = user.get("companies", [])

        if company and company not in companies:
            logger.warning(
                f"[AUTH] User {user.get('id')} ({user.get('email')}) lacks access to company: {company}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Company access denied",
                    "code": "COMPANY_ACCESS_DENIED",
                    "requested_company": company,
                    "user_companies": companies,
                    "user_profile": user.get("profile"),
                    "reason": f"User does not have access to company '{company}'. Accessible companies: {companies}"
                },
            )

        return user

    return _require_company_access


async def require_admin(
    user: TrustedUserContext = Depends(require_auth),
) -> TrustedUserContext:
    """Require system admin profile."""
    user_profile = user.get("profile")
    if user_profile != "system_admin":
        logger.warning(
            f"[AUTH] User {user.get('id')} ({user.get('email')}) denied admin access"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Admin access required",
                "code": "ADMIN_REQUIRED",
                "required_profile": "system_admin",
                "user_profile": user_profile,
                "reason": f"User has profile '{user_profile}' but 'system_admin' is required"
            },
        )
    return user


# =============================================================================
# AUTHUSER-BASED DEPENDENCIES (dataclass return type)
# =============================================================================
# These return AuthUser dataclass instead of TrustedUserContext dict.
# Use these when you need property access (user.id, user.companies) instead
# of dict access (user["id"], user.get("companies")).
# =============================================================================


def _context_to_auth_user(ctx: TrustedUserContext) -> AuthUser:
    """Convert TrustedUserContext to AuthUser dataclass."""
    return AuthUser(
        id=ctx.get("id", ""),
        email=ctx.get("email", ""),
        name=ctx.get("name"),
        is_active=True,
        supabase_id=ctx.get("id"),
        metadata={
            "profile": ctx.get("profile"),
            "permissions": ctx.get("permissions", []),
            "companies": ctx.get("companies", []),
            "teams": ctx.get("teams", []),
            "team_ids": ctx.get("team_ids", []),
            "manager_id": ctx.get("manager_id"),
            "subordinate_ids": ctx.get("subordinate_ids", []),
            "sharing_rules": ctx.get("sharing_rules", []),
            "shared_records": ctx.get("shared_records", {}),
            "shared_from_user_ids": ctx.get("shared_from_user_ids", []),
        },
    )


async def get_current_auth_user(request: Request) -> AuthUser | None:
    """
    Get the current authenticated user as AuthUser dataclass.

    Returns:
        AuthUser if authenticated, None otherwise
    """
    ctx = await get_current_user(request)
    if not ctx:
        return None
    return _context_to_auth_user(ctx)


async def require_auth_user(
    user: AuthUser | None = Depends(get_current_auth_user),
) -> AuthUser:
    """
    Require authentication, returns AuthUser dataclass.

    Raises HTTPException 401 if not authenticated.

    Usage:
        @app.get("/api/protected")
        async def protected(user: AuthUser = Depends(require_auth_user)):
            return {"user": user.email, "companies": user.companies}
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission_user(permission: str) -> Callable:
    """
    Factory for requiring a specific permission, returns AuthUser.

    Usage:
        @app.get("/api/admin")
        async def admin(user: AuthUser = Depends(require_permission_user("core:users:manage"))):
            return {"user": user.email}
    """
    async def _require_permission(
        user: AuthUser = Depends(require_auth_user),
    ) -> AuthUser:
        if not has_permission(user.permissions, permission):
            logger.warning(
                f"[AUTH] User {user.id} ({user.email}) lacks permission: {permission}"
            )
            user_perms_sample = user.permissions[:10]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Permission denied",
                    "code": "PERMISSION_DENIED",
                    "required_permission": permission,
                    "user_profile": user.profile,
                    "user_permissions_count": len(user.permissions),
                    "user_permissions_sample": user_perms_sample,
                    "reason": f"User with profile '{user.profile}' does not have '{permission}'"
                },
            )
        return user

    return _require_permission


def require_any_permission_user(permissions: list[str]) -> Callable:
    """
    Factory for requiring any of the specified permissions, returns AuthUser.
    """
    async def _require_any_permission(
        user: AuthUser = Depends(require_auth_user),
    ) -> AuthUser:
        for required in permissions:
            if has_permission(user.permissions, required):
                return user

        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) lacks any permission: {permissions}"
        )
        user_perms_sample = user.permissions[:10]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Permission denied",
                "code": "PERMISSION_DENIED",
                "required_permissions": permissions,
                "requires": "any",
                "user_profile": user.profile,
                "user_permissions_count": len(user.permissions),
                "user_permissions_sample": user_perms_sample,
                "reason": f"User with profile '{user.profile}' does not have any of: {permissions}"
            },
        )

    return _require_any_permission


def require_profile_user(profile_name: str) -> Callable:
    """
    Factory for requiring a specific profile, returns AuthUser.
    """
    async def _require_profile(
        user: AuthUser = Depends(require_auth_user),
    ) -> AuthUser:
        if user.profile != profile_name:
            logger.warning(
                f"[AUTH] User {user.id} ({user.email}) lacks profile: {profile_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Profile required",
                    "code": "PROFILE_REQUIRED",
                    "required_profile": profile_name,
                    "user_profile": user.profile,
                    "reason": f"User has profile '{user.profile}' but '{profile_name}' is required"
                },
            )
        return user

    return _require_profile


def require_any_profile_user(*profile_names: str) -> Callable:
    """
    Factory for requiring any of the specified profiles, returns AuthUser.
    """
    async def _require_any_profile(
        user: AuthUser = Depends(require_auth_user),
    ) -> AuthUser:
        if user.profile in profile_names:
            return user

        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) lacks profiles: {profile_names}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Profile required",
                "code": "PROFILE_REQUIRED",
                "required_profiles": list(profile_names),
                "requires": "any",
                "user_profile": user.profile,
                "reason": f"User has profile '{user.profile}' but one of {list(profile_names)} is required"
            },
        )

    return _require_any_profile


async def require_admin_user(
    user: AuthUser = Depends(require_auth_user),
) -> AuthUser:
    """Require system admin profile, returns AuthUser."""
    if user.profile != "system_admin":
        logger.warning(
            f"[AUTH] User {user.id} ({user.email}) denied admin access"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Admin access required",
                "code": "ADMIN_REQUIRED",
                "required_profile": "system_admin",
                "user_profile": user.profile,
                "reason": f"User has profile '{user.profile}' but 'system_admin' is required"
            },
        )
    return user
