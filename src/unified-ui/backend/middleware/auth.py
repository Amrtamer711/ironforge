"""
Authentication middleware for unified-ui (API Gateway).

[VERIFIED] Mirrors server.js lines 548-805:
- proxyAuthMiddleware (lines 548-621) - for proxy routes, includes full RBAC
- requireAuth (lines 742-767) - basic JWT validation
- requireProfile (lines 772-805) - profile check middleware

These middlewares are implemented as FastAPI dependencies.

ARCHITECTURE NOTE:
==================
This module contains gateway-specific AuthUser (raw Supabase response).
This is DIFFERENT from shared/security/models.py::AuthUser.

Flow:
1. User request with JWT → unified-ui validates with Supabase → AuthUser (this file)
2. unified-ui fetches full RBAC from database → TrustedUser
3. Proxy injects TrustedUser as X-Trusted-User-* headers
4. Backend services receive headers → TrustedUserMiddleware parses → shared AuthUser

The separation is intentional:
- Gateway AuthUser = minimal (raw JWT claims)
- Shared AuthUser = full RBAC context (permissions, profile, companies)

LOCAL AUTH MODE:
================
When ENVIRONMENT=local and AUTH_PROVIDER=local, this middleware uses
the local_auth service for fully offline development. This allows:
- Testing without network access
- Using test personas from personas.yaml
- SQLite-based user/RBAC lookup
"""

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request

from backend.config import get_settings
from backend.services.rbac_service import get_user_rbac_data
from backend.services.supabase_client import get_supabase
from backend.services.local_auth import (
    is_local_auth_enabled,
    local_get_user,
    local_get_rbac,
    get_persona_by_token,
    get_local_user_rbac,
    LocalRBACData,
)

# Dev mode detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
IS_DEV = ENVIRONMENT in ("local", "development", "test")

logger = logging.getLogger("unified-ui")

# Auth timeout configuration (seconds)
SUPABASE_AUTH_TIMEOUT = float(os.getenv("SUPABASE_AUTH_TIMEOUT", "5.0"))


async def _get_user_with_timeout(supabase, token: str, timeout: float = None):
    """
    Get Supabase user with timeout to prevent indefinite hangs.

    The Supabase SDK's get_user() is synchronous and can block indefinitely
    if the Supabase service is slow or unavailable. This wrapper runs it
    in a thread with a timeout.

    Args:
        supabase: Supabase client instance
        token: JWT token to validate
        timeout: Timeout in seconds (defaults to SUPABASE_AUTH_TIMEOUT)

    Returns:
        Supabase user object or None

    Raises:
        asyncio.TimeoutError: If the request times out
    """
    if timeout is None:
        timeout = SUPABASE_AUTH_TIMEOUT

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(supabase.auth.get_user, token),
            timeout=timeout
        )
        return response.user
    except asyncio.TimeoutError:
        logger.warning(f"[UI Auth] Supabase auth timeout after {timeout}s")
        raise


# =============================================================================
# USER MODELS
# =============================================================================

@dataclass
class AuthUser:
    """
    Authenticated user from Supabase.
    Mirrors server.js req.user structure.
    """
    id: str
    email: str
    role: str | None = None
    user_metadata: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        """Get user's display name from metadata."""
        if self.user_metadata:
            return (
                self.user_metadata.get("name") or
                self.user_metadata.get("full_name") or
                ""
            )
        return ""


@dataclass
class TrustedUser:
    """
    User with full RBAC context for proxy requests.
    Mirrors server.js req.trustedUser (lines 592-614).
    """
    id: str
    email: str
    name: str
    # Level 1: Profile
    profile: str
    # Level 1 + 2: Combined permissions
    permissions: list[str]
    # Level 2: Permission sets
    permission_sets: list[dict[str, Any]]
    # Level 3: Teams
    teams: list[dict[str, Any]]
    team_ids: list[int]
    # Level 3: Hierarchy
    manager_id: str | None
    subordinate_ids: list[str]
    # Level 4: Sharing
    sharing_rules: list[dict[str, Any]]
    shared_records: dict[str, list[dict[str, Any]]]
    shared_from_user_ids: list[str]
    # Level 5: Company access
    companies: list[str]


# =============================================================================
# IMPERSONATION HELPER
# =============================================================================

