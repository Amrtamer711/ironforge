"""
API Key Authentication - SDK Client.

Thin client that validates API keys via the security-service.
All key storage and management is handled by the service.

Usage:
    from crm_security import require_api_key, APIKeyScope

    @app.get("/api/external/data")
    async def get_data(api_key: APIKeyInfo = Depends(require_api_key())):
        return {"client": api_key.name}
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from .config import security_config

logger = logging.getLogger(__name__)


class APIKeyScope(str, Enum):
    """API key access scopes."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    PROPOSALS = "proposals"
    MOCKUPS = "mockups"
    ASSETS = "assets"


@dataclass
class APIKeyInfo:
    """Information about a validated API key."""
    key_id: str
    name: str
    scopes: list[APIKeyScope]
    rate_limit_per_minute: int | None = None
    rate_limit_per_day: int | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if key has a specific scope."""
        if APIKeyScope.ADMIN in self.scopes:
            return True
        if scope == APIKeyScope.READ and APIKeyScope.WRITE in self.scopes:
            return True
        return scope in self.scopes


# API key header scheme
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _validate_key_via_service(raw_key: str, request: Request) -> APIKeyInfo | None:
    """Validate API key by calling security-service."""
    if not security_config.security_service_url:
        logger.debug("[API_KEY] SECURITY_SERVICE_URL not configured")
        return None

    try:
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": security_config.service_name,
        }
        if security_config.service_api_secret:
            headers["X-Service-Secret"] = security_config.service_api_secret

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{security_config.security_service_url}/api/api-keys/validate",
                json={
                    "api_key": raw_key,
                },
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()

                # Check if validation succeeded
                if not data.get("valid", False):
                    logger.debug(f"[API_KEY] Validation failed: {data.get('error')}")
                    return None

                scopes = [APIKeyScope(s) for s in data.get("scopes", ["read"])]

                return APIKeyInfo(
                    key_id=data.get("key_id", ""),
                    name=data.get("client_name", ""),
                    scopes=scopes,
                    rate_limit_per_minute=data.get("rate_limit_per_minute"),
                    rate_limit_per_day=data.get("rate_limit_per_day"),
                    expires_at=None,  # Not returned in validate response
                    metadata=data.get("metadata"),
                )
            elif response.status_code == 401:
                logger.debug("[API_KEY] Invalid or expired key")
                return None
            else:
                logger.warning(f"[API_KEY] Service returned {response.status_code}")
                return None

    except httpx.TimeoutException:
        logger.warning("[API_KEY] Timeout calling security-service")
        return None
    except Exception as e:
        logger.error(f"[API_KEY] Error validating key: {e}")
        return None


async def get_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> APIKeyInfo | None:
    """
    Get API key info from request (if provided).

    Does NOT raise exception if no key provided.
    Use require_api_key for protected endpoints.
    """
    if not api_key:
        return None

    return await _validate_key_via_service(api_key, request)


def require_api_key(scope: APIKeyScope | None = None):
    """
    Factory for requiring API key authentication.

    Args:
        scope: Optional required scope. If None, any valid key is accepted.

    Usage:
        @app.get("/api/data")
        async def get_data(key: APIKeyInfo = Depends(require_api_key())):
            ...

        @app.post("/api/data")
        async def post_data(key: APIKeyInfo = Depends(require_api_key(APIKeyScope.WRITE))):
            ...
    """
    async def _require_api_key(
        key_info: APIKeyInfo | None = Depends(get_api_key),
    ) -> APIKeyInfo:
        # Bypass if API keys disabled
        if not security_config.api_keys_enabled:
            return APIKeyInfo(
                key_id="dev_bypass",
                name="Development",
                scopes=[APIKeyScope.ADMIN],
                metadata={"bypass": True},
            )

        if not key_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "API-Key"},
            )

        # Check scope
        if scope and not key_info.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scope: {scope.value}",
            )

        return key_info

    return _require_api_key


# Convenience alias
def api_key_required(scope: APIKeyScope | None = None):
    """Alias for require_api_key."""
    return require_api_key(scope)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def generate_api_key(prefix: str = "sk", length: int = 32) -> tuple[str, str]:
    """
    Generate a new API key and its hash.

    This is a utility function for key generation only.
    Storage and management should be handled by the security-service.

    Args:
        prefix: Key prefix (e.g., "sk" for secret key)
        length: Length of the random portion (default: 32)

    Returns:
        Tuple of (raw_key, key_hash):
        - raw_key: The full key to give to the user (e.g., "sk_abc123...")
        - key_hash: SHA-256 hash of the key for storage

    Usage:
        raw_key, key_hash = generate_api_key(prefix="sk")
        # Store key_hash in database
        # Return raw_key to user (shown only once)
    """
    # Generate cryptographically secure random bytes
    random_bytes = secrets.token_bytes(length)
    random_part = secrets.token_urlsafe(length)[:length]

    # Create the full key
    raw_key = f"{prefix}_{random_part}"

    # Create hash for storage
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    """
    Hash an API key for comparison.

    Args:
        raw_key: The raw API key string

    Returns:
        SHA-256 hash of the key
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()
