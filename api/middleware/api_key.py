"""
API Key Authentication Middleware.

Provides API key validation for external API access. API keys are separate
from user JWT authentication and used for:
- Service-to-service communication
- External integrations
- Programmatic API access

Usage:
    from api.middleware import require_api_key, APIKeyScope

    # Require any valid API key
    @app.get("/api/external/data")
    async def get_data(api_key: APIKeyInfo = Depends(require_api_key)):
        return {"client": api_key.client_name}

    # Require API key with specific scope
    @app.post("/api/external/write")
    async def write_data(api_key: APIKeyInfo = Depends(require_api_key(APIKeyScope.WRITE))):
        return {"client": api_key.client_name}

Configuration:
    API keys are configured via environment variables or database.
    Set API_KEYS_ENABLED=true to enable enforcement.
"""

import hashlib
import hmac
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from utils.logging import get_logger
from utils.time import get_uae_time

logger = get_logger("api.middleware.api_key")


class APIKeyScope(str, Enum):
    """API key access scopes."""
    READ = "read"           # Read-only access
    WRITE = "write"         # Read and write access
    ADMIN = "admin"         # Full admin access
    PROPOSALS = "proposals" # Proposals-specific access
    MOCKUPS = "mockups"     # Mockups-specific access


@dataclass
class APIKeyInfo:
    """Information about a validated API key."""
    key_id: str
    client_name: str
    scopes: list[APIKeyScope]
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    rate_limit: Optional[int] = None  # Requests per minute
    metadata: Optional[dict] = None

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if key has a specific scope."""
        # Admin scope implies all other scopes
        if APIKeyScope.ADMIN in self.scopes:
            return True
        # Write scope implies read
        if scope == APIKeyScope.READ and APIKeyScope.WRITE in self.scopes:
            return True
        return scope in self.scopes


# API key header scheme
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(key: str) -> str:
    """Hash an API key for storage/comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(prefix: str = "sk") -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (raw_key, hashed_key)
        The raw key should be shown to the user once,
        the hashed key should be stored.
    """
    # Generate 32 random bytes -> 64 hex chars
    random_part = secrets.token_hex(32)
    raw_key = f"{prefix}_{random_part}"
    hashed = _hash_key(raw_key)
    return raw_key, hashed


class APIKeyStore:
    """
    Abstract base for API key storage.

    Subclasses implement storage-specific retrieval.
    """

    async def get_key_info(self, key_hash: str) -> Optional[APIKeyInfo]:
        """Retrieve key info by hash."""
        raise NotImplementedError

    async def validate_key(self, raw_key: str) -> Optional[APIKeyInfo]:
        """Validate a raw API key and return its info."""
        key_hash = _hash_key(raw_key)
        return await self.get_key_info(key_hash)

    async def log_usage(self, key_id: str, endpoint: str, status_code: int) -> None:
        """Log API key usage for auditing."""
        pass


class EnvAPIKeyStore(APIKeyStore):
    """
    API key store backed by environment variables.

    For simple deployments where keys are configured via env vars.

    Environment variables:
        API_KEY_<name>_KEY: The raw API key
        API_KEY_<name>_SCOPES: Comma-separated scopes (read,write,admin)
        API_KEY_<name>_RATE_LIMIT: Optional rate limit (requests/minute)

    Example:
        API_KEY_FRONTEND_KEY=sk_abc123...
        API_KEY_FRONTEND_SCOPES=read,write
        API_KEY_BACKEND_KEY=sk_xyz789...
        API_KEY_BACKEND_SCOPES=admin
    """

    def __init__(self):
        self._keys: dict[str, APIKeyInfo] = {}
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load API keys from environment variables."""
        prefix = "API_KEY_"

        # Find all API key names from env vars
        key_names = set()
        for var_name in os.environ:
            if var_name.startswith(prefix) and var_name.endswith("_KEY"):
                name = var_name[len(prefix):-4]  # Remove prefix and _KEY suffix
                key_names.add(name)

        for name in key_names:
            raw_key = os.getenv(f"{prefix}{name}_KEY", "")
            if not raw_key:
                continue

            # Parse scopes
            scopes_str = os.getenv(f"{prefix}{name}_SCOPES", "read")
            scopes = []
            for scope_name in scopes_str.split(","):
                scope_name = scope_name.strip().lower()
                try:
                    scopes.append(APIKeyScope(scope_name))
                except ValueError:
                    logger.warning(f"[API_KEY] Unknown scope '{scope_name}' for key {name}")

            # Parse rate limit
            rate_limit_str = os.getenv(f"{prefix}{name}_RATE_LIMIT", "")
            rate_limit = int(rate_limit_str) if rate_limit_str.isdigit() else None

            # Hash and store
            key_hash = _hash_key(raw_key)
            self._keys[key_hash] = APIKeyInfo(
                key_id=f"env_{name.lower()}",
                client_name=name,
                scopes=scopes or [APIKeyScope.READ],
                rate_limit=rate_limit,
                metadata={"source": "environment"},
            )

        if self._keys:
            logger.info(f"[API_KEY] Loaded {len(self._keys)} API keys from environment")

    async def get_key_info(self, key_hash: str) -> Optional[APIKeyInfo]:
        """Retrieve key info by hash with constant-time comparison."""
        # Use constant-time comparison to prevent timing attacks
        for stored_hash, key_info in self._keys.items():
            if hmac.compare_digest(key_hash, stored_hash):
                return key_info
        return None