def _get_impersonation_context(request: Request) -> dict | None:
    """
    Check if request has dev impersonation cookie.

    Only works in dev mode - returns None in production.
    """
    if not IS_DEV:
        return None

    import json
    impersonate_cookie = request.cookies.get("dev_impersonate")
    if not impersonate_cookie:
        return None

    try:
        return json.loads(impersonate_cookie)
    except json.JSONDecodeError:
        return None


def _get_permission_overrides(request: Request) -> dict:
    """
    Get permission overrides from dev cookie.

    Returns dict with:
    - mode: "modify" (default) or "exact"
    - added: list of permissions to add
    - removed: list of permissions to remove
    - exact_permissions: if mode is "exact", use only these permissions
    """
    if not IS_DEV:
        return {"mode": "modify", "added": [], "removed": []}

    import json
    override_cookie = request.cookies.get("dev_permission_overrides")
    if not override_cookie:
        return {"mode": "modify", "added": [], "removed": []}

    try:
        return json.loads(override_cookie)
    except json.JSONDecodeError:
        return {"mode": "modify", "added": [], "removed": []}


def _get_company_overrides(request: Request) -> dict:
    """
    Get company overrides from dev cookie.

    Returns dict with:
    - mode: "modify" (default) or "exact"
    - added: list of companies to add
    - removed: list of companies to remove
    - exact_companies: if mode is "exact", use only these companies
    """
    if not IS_DEV:
        return {"mode": "modify", "added": [], "removed": []}

    import json
    override_cookie = request.cookies.get("dev_company_overrides")
    if not override_cookie:
        return {"mode": "modify", "added": [], "removed": []}

    try:
        return json.loads(override_cookie)
    except json.JSONDecodeError:
        return {"mode": "modify", "added": [], "removed": []}


def _apply_permission_overrides(
    permissions: list[str],
    overrides: dict,
) -> list[str]:
    """
    Apply permission overrides to a permission list.

    Handles two modes:
    - "exact": Replace permissions entirely with exact_permissions list
    - "modify" (default): Add/remove individual permissions
    """
    mode = overrides.get("mode", "modify")

    if mode == "exact":
        # Replace entirely with exact permissions
        return overrides.get("exact_permissions", [])

    # Modify mode: add/remove individual permissions
    result = list(permissions)  # Copy the list

    # Add new permissions
    for perm in overrides.get("added", []):
        if perm not in result:
            result.append(perm)

    # Remove permissions
    for perm in overrides.get("removed", []):
        if perm in result:
            result.remove(perm)

    return result


def _apply_company_overrides(
    companies: list[str],
    overrides: dict,
) -> list[str]:
    """
    Apply company overrides to a company list.

    Handles two modes:
    - "exact": Replace companies entirely with exact_companies list
    - "modify" (default): Add/remove individual companies
    """
    mode = overrides.get("mode", "modify")

    if mode == "exact":
        # Replace entirely with exact companies
        return overrides.get("exact_companies", [])

    # Modify mode: add/remove individual companies
    result = list(companies)  # Copy the list

    # Add new companies
    for company in overrides.get("added", []):
        if company not in result:
            result.append(company)

    # Remove companies
    for company in overrides.get("removed", []):
        if company in result:
            result.remove(company)

    return result


async def _expand_companies_for_hierarchy(companies: list[str]) -> list[str]:
    """
    Expand company codes using hierarchical access rules.

    If a user has access to a group company (e.g., 'mmg' or 'backlite'),
    this expands to all leaf companies they can access:
    - mmg -> all companies (backlite_dubai, backlite_uk, backlite_abudhabi, viola)
    - backlite -> all backlite verticals (backlite_dubai, backlite_uk, backlite_abudhabi)
    - backlite_dubai -> just backlite_dubai (leaf company)

    Calls asset-management /api/companies/expand endpoint.
    Falls back to original companies if the API call fails.
    """
    if not companies:
        return []

    settings = get_settings()
    if not settings.ASSET_MANAGEMENT_URL:
        logger.warning("[AUTH] Asset Management URL not configured, cannot expand companies")
        return companies

    try:
        # Build query string with all company codes
        params = "&".join(f"company_codes={c}" for c in companies)
        url = f"{settings.ASSET_MANAGEMENT_URL}/api/companies/expand?{params}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url)
            response.raise_for_status()
            data = response.json()
            expanded = data.get("expanded", companies)

            if expanded != companies:
                logger.info(f"[AUTH] Expanded companies: {companies} -> {expanded}")

            return expanded

    except httpx.TimeoutException:
        logger.warning("[AUTH] Timeout expanding companies, using original list")
        return companies
    except httpx.ConnectError as e:
        logger.warning(f"[AUTH] Connection error expanding companies: {e}")
        return companies
    except Exception as e:
        logger.warning(f"[AUTH] Error expanding companies: {e}, using original list")
        return companies


