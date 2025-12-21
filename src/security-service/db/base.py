"""
Abstract base class for database backends.

Each backend implements their own storage-specific syntax.
Follows the same pattern as asset-management/db/base.py.
"""

from abc import ABC, abstractmethod
from typing import Any


class DatabaseBackend(ABC):
    """
    Abstract base class for security database backends.

    Each backend (Supabase, etc.) implements this interface
    with their own storage-specific syntax.

    Pattern follows:
    - asset-management/db/base.py
    - sales-module/db/base.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g., 'supabase')."""
        pass

    @abstractmethod
    def init_db(self) -> None:
        """Initialize database connections."""
        pass

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================

    @abstractmethod
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
        """
        Create an audit log entry.

        Args:
            actor_type: 'user', 'service', 'system', 'anonymous'
            service: Service name (e.g., 'sales-module')
            action: Action performed (e.g., 'create', 'read', 'update', 'delete')
            actor_id: User ID or service name
            actor_email: Email (for user actors)
            actor_ip: IP address
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            result: 'success', 'denied', 'error'
            error_message: Error message if result is 'error'
            request_id: Correlation ID
            request_method: HTTP method
            request_path: Request path
            request_body: Sanitized request body
            response_status: HTTP status code
            duration_ms: Request duration
            metadata: Additional metadata

        Returns:
            Created audit log record or None
        """
        pass

    @abstractmethod
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
        """
        List audit logs with filters.

        Returns:
            Tuple of (list of audit log records, total count)
        """
        pass

    @abstractmethod
    def get_audit_log(self, log_id: str) -> dict[str, Any] | None:
        """Get a single audit log by ID."""
        pass

    # =========================================================================
    # API KEYS
    # =========================================================================

    @abstractmethod
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
        """
        Create a new API key record.

        Args:
            key_hash: SHA-256 hash of the API key
            key_prefix: First 8 chars for identification
            name: Human-readable name
            scopes: List of scopes ['read', 'write', 'admin']
            created_by: User ID who created
            description: Optional description
            allowed_services: Services this key can access (None = all)
            allowed_ips: IPs this key can be used from (None = all)
            rate_limit_per_minute: Rate limit per minute
            rate_limit_per_day: Rate limit per day
            expires_at: Optional expiration datetime
            metadata: Additional metadata

        Returns:
            Created API key record (without the actual key)
        """
        pass

    @abstractmethod
    def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Get an API key record by its hash."""
        pass

    @abstractmethod
    def get_api_key(self, key_id: str) -> dict[str, Any] | None:
        """Get an API key record by ID."""
        pass

    @abstractmethod
    def list_api_keys(
        self,
        created_by: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List API keys with filters.

        Returns:
            Tuple of (list of API key records, total count)
        """
        pass

    @abstractmethod
    def update_api_key(
        self,
        key_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an API key."""
        pass

    @abstractmethod
    def delete_api_key(self, key_id: str, hard_delete: bool = False) -> bool:
        """Delete an API key (soft delete by default)."""
        pass

    @abstractmethod
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
        """Log API key usage for analytics."""
        pass

    @abstractmethod
    def get_api_key_usage(
        self,
        key_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get API key usage statistics."""
        pass

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    @abstractmethod
    def get_rate_limit_count(
        self,
        key: str,
        window_seconds: int = 60,
    ) -> int:
        """
        Get current request count for a rate limit key.

        Args:
            key: Rate limit key (e.g., "user:123:endpoint:/api/data")
            window_seconds: Window size in seconds

        Returns:
            Current request count in the window
        """
        pass

    @abstractmethod
    def increment_rate_limit(
        self,
        key: str,
        window_seconds: int = 60,
        increment: int = 1,
    ) -> int:
        """
        Increment rate limit counter and return new count.

        Args:
            key: Rate limit key
            window_seconds: Window size in seconds
            increment: Amount to increment

        Returns:
            New request count after increment
        """
        pass

    @abstractmethod
    def cleanup_rate_limits(self) -> int:
        """
        Clean up expired rate limit windows.

        Returns:
            Number of records cleaned up
        """
        pass

    # =========================================================================
    # SECURITY EVENTS
    # =========================================================================

    @abstractmethod
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
        """
        Create a security event.

        Args:
            event_type: 'failed_login', 'rate_limit_exceeded', 'invalid_token', etc.
            severity: 'info', 'warning', 'error', 'critical'
            service: Service name
            message: Human-readable message
            actor_type: Type of actor
            actor_id: Actor identifier
            ip_address: IP address
            details: Additional details

        Returns:
            Created security event record
        """
        pass

    @abstractmethod
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
        """List security events with filters."""
        pass

    @abstractmethod
    def resolve_security_event(
        self,
        event_id: str,
        resolved_by: str,
        resolution_notes: str | None = None,
    ) -> dict[str, Any] | None:
        """Mark a security event as resolved."""
        pass

    # =========================================================================
    # USER LOOKUPS (from UI Supabase - read only)
    # =========================================================================

    @abstractmethod
    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Get user info from UI Supabase."""
        pass

    @abstractmethod
    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user's RBAC profile from UI Supabase."""
        pass

    @abstractmethod
    def get_user_permissions(self, user_id: str) -> list[str]:
        """Get user's combined permissions from UI Supabase."""
        pass

    @abstractmethod
    def get_user_teams(self, user_id: str) -> list[dict[str, Any]]:
        """Get user's teams from UI Supabase."""
        pass

    @abstractmethod
    def get_user_subordinates(self, user_id: str) -> list[str]:
        """Get user's subordinate IDs from UI Supabase."""
        pass

    @abstractmethod
    def get_user_companies(self, user_id: str) -> list[str]:
        """Get user's accessible company schemas from UI Supabase."""
        pass

    @abstractmethod
    def get_full_user_context(self, user_id: str) -> dict[str, Any] | None:
        """
        Get complete user context for RBAC.

        Returns all 5 levels of RBAC data:
        - Level 1: Profile
        - Level 2: Permission sets
        - Level 3: Teams & hierarchy
        - Level 4: Sharing rules
        - Level 5: Companies

        Returns:
            Full user context dict or None if user not found
        """
        pass