class DatabaseAPIKeyStore(APIKeyStore):
    """
    API key store backed by database.

    For production deployments where keys are managed via API/admin UI.
    Supports key creation, rotation, deactivation, and usage logging.
    """

    def __init__(self):
        from db.database import db
        self._db = db
        logger.info("[API_KEY] Using database-backed API key store")

    async def get_key_info(self, key_hash: str) -> Optional[APIKeyInfo]:
        """Retrieve key info by hash with constant-time comparison."""
        record = self._db.get_api_key_by_hash(key_hash)
        if not record:
            return None

        # Constant-time comparison to prevent timing attacks
        stored_hash = record.get("key_hash", "")
        if not hmac.compare_digest(key_hash, stored_hash):
            return None

        # Check if active
        if not record.get("is_active"):
            return None

        # Parse scopes
        scopes = []
        for scope_str in record.get("scopes", []):
            try:
                scopes.append(APIKeyScope(scope_str))
            except ValueError:
                logger.warning(f"[API_KEY] Unknown scope '{scope_str}' in key {record['id']}")

        # Parse dates
        created_at = None
        expires_at = None
        last_used_at = None

        if record.get("created_at"):
            try:
                created_at = datetime.fromisoformat(record["created_at"])
            except (ValueError, TypeError):
                pass

        if record.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(record["expires_at"])
            except (ValueError, TypeError):
                pass

        if record.get("last_used_at"):
            try:
                last_used_at = datetime.fromisoformat(record["last_used_at"])
            except (ValueError, TypeError):
                pass

        return APIKeyInfo(
            key_id=str(record["id"]),
            client_name=record["name"],
            scopes=scopes or [APIKeyScope.READ],
            created_at=created_at,
            expires_at=expires_at,
            last_used_at=last_used_at,
            rate_limit=record.get("rate_limit"),
            metadata=record.get("metadata", {"source": "database"}),
        )

    async def log_usage(self, key_id: str, endpoint: str, status_code: int) -> None:
        """Log API key usage for auditing."""
        try:
            self._db.log_api_key_usage(
                api_key_id=int(key_id),
                endpoint=endpoint,
                method="",  # Will be populated by middleware if needed
                status_code=status_code,
            )
            # Update last_used_at
            self._db.update_api_key_last_used(
                int(key_id),
                get_uae_time().isoformat(),
            )
        except Exception as e:
            logger.warning(f"[API_KEY] Failed to log usage: {e}")