def _build_trusted_user_from_impersonation(impersonate_data: dict) -> TrustedUser:
    """
    Build TrustedUser from impersonation cookie data + full RBAC from persona.
    """
    persona_id = impersonate_data.get("persona_id")

    # Load full RBAC from personas.yaml
    user_id = f"test-{persona_id}"
    local_rbac = get_local_user_rbac(user_id)

    if local_rbac:
        return TrustedUser(
            id=user_id,
            email=impersonate_data.get("email", ""),
            name=impersonate_data.get("name", ""),
            profile=local_rbac.profile,
            permissions=local_rbac.permissions,
            permission_sets=local_rbac.permission_sets,
            teams=local_rbac.teams,
            team_ids=local_rbac.team_ids,
            manager_id=local_rbac.manager_id,
            subordinate_ids=local_rbac.subordinate_ids,
            sharing_rules=local_rbac.sharing_rules,
            shared_records=local_rbac.shared_records,
            shared_from_user_ids=local_rbac.shared_from_user_ids,
            companies=local_rbac.companies,
        )

    # Fallback to cookie data only (limited RBAC)
    logger.warning(f"[IMPERSONATE] No full RBAC for {persona_id}, using cookie data")
    return TrustedUser(
        id=user_id,
        email=impersonate_data.get("email", ""),
        name=impersonate_data.get("name", ""),
        profile=impersonate_data.get("profile", ""),
        permissions=[],
        permission_sets=[],
        teams=[],
        team_ids=[],
        manager_id=None,
        subordinate_ids=[],
        sharing_rules=[],
        shared_records={},
        shared_from_user_ids=[],
        companies=impersonate_data.get("companies", []),
    )


# =============================================================================
# REQUIRE AUTH MIDDLEWARE - server.js:742-767
# =============================================================================

async def get_current_user(request: Request) -> AuthUser | None:
    """
    Extract and validate user from Authorization header.

    This is the base dependency - returns None if not authenticated.
    Use require_auth() for endpoints that require authentication.

    Supports two modes:
    - Supabase auth (default): Validates JWT against Supabase
    - Local auth (ENVIRONMENT=local, AUTH_PROVIDER=local): Uses local SQLite/personas
    """
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer " prefix

    # LOCAL AUTH MODE
    if is_local_auth_enabled():
        local_user = local_get_user(token)
        if local_user:
            return AuthUser(
                id=local_user.id,
                email=local_user.email,
                role="authenticated",
                user_metadata={"name": local_user.name} if local_user.name else None,
            )
        return None

    # SUPABASE AUTH MODE (default)
    supabase = get_supabase()
    if not supabase:
        return None

    try:
        user = await _get_user_with_timeout(supabase, token)

        if not user:
            return None

        return AuthUser(
            id=user.id,
            email=user.email,
            role=user.role,
            user_metadata=user.user_metadata,
        )

    except asyncio.TimeoutError:
        logger.warning("[UI Auth] Auth service timeout - returning None")
        return None
    except Exception as e:
        logger.debug(f"[UI Auth] Token validation failed: {e}")
        return None


