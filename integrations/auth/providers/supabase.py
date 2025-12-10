"""
Supabase authentication provider.

Implements AuthProvider using Supabase Auth for JWT validation
and user management.

Uses ES256 (asymmetric JWKS) for JWT verification - the default for
Supabase projects created after May 2025.
"""

import os
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from integrations.auth.base import (
    AuthProvider,
    AuthUser,
    AuthResult,
    AuthStatus,
    TokenPayload,
)
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")

# JWKS cache with TTL
_jwks_cache: Dict[str, Any] = {}  # keyed by JWKS URL
_jwks_cache_time: Dict[str, float] = {}
JWKS_CACHE_TTL = 600  # 10 minutes (matches Supabase edge cache)


async def fetch_jwks(jwks_url: str) -> Dict[str, Any]:
    """
    Fetch JWKS from Supabase endpoint with caching.

    Args:
        jwks_url: The JWKS endpoint URL

    Returns:
        The JWKS response containing public keys
    """
    global _jwks_cache, _jwks_cache_time

    now = time.time()

    # Check cache
    if jwks_url in _jwks_cache:
        cache_age = now - _jwks_cache_time.get(jwks_url, 0)
        if cache_age < JWKS_CACHE_TTL:
            logger.debug(f"[AUTH:SUPABASE] Using cached JWKS (age: {cache_age:.0f}s)")
            return _jwks_cache[jwks_url]

    # Fetch fresh JWKS
    logger.info(f"[AUTH:SUPABASE] Fetching JWKS from {jwks_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            jwks = response.json()

            # Cache the result
            _jwks_cache[jwks_url] = jwks
            _jwks_cache_time[jwks_url] = now

            logger.info(f"[AUTH:SUPABASE] JWKS fetched successfully, {len(jwks.get('keys', []))} keys found")
            return jwks
    except Exception as e:
        logger.error(f"[AUTH:SUPABASE] Failed to fetch JWKS: {e}")
        # Return cached version if available (even if stale)
        if jwks_url in _jwks_cache:
            logger.warning("[AUTH:SUPABASE] Using stale cached JWKS due to fetch failure")
            return _jwks_cache[jwks_url]
        raise


def get_signing_key_from_jwks(jwks: Dict[str, Any], kid: str) -> Any:
    """
    Find the signing key in JWKS that matches the key ID.

    Args:
        jwks: The JWKS response
        kid: The key ID from the JWT header

    Returns:
        The matching JWK key
    """
    from jose import jwk

    keys = jwks.get("keys", [])
    for key in keys:
        if key.get("kid") == kid:
            return jwk.construct(key)

    # If no matching kid, and there's only one key, use it
    if len(keys) == 1:
        logger.warning(f"[AUTH:SUPABASE] No key matching kid={kid}, using single available key")
        return jwk.construct(keys[0])

    raise ValueError(f"No key found in JWKS matching kid: {kid}")


class SupabaseAuthProvider(AuthProvider):
    """
    Supabase Auth provider implementation using ES256 JWKS.

    In a decoupled architecture (4-project setup):
    - UI Supabase handles user authentication and issues JWTs
    - Sales Bot fetches the public key from JWKS endpoint to validate tokens
    - User data is extracted from JWT claims (no API calls needed)

    For token validation, requires:
    - UI_SUPABASE_URL or UI_DEV_SUPABASE_URL / UI_PROD_SUPABASE_URL
      (used to construct the JWKS endpoint: {url}/auth/v1/.well-known/jwks.json)

    For full user management (optional), also requires:
    - SUPABASE_URL
    - SUPABASE_SERVICE_KEY
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_key: Optional[str] = None,
        ui_supabase_url: Optional[str] = None,
    ):
        """
        Initialize Supabase auth provider.

        Args:
            supabase_url: Supabase project URL (optional - for user management)
            service_key: Supabase service role key (optional - for user management)
            ui_supabase_url: UI Supabase project URL (for JWKS endpoint)
        """
        environment = os.getenv("ENVIRONMENT", "development")

        # Determine UI Supabase URL for JWKS endpoint
        if ui_supabase_url:
            self._ui_supabase_url = ui_supabase_url
        elif environment == "production":
            self._ui_supabase_url = (
                os.getenv("UI_PROD_SUPABASE_URL", "")
                or os.getenv("UI_SUPABASE_URL", "")
            )
        else:
            self._ui_supabase_url = (
                os.getenv("UI_DEV_SUPABASE_URL", "")
                or os.getenv("UI_SUPABASE_URL", "")
            )

        # Construct JWKS URL from Supabase URL
        if self._ui_supabase_url:
            # Remove trailing slash if present
            base_url = self._ui_supabase_url.rstrip("/")
            self._jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"
        else:
            self._jwks_url = ""

        # Supabase client credentials (optional - only needed for user management APIs)
        self._supabase_url = supabase_url or os.getenv("SUPABASE_URL", "")
        self._service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY", "")
        self._client = None

        # Log configuration status
        if self._jwks_url:
            logger.info(f"[AUTH:SUPABASE] JWKS URL configured for {environment}: {self._jwks_url}")
        else:
            logger.warning(f"[AUTH:SUPABASE] No JWKS URL! Set UI_DEV_SUPABASE_URL or UI_PROD_SUPABASE_URL env var.")

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
        Verify JWT token using ES256 with JWKS and extract user data from claims.

        This fetches the public key from Supabase's JWKS endpoint and verifies
        the token signature. User data is extracted directly from the JWT claims.
        """
        print(f"[SUPABASE AUTH] verify_token called, jwks_url={self._jwks_url}")
        try:
            from jose import jwt as jose_jwt
            from jose.exceptions import ExpiredSignatureError, JWTError

            if not self._jwks_url:
                logger.error("[AUTH:SUPABASE] Cannot verify token - no JWKS URL configured")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error="JWKS URL not configured. Set UI_DEV_SUPABASE_URL or UI_PROD_SUPABASE_URL."
                )

            # Get the key ID from token header
            try:
                unverified_header = jose_jwt.get_unverified_header(token)
                kid = unverified_header.get("kid")
                alg = unverified_header.get("alg", "ES256")

                if not kid:
                    logger.warning("[AUTH:SUPABASE] Token missing key ID (kid) in header")
                    return AuthResult(
                        success=False,
                        status=AuthStatus.INVALID,
                        error="Token missing key ID (kid)"
                    )
            except JWTError as e:
                logger.warning(f"[AUTH:SUPABASE] Invalid token header: {e}")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error=f"Invalid token header: {e}"
                )

            # Fetch JWKS and get the signing key
            try:
                jwks = await fetch_jwks(self._jwks_url)
                signing_key = get_signing_key_from_jwks(jwks, kid)
            except Exception as e:
                logger.error(f"[AUTH:SUPABASE] Failed to get signing key: {e}")
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error=f"Failed to get signing key: {e}"
                )

            # Decode and validate JWT
            try:
                payload = jose_jwt.decode(
                    token,
                    signing_key,
                    algorithms=[alg],
                    audience="authenticated",
                )
            except ExpiredSignatureError:
                logger.debug("[AUTH:SUPABASE] Token expired")
                return AuthResult(
                    success=False,
                    status=AuthStatus.EXPIRED,
                    error="Token has expired"
                )
            except JWTError as e:
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