class CombinedAPIKeyStore(APIKeyStore):
    """
    Combined store that checks both environment and database.

    Tries environment first (for quick lookups), then database.
    This allows env-based keys for simple setups while supporting
    database keys for production.
    """

    def __init__(self):
        self._env_store = EnvAPIKeyStore()
        self._db_store: Optional[DatabaseAPIKeyStore] = None
        self._db_initialized = False

    def _get_db_store(self) -> Optional[DatabaseAPIKeyStore]:
        """Lazy-load database store."""
        if not self._db_initialized:
            self._db_initialized = True
            try:
                self._db_store = DatabaseAPIKeyStore()
            except Exception as e:
                logger.warning(f"[API_KEY] Failed to initialize database store: {e}")
                self._db_store = None
        return self._db_store

    async def get_key_info(self, key_hash: str) -> Optional[APIKeyInfo]:
        """Check env first, then database."""
        # Try environment
        key_info = await self._env_store.get_key_info(key_hash)
        if key_info:
            return key_info

        # Try database
        db_store = self._get_db_store()
        if db_store:
            return await db_store.get_key_info(key_hash)

        return None

    async def log_usage(self, key_id: str, endpoint: str, status_code: int) -> None:
        """Log usage for database keys."""
        # Only log for database keys (numeric IDs)
        if key_id.isdigit():
            db_store = self._get_db_store()
            if db_store:
                await db_store.log_usage(key_id, endpoint, status_code)


# Global store instance
_store: Optional[APIKeyStore] = None


def _get_store() -> APIKeyStore:
    """Get or create the API key store."""
    global _store
    if _store is None:
        from app_settings import settings

        store_type = settings.api_key_store

        if store_type == "database":
            _store = DatabaseAPIKeyStore()
        elif store_type == "env":
            _store = EnvAPIKeyStore()
        else:
            _store = CombinedAPIKeyStore()

        logger.info(f"[API_KEY] Using {store_type} API key store")
    return _store


def set_api_key_store(store: APIKeyStore) -> None:
    """Set a custom API key store (for testing)."""
    global _store
    _store = store


async def get_api_key(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> Optional[APIKeyInfo]:
    """
    Get API key info from request (if provided).

    This dependency does NOT raise an exception if no key is provided.
    Use require_api_key for protected endpoints.

    Returns:
        APIKeyInfo if valid key provided, None otherwise
    """
    if not api_key:
        return None

    store = _get_store()
    key_info = await store.validate_key(api_key)

    if key_info:
        # Check expiration
        if key_info.expires_at and key_info.expires_at < get_uae_time():
            logger.warning(f"[API_KEY] Expired key used: {key_info.key_id}")
            return None

        # Log usage
        await store.log_usage(
            key_info.key_id,
            str(request.url.path),
            200,  # Preliminary - actual status logged later
        )

    return key_info


def require_api_key(scope: Optional[APIKeyScope] = None) -> Callable:
    """
    Factory for requiring API key authentication.

    Args:
        scope: Optional required scope. If None, any valid key is accepted.

    Usage:
        # Any valid API key
        @app.get("/api/data")
        async def get_data(key: APIKeyInfo = Depends(require_api_key())):
            ...

        # Require write scope
        @app.post("/api/data")
        async def post_data(key: APIKeyInfo = Depends(require_api_key(APIKeyScope.WRITE))):
            ...
    """
    async def _require_api_key(
        key_info: Optional[APIKeyInfo] = Depends(get_api_key),
    ) -> APIKeyInfo:
        # Check if API keys are enabled
        api_keys_enabled = os.getenv("API_KEYS_ENABLED", "false").lower() == "true"

        if not api_keys_enabled:
            # Return a mock key for development
            return APIKeyInfo(
                key_id="dev_bypass",
                client_name="Development",
                scopes=[APIKeyScope.ADMIN],
                metadata={"bypass": True},
            )

        if not key_info:
            logger.warning("[API_KEY] Request without valid API key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "API-Key"},
            )

        # Check scope if required
        if scope and not key_info.has_scope(scope):
            logger.warning(
                f"[API_KEY] Key {key_info.key_id} lacks scope: {scope.value}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scope: {scope.value}",
            )

        return key_info

    return _require_api_key


# Convenience function for simple usage
def api_key_required(
    key_info: Optional[APIKeyInfo] = Depends(get_api_key),
) -> APIKeyInfo:
    """Simple dependency that requires any valid API key."""
    return require_api_key()(key_info)