async def require_auth(request: Request) -> AuthUser:
    """
    Require authentication - raises 401 if not authenticated.

    Mirrors server.js:742-767 (requireAuth)

    Supports two modes:
    - Supabase auth (default): Validates JWT against Supabase
    - Local auth (ENVIRONMENT=local, AUTH_PROVIDER=local): Uses local SQLite/personas

    Usage:
        @router.get("/protected")
        async def protected_endpoint(user: AuthUser = Depends(require_auth)):
            return {"user_id": user.id}
    """
    auth_header = request.headers.get("authorization")

    # server.js:747-750
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "requiresAuth": True},
        )

    token = auth_header[7:]

    # LOCAL AUTH MODE
    if is_local_auth_enabled():
        local_user = local_get_user(token)
        if not local_user:
            raise HTTPException(
                status_code=401,
                detail={"error": "Invalid token", "requiresAuth": True},
            )
        logger.debug(f"[UI Auth] Local auth: {local_user.email}")
        return AuthUser(
            id=local_user.id,
            email=local_user.email,
            role="authenticated",
            user_metadata={"name": local_user.name} if local_user.name else None,
        )

    # SUPABASE AUTH MODE (default)
    supabase = get_supabase()

    # server.js:743-745
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # server.js:754-759
        user = await _get_user_with_timeout(supabase, token)

        if not user:
            raise HTTPException(
                status_code=401,
                detail={"error": "Invalid token", "requiresAuth": True},
            )

        # server.js:761 - req.user = user
        return AuthUser(
            id=user.id,
            email=user.email,
            role=user.role,
            user_metadata=user.user_metadata,
        )

    except asyncio.TimeoutError:
        logger.warning("[UI Auth] Auth service timeout")
        raise HTTPException(
            status_code=503,
            detail={"error": "Auth service temporarily unavailable", "retryable": True},
        )
    except HTTPException:
        raise
    except Exception as e:
        # server.js:763-765
        logger.error(f"[UI Auth] Error: {e}")
        raise HTTPException(
            status_code=401,
            detail={"error": "Authentication failed", "requiresAuth": True},
        )


# =============================================================================
# REQUIRE PROFILE MIDDLEWARE - server.js:772-805
# =============================================================================

def require_profile(*allowed_profiles: str) -> Callable:
    """
    Create a dependency that checks if user has one of the allowed profiles.

    Mirrors server.js:772-805 (requireProfile)

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: AuthUser = Depends(require_profile("system_admin"))):
            return {"admin": True}

        # Multiple profiles allowed:
        @router.get("/managers")
        async def managers_endpoint(
            user: AuthUser = Depends(require_profile("system_admin", "sales_manager"))
        ):
            return {"manager": True}
    """

    async def check_profile(
        user: AuthUser = Depends(require_auth),
    ) -> AuthUser:
        supabase = get_supabase()

        # server.js:774-776
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            # server.js:779-784 - Get user's profile from users table
            user_response = (
                supabase.table("users")
                .select("profile_id, profiles(name)")
                .eq("id", user.id)
                .single()
                .execute()
            )

            user_data = user_response.data

            # server.js:786-788
            if not user_data or not user_data.get("profiles", {}).get("name"):
                logger.warning(f"[UI Auth] User {user.email} has no profile assigned")
                raise HTTPException(status_code=403, detail="No profile assigned")

            user_profile = user_data["profiles"]["name"]

            # server.js:793-795
            if user_profile not in allowed_profiles:
                logger.warning(
                    f"[UI Auth] User {user.email} with profile {user_profile} "
                    f"denied access (requires: {', '.join(allowed_profiles)})"
                )
                raise HTTPException(status_code=403, detail="Insufficient permissions")

            # server.js:798 - req.userProfile = userProfile
            # We return the user; profile can be accessed separately if needed
            return user

        except HTTPException:
            raise
        except Exception as e:
            # server.js:800-802
            logger.error(f"[UI Auth] Profile check error: {e}")
            raise HTTPException(status_code=500, detail="Failed to check permissions")

    return check_profile


# =============================================================================
# REQUIRE PERMISSION MIDDLEWARE
# =============================================================================

def require_permission(*required_permissions: str, require_all: bool = False) -> Callable:
    """
    Create a dependency that checks if user has required permission(s).

    More granular than require_profile - checks actual permissions from RBAC.

    Args:
        required_permissions: Permission strings (e.g., "admin:users:read")
        require_all: If True, user must have ALL permissions. Default: any one.

    Usage:
        @router.get("/users")
        async def list_users(user: AuthUser = Depends(require_permission("admin:users:read"))):
            ...

        # Multiple (any one):
        @router.post("/users")
        async def create_user(user: AuthUser = Depends(require_permission("admin:users:create", "admin:users:manage"))):
            ...
    """
    import re
    from backend.services.rbac_service import get_user_rbac_data

    def _check_perm_match(user_perms: list[str], required: str) -> bool:
        """Check permission with wildcard support."""
        if required in user_perms or "*:*:*" in user_perms:
            return True
        for perm in user_perms:
            if "*" in perm:
                pattern = perm.replace("*", ".*")
                if re.match(f"^{pattern}$", required):
                    return True
        return False

    async def check_permission(user: AuthUser = Depends(require_auth)) -> AuthUser:
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            rbac = await get_user_rbac_data(user.id)
            if not rbac:
                raise HTTPException(status_code=403, detail="No permissions assigned")

            user_perms = rbac.get("permissions", [])

            if require_all:
                has_access = all(_check_perm_match(user_perms, p) for p in required_permissions)
            else:
                has_access = any(_check_perm_match(user_perms, p) for p in required_permissions)

            if not has_access:
                logger.warning(f"[UI Auth] {user.email} denied (needs: {required_permissions})")
                raise HTTPException(status_code=403, detail="Insufficient permissions")

            return user

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[UI Auth] Permission check error: {e}")
            raise HTTPException(status_code=500, detail="Failed to check permissions")

    return check_permission


