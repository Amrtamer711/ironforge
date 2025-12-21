"""
API Key Management Service.

Handles API key creation, validation, and lifecycle management.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime
from typing import Any

from db import db
from models.api_keys import APIKeyScope, APIKeyInfo

logger = logging.getLogger("security-service")


def _hash_key(key: str) -> str:
    """Hash an API key for storage/comparison using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKeyService:
    """
    API key management service.

    Handles creation, validation, and lifecycle management of API keys.
    Keys are stored hashed in Security Supabase.
    """

    # =========================================================================
    # KEY GENERATION
    # =========================================================================

    def generate_key(
        self,
        name: str,
        scopes: list[str],
        created_by: str | None = None,
        description: str | None = None,
        allowed_services: list[str] | None = None,
        allowed_ips: list[str] | None = None,
        rate_limit_per_minute: int = 100,
        rate_limit_per_day: int = 10000,
        expires_at: str | None = None,
        metadata: dict | None = None,
        prefix: str = "sk",
    ) -> dict[str, Any]:
        """
        Generate a new API key.

        Args:
            name: Human-readable name for the key
            scopes: List of scopes (e.g., ["read", "write"])
            created_by: User ID who created the key
            description: Optional description
            allowed_services: Optional list of services key can access
            allowed_ips: Optional list of allowed IP addresses
            rate_limit_per_minute: Requests per minute limit
            rate_limit_per_day: Requests per day limit
            expires_at: Optional expiration date (ISO format)
            metadata: Optional additional metadata
            prefix: Key prefix (default "sk")

        Returns:
            {
                "key": Raw API key (SHOW ONCE),
                "key_id": Database ID of the key,
                "key_prefix": First 8 chars for identification,
                "name": Key name,
                "scopes": Key scopes
            }
        """
        # Generate random key
        random_part = secrets.token_hex(32)
        raw_key = f"{prefix}_{random_part}"
        key_hash = _hash_key(raw_key)
        key_prefix = raw_key[:12]  # sk_ + first 8 chars

        # Store in database
        record = db.create_api_key(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes,
            created_by=created_by,
            description=description,
            allowed_services=allowed_services,
            allowed_ips=allowed_ips,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_day=rate_limit_per_day,
            expires_at=expires_at,
            metadata=metadata,
        )

        if not record:
            raise RuntimeError("Failed to create API key")

        logger.info(f"[API_KEY] Created key '{name}' with prefix {key_prefix}")

        return {
            "key": raw_key,  # Only returned once!
            "key_id": record.get("id"),
            "key_prefix": key_prefix,
            "name": name,
            "scopes": scopes,
        }

    # =========================================================================
    # KEY VALIDATION
    # =========================================================================

    def validate_key(
        self,
        raw_key: str,
        required_scope: str | None = None,
        service: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """
        Validate an API key.

        Args:
            raw_key: The raw API key to validate
            required_scope: Optional scope that must be present
            service: Optional service the key must be allowed to access
            client_ip: Optional client IP for IP whitelist check

        Returns:
            {
                "valid": bool,
                "key_info": APIKeyInfo if valid,
                "error": Error message if invalid
            }
        """
        if not raw_key:
            return {"valid": False, "error": "No API key provided"}

        # Hash the key
        key_hash = _hash_key(raw_key)

        # Look up in database
        record = db.get_api_key_by_hash(key_hash)

        if not record:
            logger.warning(f"[API_KEY] Invalid key attempted")
            return {"valid": False, "error": "Invalid API key"}

        # Use constant-time comparison for security
        stored_hash = record.get("key_hash", "")
        if not hmac.compare_digest(key_hash, stored_hash):
            return {"valid": False, "error": "Invalid API key"}

        # Check if active
        if not record.get("is_active", False):
            logger.warning(f"[API_KEY] Inactive key used: {record.get('id')}")
            return {"valid": False, "error": "API key is inactive"}

        # Check expiration
        expires_at = record.get("expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp_dt < datetime.utcnow().replace(tzinfo=exp_dt.tzinfo):
                    logger.warning(f"[API_KEY] Expired key used: {record.get('id')}")
                    return {"valid": False, "error": "API key expired"}
            except (ValueError, TypeError):
                pass

        # Check scope if required
        scopes = record.get("scopes", [])
        if required_scope:
            if not self._has_scope(scopes, required_scope):
                logger.warning(
                    f"[API_KEY] Key {record.get('id')} lacks scope: {required_scope}"
                )
                return {"valid": False, "error": f"Missing scope: {required_scope}"}

        # Check service whitelist
        allowed_services = record.get("allowed_services")
        if allowed_services and service:
            if service not in allowed_services:
                logger.warning(
                    f"[API_KEY] Key {record.get('id')} not allowed for service: {service}"
                )
                return {"valid": False, "error": f"Key not allowed for service: {service}"}

        # Check IP whitelist
        allowed_ips = record.get("allowed_ips")
        if allowed_ips and client_ip:
            if client_ip not in allowed_ips:
                logger.warning(
                    f"[API_KEY] Key {record.get('id')} not allowed from IP: {client_ip}"
                )
                return {"valid": False, "error": "IP not allowed"}

        # Build key info
        key_info = APIKeyInfo(
            id=record.get("id"),
            name=record.get("name"),
            key_prefix=record.get("key_prefix"),
            scopes=[APIKeyScope(s) for s in scopes if s in [e.value for e in APIKeyScope]],
            rate_limit_per_minute=record.get("rate_limit_per_minute", 100),
            rate_limit_per_day=record.get("rate_limit_per_day", 10000),
            is_active=True,
            created_at=record.get("created_at"),
            expires_at=record.get("expires_at"),
            metadata=record.get("metadata", {}),
        )

        return {
            "valid": True,
            "key_info": key_info,
        }

    def _has_scope(self, scopes: list[str], required: str) -> bool:
        """Check if scopes include the required scope."""
        # Admin implies all scopes
        if "admin" in scopes:
            return True
        # Write implies read
        if required == "read" and "write" in scopes:
            return True
        return required in scopes

    # =========================================================================
    # KEY MANAGEMENT
    # =========================================================================

    def get_key(self, key_id: str) -> dict[str, Any] | None:
        """Get API key record by ID (excludes hash)."""
        record = db.get_api_key(key_id)
        if record:
            # Remove sensitive data
            record.pop("key_hash", None)
        return record

    def list_keys(
        self,
        created_by: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List API keys with filters.

        Returns:
            Tuple of (list of keys without hashes, total count)
        """
        keys, total = db.list_api_keys(
            created_by=created_by,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

        # Remove sensitive data
        for key in keys:
            key.pop("key_hash", None)

        return keys, total

    def update_key(
        self,
        key_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update an API key.

        Allowed updates: name, description, scopes, allowed_services,
        allowed_ips, rate_limit_per_minute, rate_limit_per_day, is_active,
        expires_at, metadata
        """
        # Filter to allowed updates
        allowed_fields = {
            "name", "description", "scopes", "allowed_services",
            "allowed_ips", "rate_limit_per_minute", "rate_limit_per_day",
            "is_active", "expires_at", "metadata"
        }
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return None

        record = db.update_api_key(key_id, filtered_updates)
        if record:
            record.pop("key_hash", None)
        return record

    def revoke_key(self, key_id: str) -> bool:
        """Revoke (soft delete) an API key."""
        logger.info(f"[API_KEY] Revoking key {key_id}")
        return db.delete_api_key(key_id, hard_delete=False)

    def delete_key(self, key_id: str) -> bool:
        """Permanently delete an API key."""
        logger.warning(f"[API_KEY] Permanently deleting key {key_id}")
        return db.delete_api_key(key_id, hard_delete=True)

    # =========================================================================
    # USAGE TRACKING
    # =========================================================================

    def log_usage(
        self,
        key_id: str,
        service: str,
        endpoint: str,
        method: str,
        status_code: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Log API key usage for analytics."""
        db.log_api_key_usage(
            key_id=key_id,
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=duration_ms,
        )

    def get_usage(
        self,
        key_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get API key usage statistics."""
        return db.get_api_key_usage(key_id, start_date, end_date)


# Singleton instance
api_key_service = APIKeyService()
