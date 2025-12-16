"""
Supabase authentication provider.

Reads authenticated user context from trusted proxy headers.
unified-ui handles all JWT validation and RBAC - this provider
simply extracts the pre-validated user data from request headers.

Trusted Headers (set by unified-ui proxy):
- X-Trusted-User-Id: User's UUID
- X-Trusted-User-Email: User's email
- X-Trusted-User-Name: User's display name
- X-Trusted-User-Profile: User's RBAC profile name
- X-Trusted-User-Permissions: JSON array of permission strings
"""

import json
import logging
from typing import Any, Optional

from integrations.auth.base import (
    AuthProvider,
    AuthResult,
    AuthStatus,
    AuthUser,
    TokenPayload,
)

logger = logging.getLogger("proposal-bot")

# Thread-local storage for current request headers
_current_request_headers: dict[str, str] = {}


def set_request_headers(headers: dict[str, str]) -> None:
    """
    Set the current request headers for the auth provider.

    Called by FastAPI middleware to make headers available to the provider.

    Args:
        headers: Dictionary of request headers
    """
    global _current_request_headers
    _current_request_headers = dict(headers)


def clear_request_headers() -> None:
    """Clear request headers after request completes."""
    global _current_request_headers
    _current_request_headers = {}


def get_request_header(name: str) -> Optional[str]:
    """Get a request header value."""
    return _current_request_headers.get(name)


class SupabaseAuthProvider(AuthProvider):
    """
    Supabase Auth provider that reads from trusted proxy headers.

    unified-ui is the auth gateway:
    - Validates JWTs against UI Supabase
    - Fetches user profile and permissions from UI Supabase
    - Injects trusted headers when proxying to backend services

    This provider simply reads those pre-validated headers.
    No token validation or database queries needed.
    """

    def __init__(self, **kwargs):
        """Initialize Supabase auth provider."""
        logger.info("[AUTH:SUPABASE] Provider initialized (trusted proxy mode)")

    @property
    def name(self) -> str:
        return "supabase"

    async def verify_token(self, token: str) -> AuthResult:
        """
        Get authenticated user from trusted proxy headers.

        The token parameter is ignored - user context comes from headers
        that unified-ui set after validating the actual JWT.
        """
        try:
            # Read trusted headers
            user_id = get_request_header("x-trusted-user-id")
            email = get_request_header("x-trusted-user-email")
            name = get_request_header("x-trusted-user-name")
            profile = get_request_header("x-trusted-user-profile")
            permissions_json = get_request_header("x-trusted-user-permissions")

            if not user_id:
                logger.debug("[AUTH:SUPABASE] No trusted user headers found")
                return AuthResult(
                    success=False,
                    status=AuthStatus.UNAUTHENTICATED,
                    error="Not authenticated"
                )

            # Parse permissions
            permissions = []
            if permissions_json:
                try:
                    permissions = json.loads(permissions_json)
                except json.JSONDecodeError:
                    logger.warning("[AUTH:SUPABASE] Failed to parse permissions JSON")

            # Build user from headers
            user = AuthUser(
                id=user_id,
                email=email or "",
                name=name,
                is_active=True,
                supabase_id=user_id,
                metadata={
                    "profile": profile,
                    "permissions": permissions,
                },
            )

            logger.debug(f"[AUTH:SUPABASE] User from headers: {email} (profile: {profile})")
            return AuthResult(
                success=True,
                user=user,
                status=AuthStatus.AUTHENTICATED,
            )

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Error reading trusted headers: {e}")
            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error=str(e)
            )

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        """
        Get user by ID.

        In trusted proxy mode, we only have the current request user.
        Returns None - user management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] get_user_by_id not available in proxy mode")
        return None

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        """
        Get user by email.

        In trusted proxy mode, user management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] get_user_by_email not available in proxy mode")
        return None

    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """
        Sync user to database.

        In trusted proxy mode, user data is managed by unified-ui.
        """
        logger.debug("[AUTH:SUPABASE] sync_user_to_db skipped in proxy mode")
        return True

    async def create_user(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """
        Create user.

        User management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] create_user not available in proxy mode")
        return None

    async def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """
        Update user.

        User management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] update_user not available in proxy mode")
        return None

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete user.

        User management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] delete_user not available in proxy mode")
        return False

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        is_active: Optional[bool] = None,
    ) -> list[AuthUser]:
        """
        List users.

        User management is handled by unified-ui.
        """
        logger.warning("[AUTH:SUPABASE] list_users not available in proxy mode")
        return []

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """Decode JWT without verification (for debugging)."""
        try:
            import jwt
            payload = jwt.decode(token, options={"verify_signature": False})

            return TokenPayload(
                sub=payload.get("sub", ""),
                email=payload.get("email"),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
                aud=payload.get("aud"),
                role=payload.get("role"),
                metadata=payload.get("user_metadata", {}),
            )
        except Exception as e:
            logger.warning(f"[AUTH:SUPABASE] Token decode failed: {e}")
            return None