# =============================================================================
# PROXY AUTH MIDDLEWARE - server.js:548-621
# =============================================================================

async def get_trusted_user(request: Request) -> TrustedUser:
    """
    Authenticate user and build full RBAC context for proxy requests.

    Mirrors server.js:548-621 (proxyAuthMiddleware)

    This includes full 5-level RBAC context that will be injected
    as trusted headers when proxying to backend services.

    Supports three modes:
    - Impersonation (dev only): Uses dev_impersonate cookie to switch context
    - Supabase auth (default): Validates JWT and fetches RBAC from Supabase
    - Local auth (ENVIRONMENT=local, AUTH_PROVIDER=local): Uses personas/SQLite

    In dev mode, also applies permission and company overrides from cookies.
    """
    # Get overrides (dev mode only)
    permission_overrides = _get_permission_overrides(request)
    has_permission_overrides = (
        permission_overrides.get("mode") == "exact"
        or permission_overrides.get("added")
        or permission_overrides.get("removed")
    )

    company_overrides = _get_company_overrides(request)
    has_company_overrides = (
        company_overrides.get("mode") == "exact"
        or company_overrides.get("added")
        or company_overrides.get("removed")
    )

    # DEV MODE: Check for impersonation cookie FIRST
    # This allows testing different user contexts without logging out
    impersonate_data = _get_impersonation_context(request)
    if impersonate_data:
        logger.info(f"[PROXY AUTH] Using impersonated user: {impersonate_data.get('persona_id')}")
        trusted_user = _build_trusted_user_from_impersonation(impersonate_data)

        # Apply permission overrides if any
        if has_permission_overrides:
            trusted_user.permissions = _apply_permission_overrides(
                trusted_user.permissions, permission_overrides
            )
            logger.debug(f"[PROXY AUTH] Applied permission overrides: {permission_overrides}")

        # Apply company overrides if any
        if has_company_overrides:
            trusted_user.companies = _apply_company_overrides(
                trusted_user.companies, company_overrides
            )
            logger.debug(f"[PROXY AUTH] Applied company overrides: {company_overrides}")

        # Expand companies based on hierarchy (e.g., 'backlite' -> all backlite verticals)
        trusted_user.companies = await _expand_companies_for_hierarchy(trusted_user.companies)

        return trusted_user

    # server.js:552-554
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header[7:]

    # LOCAL AUTH MODE
    if is_local_auth_enabled():
        try:
            local_user = local_get_user(token)
            if not local_user:
                logger.warning("[PROXY AUTH] Local auth: Invalid token")
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            # Get RBAC from local source (personas.yaml or SQLite)
            local_rbac = local_get_rbac(local_user.id)
            if not local_rbac:
                logger.warning(
                    f"[PROXY AUTH] Local auth: No RBAC for {local_user.id}"
                )
                # Return minimal context for local testing
                return TrustedUser(
                    id=local_user.id,
                    email=local_user.email,
                    name=local_user.name or "",
                    profile=local_user.profile_name or "viewer",
                    permissions=[],
                    permission_sets=[],
                    teams=[],
                    team_ids=[],
                    manager_id=None,
                    subordinate_ids=[],
                    sharing_rules=[],
                    shared_records={},
                    shared_from_user_ids=[],
                    companies=[],
                )

            # Build TrustedUser from local RBAC
            logger.debug(f"[PROXY AUTH] Local auth: {local_user.email} -> {local_rbac.profile}")

            # Apply permission overrides if any
            final_permissions = local_rbac.permissions
            if has_permission_overrides:
                final_permissions = _apply_permission_overrides(
                    local_rbac.permissions, permission_overrides
                )
                logger.debug(f"[PROXY AUTH] Applied permission overrides: {permission_overrides}")

            # Apply company overrides if any
            final_companies = local_rbac.companies
            if has_company_overrides:
                final_companies = _apply_company_overrides(
                    local_rbac.companies, company_overrides
                )
                logger.debug(f"[PROXY AUTH] Applied company overrides: {company_overrides}")

            # Expand companies based on hierarchy (e.g., 'backlite' -> all backlite verticals)
            final_companies = await _expand_companies_for_hierarchy(final_companies)

            return TrustedUser(
                id=local_user.id,
                email=local_user.email,
                name=local_user.name or "",
                profile=local_rbac.profile,
                permissions=final_permissions,
                permission_sets=local_rbac.permission_sets,
                teams=local_rbac.teams,
                team_ids=local_rbac.team_ids,
                manager_id=local_rbac.manager_id,
                subordinate_ids=local_rbac.subordinate_ids,
                sharing_rules=local_rbac.sharing_rules,
                shared_records=local_rbac.shared_records,
                shared_from_user_ids=local_rbac.shared_from_user_ids,
                companies=final_companies,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[PROXY AUTH] Local auth error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")

    # SUPABASE AUTH MODE (default)
    supabase = get_supabase()

    # server.js:556-558
    if not supabase:
        raise HTTPException(status_code=500, detail="Auth service not configured")

    try:
        # server.js:561-567
        user = await _get_user_with_timeout(supabase, token)

        if not user:
            logger.warning("[PROXY AUTH] Invalid token: no user")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # server.js:569-578 - Get RBAC (uses internal caching)
        rbac = await get_user_rbac_data(user.id)

        # server.js:580-588 - If RBAC is null, user doesn't exist or is deactivated
        if not rbac:
            logger.warning(
                f"[PROXY AUTH] User {user.id} ({user.email}) not authorized - "
                "not in users table or deactivated"
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Account not found or deactivated",
                    "code": "USER_NOT_FOUND",
                    "requiresLogout": True,
                },
            )

        # server.js:590-614 - Build trustedUser object
        rbac_dict = rbac.to_dict()

        # Apply permission overrides if any (dev mode only)
        final_permissions = rbac_dict["permissions"]
        if has_permission_overrides:
            final_permissions = _apply_permission_overrides(
                rbac_dict["permissions"], permission_overrides
            )
            logger.debug(f"[PROXY AUTH] Applied permission overrides: {permission_overrides}")

        # Apply company overrides if any (dev mode only)
        final_companies = rbac_dict["companies"]
        if has_company_overrides:
            final_companies = _apply_company_overrides(
                rbac_dict["companies"], company_overrides
            )
            logger.debug(f"[PROXY AUTH] Applied company overrides: {company_overrides}")

        # Expand companies based on hierarchy (e.g., 'backlite' -> all backlite verticals)
        final_companies = await _expand_companies_for_hierarchy(final_companies)

        return TrustedUser(
            id=user.id,
            email=user.email,
            name=user.user_metadata.get("name") or user.user_metadata.get("full_name") or "" if user.user_metadata else "",
            # Level 1: Profile
            profile=rbac_dict["profile"],
            # Level 1 + 2: Combined permissions (with overrides applied)
            permissions=final_permissions,
            # Level 2: Permission sets
            permission_sets=rbac_dict["permissionSets"],
            # Level 3: Teams
            teams=rbac_dict["teams"],
            team_ids=[t["id"] for t in rbac_dict["teams"]],
            # Level 3: Hierarchy
            manager_id=rbac_dict["managerId"],
            subordinate_ids=rbac_dict["subordinateIds"],
            # Level 4: Sharing
            sharing_rules=rbac_dict["sharingRules"],
            shared_records=rbac_dict["sharedRecords"],
            shared_from_user_ids=rbac_dict["sharedFromUserIds"],
            # Level 5: Company access (with overrides and hierarchy expansion applied)
            companies=final_companies,
        )

    except asyncio.TimeoutError:
        logger.warning("[PROXY AUTH] Auth service timeout")
        raise HTTPException(
            status_code=503,
            detail={"error": "Auth service temporarily unavailable", "retryable": True},
        )
    except HTTPException:
        raise
    except Exception as e:
        # server.js:617-620
        logger.error(f"[PROXY AUTH] Error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
