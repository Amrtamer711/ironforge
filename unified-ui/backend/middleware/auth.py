"""
Authentication middleware for unified-ui.

[VERIFIED] Mirrors server.js lines 548-805:
- proxyAuthMiddleware (lines 548-621) - for proxy routes, includes full RBAC
- requireAuth (lines 742-767) - basic JWT validation
- requireProfile (lines 772-805) - profile check middleware

These middlewares are implemented as FastAPI dependencies.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request

from backend.services.supabase_client import get_supabase
from backend.services.rbac_service import get_user_rbac_data, RBACContext

logger = logging.getLogger("unified-ui")


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
    role: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None

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
    permissions: List[str]
    # Level 2: Permission sets
    permission_sets: List[Dict[str, Any]]
    # Level 3: Teams
    teams: List[Dict[str, Any]]
    team_ids: List[int]
    # Level 3: Hierarchy
    manager_id: Optional[str]
    subordinate_ids: List[str]
    # Level 4: Sharing
    sharing_rules: List[Dict[str, Any]]
    shared_records: Dict[str, List[Dict[str, Any]]]
    shared_from_user_ids: List[str]
    # Level 5: Company access
    companies: List[str]


# =============================================================================
# REQUIRE AUTH MIDDLEWARE - server.js:742-767
# =============================================================================

async def get_current_user(request: Request) -> Optional[AuthUser]:
    """
    Extract and validate user from Authorization header.

    This is the base dependency - returns None if not authenticated.
    Use require_auth() for endpoints that require authentication.
    """
    supabase = get_supabase()
    if not supabase:
        return None

    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer " prefix

    try:
        response = supabase.auth.get_user(token)
        user = response.user

        if not user:
            return None

        return AuthUser(
            id=user.id,
            email=user.email,
            role=user.role,
            user_metadata=user.user_metadata,
        )

    except Exception as e:
        logger.debug(f"[UI Auth] Token validation failed: {e}")
        return None


async def require_auth(request: Request) -> AuthUser:
    """
    Require authentication - raises 401 if not authenticated.

    Mirrors server.js:742-767 (requireAuth)

    Usage:
        @router.get("/protected")
        async def protected_endpoint(user: AuthUser = Depends(require_auth)):
            return {"user_id": user.id}
    """
    supabase = get_supabase()

    # server.js:743-745
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    auth_header = request.headers.get("authorization")

    # server.js:747-750
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "requiresAuth": True},
        )

    token = auth_header[7:]

    try:
        # server.js:754-759
        response = supabase.auth.get_user(token)
        user = response.user

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
# PROXY AUTH MIDDLEWARE - server.js:548-621
# =============================================================================

async def get_trusted_user(request: Request) -> TrustedUser:
    """
    Authenticate user and build full RBAC context for proxy requests.

    Mirrors server.js:548-621 (proxyAuthMiddleware)

    This includes full 5-level RBAC context that will be injected
    as trusted headers when proxying to proposal-bot.
    """
    supabase = get_supabase()

    # server.js:552-554
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    # server.js:556-558
    if not supabase:
        raise HTTPException(status_code=500, detail="Auth service not configured")

    try:
        # server.js:561-567
        token = auth_header[7:]
        response = supabase.auth.get_user(token)
        user = response.user

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

        return TrustedUser(
            id=user.id,
            email=user.email,
            name=user.user_metadata.get("name") or user.user_metadata.get("full_name") or "" if user.user_metadata else "",
            # Level 1: Profile
            profile=rbac_dict["profile"],
            # Level 1 + 2: Combined permissions
            permissions=rbac_dict["permissions"],
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
            # Level 5: Company access
            companies=rbac_dict["companies"],
        )

    except HTTPException:
        raise
    except Exception as e:
        # server.js:617-620
        logger.error(f"[PROXY AUTH] Error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
