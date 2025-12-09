"""
Supabase authentication provider.

Implements AuthProvider using Supabase Auth for JWT validation
and user management.
"""

import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from integrations.auth.base import (
    AuthProvider,
    AuthUser,
    AuthResult,
    AuthStatus,
    TokenPayload,
)
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")


class SupabaseAuthProvider(AuthProvider):
    """
    Supabase Auth provider implementation.

    In a decoupled architecture (4-project setup):
    - UI Supabase handles user authentication and issues JWTs
    - Sales Bot only needs the JWT secret to validate tokens
    - User data is extracted from JWT claims (no API calls needed)

    For token validation only, requires one of:
    - UI_JWT_SECRET (generic)
    - UI_DEV_JWT_SECRET (development environment)
    - UI_PROD_JWT_SECRET (production environment)
    - SUPABASE_JWT_SECRET (legacy backwards compatibility)

    For full user management (optional), also requires:
    - SUPABASE_URL
    - SUPABASE_SERVICE_KEY
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_key: Optional[str] = None,
        jwt_secret: Optional[str] = None,
    ):
        """
        Initialize Supabase auth provider.

        Args:
            supabase_url: Supabase project URL (optional - for user management)
            service_key: Supabase service role key (optional - for user management)
            jwt_secret: JWT secret for token validation (required)
        """
        # JWT secret is primary requirement
        # Check in order: explicit param, environment-specific, generic, legacy
        environment = os.getenv("ENVIRONMENT", "development")

        if jwt_secret:
            self._jwt_secret = jwt_secret
        elif environment == "production":
            # Production: try PROD first, then generic, then legacy
            self._jwt_secret = (
                os.getenv("UI_PROD_JWT_SECRET", "")
                or os.getenv("UI_JWT_SECRET", "")
                or os.getenv("SUPABASE_JWT_SECRET", "")
            )
        else:
            # Development: try DEV first, then generic, then legacy
            self._jwt_secret = (
                os.getenv("UI_DEV_JWT_SECRET", "")
                or os.getenv("UI_JWT_SECRET", "")
                or os.getenv("SUPABASE_JWT_SECRET", "")
            )

        # Supabase client credentials (optional - only needed for user management APIs)
        self._supabase_url = supabase_url or os.getenv("SUPABASE_URL", "")
        self._service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY", "")
        self._client = None

        # Log configuration status
        if self._jwt_secret:
            logger.info(f"[AUTH:SUPABASE] JWT secret configured for {environment} - token validation enabled")
        else:
            logger.warning(f"[AUTH:SUPABASE] No JWT secret! Set UI_DEV_JWT_SECRET or UI_PROD_JWT_SECRET env var.")

        if self._supabase_url and self._service_key:
            logger.info("[AUTH:SUPABASE] Supabase client credentials configured")
        else:
            logger.info("[AUTH:SUPABASE] No Supabase client credentials - using token-only mode")

    def _get_client(self):
        """Get or create Supabase client."""
        if self._client is None:
            try:
                from supabase import create_client
                self._client = create_client(self._supabase_url, self._service_key)
                logger.info("[AUTH:SUPABASE] Client initialized")
            except ImportError:
                logger.error("[AUTH:SUPABASE] supabase package not installed")
                raise
        return self._client

    @property
    def name(self) -> str:
        return "supabase"

    async def verify_token(self, token: str) -> AuthResult:
        """
        Verify JWT token and extract user data from claims.

        This is a stateless verification - no API calls to Supabase needed.
        User data is extracted directly from the JWT claims.
        """
        try:
            import jwt

            if not self._jwt_secret:
                logger.error("[AUTH:SUPABASE] Cannot verify token - no JWT secret configured")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error="JWT secret not configured"
                )

            # Decode and validate JWT
            try:
                payload = jwt.decode(
                    token,
                    self._jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
            except jwt.ExpiredSignatureError:
                logger.debug("[AUTH:SUPABASE] Token expired")
                return AuthResult(
                    success=False,
                    status=AuthStatus.EXPIRED,
                    error="Token has expired"
                )
            except jwt.InvalidTokenError as e:
                logger.warning(f"[AUTH:SUPABASE] Invalid token: {e}")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error=f"Invalid token: {e}"
                )

            # Extract user info from token claims
            user_id = payload.get("sub")
            email = payload.get("email", "")
            user_metadata = payload.get("user_metadata", {})

            if not user_id:
                logger.warning("[AUTH:SUPABASE] Token missing user ID (sub)")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error="Token missing user ID (sub)"
                )

            # Build user object from token data (no API call needed)
            user = AuthUser(
                id=user_id,
                email=email,
                name=user_metadata.get("name") or user_metadata.get("full_name"),
                avatar_url=user_metadata.get("avatar_url"),
                is_active=True,
                supabase_id=user_id,
                metadata=user_metadata,
                access_token=token,
            )

            logger.debug(f"[AUTH:SUPABASE] Token verified for user: {email}")
            return AuthResult(
                success=True,
                user=user,
                status=AuthStatus.AUTHENTICATED,
                token=token,
            )

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Token verification failed: {e}")
            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error=str(e)
            )

    async def _verify_token_via_api(self, token: str) -> AuthResult:
        """Verify token by calling Supabase API (fallback)."""
        try:
            client = self._get_client()

            # Use admin auth to get user from token
            response = client.auth.get_user(token)

            if response and response.user:
                user = AuthUser(
                    id=response.user.id,
                    email=response.user.email or "",
                    name=response.user.user_metadata.get("name"),
                    avatar_url=response.user.user_metadata.get("avatar_url"),
                    is_active=True,
                    supabase_id=response.user.id,
                    metadata=response.user.user_metadata or {},
                    access_token=token,
                )

                return AuthResult(
                    success=True,
                    user=user,
                    status=AuthStatus.AUTHENTICATED,
                    token=token,
                )

            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error="Could not validate token"
            )

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] API token verification failed: {e}")
            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error=str(e)
            )

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        """Get user from Supabase by ID."""
        try:
            client = self._get_client()
            response = client.auth.admin.get_user_by_id(user_id)

            if response and response.user:
                return AuthUser(
                    id=response.user.id,
                    email=response.user.email or "",
                    name=response.user.user_metadata.get("name"),
                    avatar_url=response.user.user_metadata.get("avatar_url"),
                    is_active=True,
                    supabase_id=response.user.id,
                    metadata=response.user.user_metadata or {},
                )

            return None

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Get user by ID failed: {e}")
            return None

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        """Get user from Supabase by email."""
        try:
            client = self._get_client()

            # Supabase doesn't have direct get_user_by_email
            # We need to list users and filter
            response = client.auth.admin.list_users()

            if response:
                for user in response:
                    if user.email == email:
                        return AuthUser(
                            id=user.id,
                            email=user.email or "",
                            name=user.user_metadata.get("name"),
                            avatar_url=user.user_metadata.get("avatar_url"),
                            is_active=True,
                            supabase_id=user.id,
                            metadata=user.user_metadata or {},
                        )

            return None

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Get user by email failed: {e}")
            return None

    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """Sync user to application database."""
        try:
            from db.database import db

            # Check if backend supports user operations
            if not hasattr(db._backend, 'upsert_user'):
                logger.warning("[AUTH:SUPABASE] Database backend doesn't support upsert_user")
                return False

            now = get_uae_time().isoformat()

            return db._backend.upsert_user(
                user_id=user.id,
                email=user.email,
                full_name=user.name,
                avatar_url=user.avatar_url,
                last_login=now,
            )

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Sync user to DB failed: {e}")
            return False

    async def create_user(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """Create user in Supabase."""
        try:
            client = self._get_client()

            user_metadata = metadata or {}
            if name:
                user_metadata["name"] = name

            response = client.auth.admin.create_user({
                "email": email,
                "email_confirm": True,
                "user_metadata": user_metadata,
            })

            if response and response.user:
                return AuthUser(
                    id=response.user.id,
                    email=response.user.email or email,
                    name=name,
                    supabase_id=response.user.id,
                    metadata=user_metadata,
                )

            return None

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Create user failed: {e}")
            return None

    async def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuthUser]:
        """Update user in Supabase."""
        try:
            client = self._get_client()

            update_data: Dict[str, Any] = {}

            # Build user_metadata update
            user_metadata = metadata or {}
            if name is not None:
                user_metadata["name"] = name
            if avatar_url is not None:
                user_metadata["avatar_url"] = avatar_url

            if user_metadata:
                update_data["user_metadata"] = user_metadata

            if is_active is not None:
                update_data["ban_duration"] = "none" if is_active else "876000h"  # ~100 years

            if not update_data:
                # Nothing to update
                return await self.get_user_by_id(user_id)

            response = client.auth.admin.update_user_by_id(user_id, update_data)

            if response and response.user:
                return AuthUser(
                    id=response.user.id,
                    email=response.user.email or "",
                    name=response.user.user_metadata.get("name"),
                    avatar_url=response.user.user_metadata.get("avatar_url"),
                    is_active=is_active if is_active is not None else True,
                    supabase_id=response.user.id,
                    metadata=response.user.user_metadata or {},
                )

            return None

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Update user failed: {e}")
            return None

    async def delete_user(self, user_id: str) -> bool:
        """Delete user from Supabase."""
        try:
            client = self._get_client()
            client.auth.admin.delete_user(user_id)
            logger.info(f"[AUTH:SUPABASE] Deleted user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Delete user failed: {e}")
            return False

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        is_active: Optional[bool] = None,
    ) -> List[AuthUser]:
        """List users from Supabase."""
        try:
            client = self._get_client()
            response = client.auth.admin.list_users()

            users = []
            for i, user in enumerate(response):
                if i < offset:
                    continue
                if len(users) >= limit:
                    break

                # Skip banned users if filtering for active
                is_user_active = not getattr(user, 'banned_until', None)
                if is_active is not None and is_user_active != is_active:
                    continue

                users.append(AuthUser(
                    id=user.id,
                    email=user.email or "",
                    name=user.user_metadata.get("name"),
                    avatar_url=user.user_metadata.get("avatar_url"),
                    is_active=is_user_active,
                    supabase_id=user.id,
                    metadata=user.user_metadata or {},
                ))

            return users

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] List users failed: {e}")
            return []

    async def refresh_token(self, refresh_token: str) -> AuthResult:
        """Refresh access token using refresh token."""
        try:
            client = self._get_client()
            response = client.auth.refresh_session(refresh_token)

            if response and response.session:
                user = AuthUser(
                    id=response.user.id if response.user else "",
                    email=response.user.email if response.user else "",
                    name=response.user.user_metadata.get("name") if response.user else None,
                    access_token=response.session.access_token,
                    refresh_token=response.session.refresh_token,
                )

                return AuthResult(
                    success=True,
                    user=user,
                    status=AuthStatus.AUTHENTICATED,
                    token=response.session.access_token,
                )

            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error="Could not refresh token"
            )

        except Exception as e:
            logger.error(f"[AUTH:SUPABASE] Refresh token failed: {e}")
            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error=str(e)
            )

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """Decode JWT without verification."""
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
