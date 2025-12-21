"""
Audit Logging Service.

Handles structured audit logging for compliance and security monitoring.
"""

import logging
from typing import Any

from db import db
from models.audit import AuditAction, AuditResult, ActorType

logger = logging.getLogger("security-service")


class AuditService:
    """
    Audit logging service for compliance-ready event tracking.

    All audit events are written to Security Supabase for centralized logging.
    """

    def __init__(self):
        self._service_name = "security-service"

    # =========================================================================
    # EVENT LOGGING
    # =========================================================================

    def log_event(
        self,
        actor_type: str | ActorType,
        service: str,
        action: str | AuditAction,
        actor_id: str | None = None,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str | AuditResult = "success",
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
        Log an audit event.

        Args:
            actor_type: Type of actor ('user', 'service', 'system', 'anonymous')
            service: Service that generated the event
            action: Action performed (e.g., 'create', 'read', 'update', 'delete')
            actor_id: ID of the actor (user ID or service name)
            actor_email: Email of the user actor
            actor_ip: IP address of the client
            resource_type: Type of resource affected
            resource_id: ID of the specific resource
            result: Result of the action ('success', 'denied', 'error')
            error_message: Error message if result is 'error'
            request_id: Correlation ID for the request
            request_method: HTTP method
            request_path: Request path
            request_body: Sanitized request body (no secrets)
            response_status: HTTP response status code
            duration_ms: Request duration in milliseconds
            metadata: Additional context data

        Returns:
            Created audit log record or None if failed
        """
        # Convert enums to strings
        if isinstance(actor_type, ActorType):
            actor_type = actor_type.value
        if isinstance(action, AuditAction):
            action = action.value
        if isinstance(result, AuditResult):
            result = result.value

        # Log locally first
        log_msg = (
            f"[AUDIT] {actor_type}:{actor_id or 'unknown'} "
            f"{action} {resource_type or ''}:{resource_id or ''} "
            f"-> {result}"
        )
        if result == "success":
            logger.info(log_msg)
        elif result == "denied":
            logger.warning(log_msg)
        else:
            logger.error(log_msg)

        # Write to database
        return db.create_audit_log(
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

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def log_access_denied(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str | None = None,
        permission: str | None = None,
        request_ip: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Log an access denied event."""
        self.log_event(
            actor_type="user",
            actor_id=user_id,
            service=self._service_name,
            action="access_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            result="denied",
            actor_ip=request_ip,
            request_id=request_id,
            metadata={"permission_required": permission} if permission else None,
        )

    def log_login_success(
        self,
        user_id: str,
        user_email: str,
        request_ip: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Log a successful login."""
        self.log_event(
            actor_type="user",
            actor_id=user_id,
            actor_email=user_email,
            actor_ip=request_ip,
            service=self._service_name,
            action="login",
            resource_type="session",
            result="success",
            metadata=metadata,
        )

    def log_login_failed(
        self,
        email: str | None = None,
        request_ip: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Log a failed login attempt."""
        self.log_event(
            actor_type="anonymous",
            actor_email=email,
            actor_ip=request_ip,
            service=self._service_name,
            action="login_failed",
            resource_type="session",
            result="error",
            error_message=reason,
            metadata={"email": email} if email else None,
        )

    def log_api_key_used(
        self,
        key_id: str,
        key_name: str,
        service: str,
        endpoint: str,
        request_ip: str | None = None,
    ) -> None:
        """Log API key usage."""
        self.log_event(
            actor_type="service",
            actor_id=key_id,
            service=service,
            action="api_key_used",
            resource_type="api_key",
            resource_id=key_id,
            result="success",
            actor_ip=request_ip,
            metadata={"key_name": key_name, "endpoint": endpoint},
        )

    # =========================================================================
    # QUERY
    # =========================================================================

    def list_events(
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
        Query audit logs with filters.

        Returns:
            Tuple of (list of events, total count)
        """
        return db.list_audit_logs(
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

    def get_event(self, log_id: str) -> dict[str, Any] | None:
        """Get a single audit log by ID."""
        return db.get_audit_log(log_id)


# Singleton instance
audit_service = AuditService()
