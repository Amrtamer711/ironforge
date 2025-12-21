"""
Database Router - Selects and exposes the appropriate database backend.

This module provides a unified interface to the database, automatically
selecting the Supabase backend based on environment configuration.

Usage:
    from db.database import db

    # All methods are exposed directly:
    db.create_audit_log(...)
    db.get_api_key_by_hash(...)
    db.get_full_user_context(...)

Configuration:
    For Supabase, set the following environment variables:
    - SECURITY_DEV_SUPABASE_URL / SECURITY_PROD_SUPABASE_URL
    - SECURITY_DEV_SUPABASE_KEY / SECURITY_PROD_SUPABASE_KEY
    - UI_DEV_SUPABASE_URL / UI_PROD_SUPABASE_URL
    - UI_DEV_SUPABASE_KEY / UI_PROD_SUPABASE_KEY
"""

import logging
from typing import Any

from db.base import DatabaseBackend
from db.backends.supabase import SupabaseBackend

logger = logging.getLogger("security-service")


def _get_backend() -> DatabaseBackend:
    """
    Get the configured database backend.

    Returns:
        DatabaseBackend instance (currently only Supabase).
    """
    logger.info("[DB] Using Supabase backend")
    return SupabaseBackend()


# Create the backend instance
_backend = _get_backend()

# Initialize the database
_backend.init_db()


class _DatabaseNamespace:
    """
    Namespace wrapper to expose backend methods as db.method() calls.

    This maintains a clean interface:
        from db.database import db
        db.create_audit_log(...)
    """

    def __init__(self, backend: DatabaseBackend):
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================

    def create_audit_log(
        self,
        actor_type: str,
        service: str,
        action: str,
        actor_id: str | None = None,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str = "success",
        error_message: str | None = None,
        request_id: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        request_body: dict | None = None,
        response_status: int | None = None,
        duration_ms: int | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.create_audit_log(
            actor_type=actor_type,
            service=service,
            action=action,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_ip=actor_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            error_message=error_message,
            request_id=request_id,
            request_method=request_method,
            request_path=request_path,
            request_body=request_body,
            response_status=response_status,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def list_audit_logs(
        self,
        actor_id: str | None = None,
        actor_type: str | None = None,
        service: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return self._backend.list_audit_logs(
            actor_id=actor_id,
            actor_type=actor_type,
            service=service,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def get_audit_log(self, log_id: str) -> dict[str, Any] | None:
        return self._backend.get_audit_log(log_id)

    # =========================================================================
    # API KEYS
    # =========================================================================

    def create_api_key(
        self,
        key_hash: str,
        key_prefix: str,
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
    ) -> dict[str, Any] | None:
        return self._backend.create_api_key(
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

    def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        return self._backend.get_api_key_by_hash(key_hash)

    def get_api_key(self, key_id: str) -> dict[str, Any] | None:
        return self._backend.get_api_key(key_id)

    def list_api_keys(
        self,
        created_by: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return self._backend.list_api_keys(
            created_by=created_by,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

    def update_api_key(
        self,
        key_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._backend.update_api_key(key_id, updates)

    def delete_api_key(self, key_id: str, hard_delete: bool = False) -> bool:
        return self._backend.delete_api_key(key_id, hard_delete)

    def log_api_key_usage(
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
        return self._backend.log_api_key_usage(
            key_id=key_id,
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=duration_ms,
        )

    def get_api_key_usage(
        self,
        key_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        return self._backend.get_api_key_usage(key_id, start_date, end_date)

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    def get_rate_limit_count(
        self,
        key: str,
        window_seconds: int = 60,
    ) -> int:
        return self._backend.get_rate_limit_count(key, window_seconds)

    def increment_rate_limit(
        self,
        key: str,
        window_seconds: int = 60,
        increment: int = 1,
    ) -> int:
        return self._backend.increment_rate_limit(key, window_seconds, increment)

    def cleanup_rate_limits(self) -> int:
        return self._backend.cleanup_rate_limits()

    # =========================================================================
    # SECURITY EVENTS
    # =========================================================================

    def create_security_event(
        self,
        event_type: str,
        severity: str,
        service: str,
        message: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        ip_address: str | None = None,
        details: dict | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.create_security_event(
            event_type=event_type,
            severity=severity,
            service=service,
            message=message,
            actor_type=actor_type,
            actor_id=actor_id,
            ip_address=ip_address,
            details=details,
        )

    def list_security_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        service: str | None = None,
        is_resolved: bool | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return self._backend.list_security_events(
            event_type=event_type,
            severity=severity,
            service=service,
            is_resolved=is_resolved,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def resolve_security_event(
        self,
        event_id: str,
        resolved_by: str,
        resolution_notes: str | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.resolve_security_event(
            event_id, resolved_by, resolution_notes
        )

    # =========================================================================
    # USER LOOKUPS (from UI Supabase - read only)
    # =========================================================================

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._backend.get_user(user_id)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        return self._backend.get_user_profile(user_id)

    def get_user_permissions(self, user_id: str) -> list[str]:
        return self._backend.get_user_permissions(user_id)

    def get_user_teams(self, user_id: str) -> list[dict[str, Any]]:
        return self._backend.get_user_teams(user_id)

    def get_user_subordinates(self, user_id: str) -> list[str]:
        return self._backend.get_user_subordinates(user_id)

    def get_user_companies(self, user_id: str) -> list[str]:
        return self._backend.get_user_companies(user_id)

    def get_full_user_context(self, user_id: str) -> dict[str, Any] | None:
        return self._backend.get_full_user_context(user_id)


# Create the singleton database interface
db = _DatabaseNamespace(_backend)
