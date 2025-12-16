"""
Audit Logging Module.

Provides structured audit logging for tracking security-relevant actions
such as authentication, authorization changes, and data modifications.

Usage:
    from utils.audit import audit_logger, audit_action, AuditAction

    # Direct logging
    await audit_logger.log(
        action=AuditAction.USER_LOGIN,
        user_id="user-123",
        resource_type="session",
        details={"method": "oauth"},
        request=request,
    )

    # Decorator-based logging
    @audit_action(AuditAction.USER_UPDATE, resource_type="user")
    async def update_user(request: Request, user_id: str, ...):
        ...
"""

import functools
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from utils.logging import get_request_id
from utils.time import get_uae_time

logger = logging.getLogger("proposal-bot")


class AuditAction(str, Enum):
    """Predefined audit action types."""
    # Authentication
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_LOGIN_FAILED = "user.login_failed"
    TOKEN_REFRESH = "token.refresh"
    TOKEN_REVOKE = "token.revoke"

    # User Management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ACTIVATE = "user.activate"
    USER_DEACTIVATE = "user.deactivate"

    # Role & Permission Management
    ROLE_CREATE = "role.create"
    ROLE_UPDATE = "role.update"
    ROLE_DELETE = "role.delete"
    ROLE_ASSIGN = "role.assign"
    ROLE_REVOKE = "role.revoke"
    PERMISSION_GRANT = "permission.grant"
    PERMISSION_REVOKE = "permission.revoke"

    # API Keys
    API_KEY_CREATE = "api_key.create"
    API_KEY_UPDATE = "api_key.update"
    API_KEY_ROTATE = "api_key.rotate"
    API_KEY_DELETE = "api_key.delete"
    API_KEY_DEACTIVATE = "api_key.deactivate"

    # Business Data
    PROPOSAL_CREATE = "proposal.create"
    PROPOSAL_UPDATE = "proposal.update"
    PROPOSAL_DELETE = "proposal.delete"

    BOOKING_ORDER_CREATE = "booking_order.create"
    BOOKING_ORDER_UPDATE = "booking_order.update"
    BOOKING_ORDER_DELETE = "booking_order.delete"
    BOOKING_ORDER_APPROVE = "booking_order.approve"
    BOOKING_ORDER_REJECT = "booking_order.reject"

    MOCKUP_CREATE = "mockup.create"
    MOCKUP_UPDATE = "mockup.update"
    MOCKUP_DELETE = "mockup.delete"

    # System
    SETTINGS_UPDATE = "settings.update"
    EXPORT_DATA = "export.data"
    IMPORT_DATA = "import.data"

    # Access Control
    ACCESS_DENIED = "access.denied"
    PERMISSION_CHECK = "permission.check"


@dataclass
class AuditEvent:
    """
    Represents a single audit log event.

    Attributes:
        action: The action that was performed
        user_id: ID of the user who performed the action (None for system actions)
        resource_type: Type of resource affected (e.g., 'user', 'role', 'proposal')
        resource_id: ID of the specific resource affected
        details: Additional context about the action
        ip_address: Client IP address
        user_agent: Client user agent string
        timestamp: When the action occurred
        request_id: Request ID for correlation
    """
    action: str
    user_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = get_uae_time().isoformat()
        if self.request_id is None:
            self.request_id = get_request_id()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "action": self.action,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details_json": json.dumps(self.details) if self.details else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp,
        }


class AuditLogger:
    """
    Audit logger that persists events to the database.

    Features:
    - Async logging to database
    - Request context extraction (IP, user agent)
    - Structured event format
    - Query/filtering support

    Usage:
        from utils.audit import audit_logger

        # Log an event
        await audit_logger.log(
            action=AuditAction.USER_LOGIN,
            user_id="user-123",
            details={"method": "oauth"},
            request=request,
        )

        # Query events
        events = await audit_logger.query(
            user_id="user-123",
            action="user.login",
            limit=100,
        )
    """

    def __init__(self):
        self._db = None

    def _get_db(self):
        """Lazy load database to avoid circular imports."""
        if self._db is None:
            from db.database import db
            self._db = db
        return self._db

    def _extract_request_info(self, request) -> dict[str, Optional[str]]:
        """Extract IP address and user agent from a request object."""
        ip_address = None
        user_agent = None

        if request is not None:
            # Try to get IP from various headers (X-Forwarded-For, X-Real-IP, etc.)
            if hasattr(request, 'headers'):
                ip_address = (
                    request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                    or request.headers.get('X-Real-IP')
                )
                user_agent = request.headers.get('User-Agent')

            # Fall back to client host if available
            if not ip_address and hasattr(request, 'client') and request.client:
                ip_address = request.client.host

        return {
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

    async def log(
        self,
        action: Union[str, AuditAction],
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Log an audit event.

        Args:
            action: The action being logged (AuditAction enum or string)
            user_id: ID of the user performing the action
            resource_type: Type of resource affected
            resource_id: ID of the resource affected
            details: Additional context dictionary
            request: FastAPI Request object (for extracting IP/user agent)
            ip_address: Override IP address
            user_agent: Override user agent
        """
        # Convert enum to string if needed
        if isinstance(action, AuditAction):
            action = action.value

        # Extract request info if provided
        request_info = self._extract_request_info(request)

        # Create the event
        event = AuditEvent(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address or request_info["ip_address"],
            user_agent=user_agent or request_info["user_agent"],
        )

        # Persist to database
        try:
            db = self._get_db()
            db.log_audit_event(
                timestamp=event.timestamp,
                user_id=event.user_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                details_json=json.dumps(event.details) if event.details else None,
                ip_address=event.ip_address,
                user_agent=event.user_agent,
            )

            # Also log to regular logger for immediate visibility
            logger.info(
                f"[AUDIT] {event.action} by user={event.user_id} "
                f"on {event.resource_type}/{event.resource_id}",
                extra={
                    "audit_action": event.action,
                    "audit_user_id": event.user_id,
                    "audit_resource": f"{event.resource_type}/{event.resource_id}",
                }
            )
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.error(f"[AUDIT] Failed to log audit event: {e}")

    def log_sync(
        self,
        action: Union[str, AuditAction],
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Synchronous version of log() for non-async contexts.
        """
        if isinstance(action, AuditAction):
            action = action.value

        request_info = self._extract_request_info(request)

        event = AuditEvent(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address or request_info["ip_address"],
            user_agent=user_agent or request_info["user_agent"],
        )

        try:
            db = self._get_db()
            db.log_audit_event(
                timestamp=event.timestamp,
                user_id=event.user_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                details_json=json.dumps(event.details) if event.details else None,
                ip_address=event.ip_address,
                user_agent=event.user_agent,
            )

            logger.info(
                f"[AUDIT] {event.action} by user={event.user_id} "
                f"on {event.resource_type}/{event.resource_id}"
            )
        except Exception as e:
            logger.error(f"[AUDIT] Failed to log audit event: {e}")

    async def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Query audit log entries.

        Args:
            user_id: Filter by user ID
            action: Filter by action type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of audit log entries
        """
        try:
            db = self._get_db()
            return db.query_audit_log(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            logger.error(f"[AUDIT] Failed to query audit log: {e}")
            return []

    async def get_user_activity(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get recent activity for a specific user."""
        return await self.query(user_id=user_id, limit=limit)

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get audit history for a specific resource."""
        return await self.query(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )


# Global audit logger instance
audit_logger = AuditLogger()


def audit_action(
    action: Union[str, AuditAction],
    resource_type: Optional[str] = None,
    get_resource_id: Optional[Callable] = None,
    get_user_id: Optional[Callable] = None,
    get_details: Optional[Callable] = None,
):
    """
    Decorator to automatically log audit events for endpoint functions.

    Args:
        action: The action type to log
        resource_type: Type of resource being affected
        get_resource_id: Callable to extract resource ID from function args
                        Default: looks for 'resource_id', 'id', or '<resource_type>_id'
        get_user_id: Callable to extract user ID from function args
                    Default: looks for current_user or user_id in request state
        get_details: Callable to extract additional details from function args

    Usage:
        @audit_action(AuditAction.USER_UPDATE, resource_type="user")
        async def update_user(request: Request, user_id: str, current_user: AuthUser):
            ...

        @audit_action(
            AuditAction.ROLE_ASSIGN,
            resource_type="user",
            get_resource_id=lambda kw: kw.get('user_id'),
            get_details=lambda kw: {"role": kw.get('role_name')},
        )
        async def assign_role(request: Request, user_id: str, role_name: str):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract request object
            request = kwargs.get('request')
            if request is None:
                for arg in args:
                    if hasattr(arg, 'headers') and hasattr(arg, 'client'):
                        request = arg
                        break

            # Extract user ID
            user_id = None
            if get_user_id:
                user_id = get_user_id(kwargs)
            else:
                # Try common patterns
                current_user = kwargs.get('current_user')
                if current_user and hasattr(current_user, 'id'):
                    user_id = current_user.id
                elif request and hasattr(request, 'state'):
                    user = getattr(request.state, 'user', None)
                    if user and hasattr(user, 'id'):
                        user_id = user.id

            # Extract resource ID
            resource_id = None
            if get_resource_id:
                resource_id = get_resource_id(kwargs)
            else:
                # Try common patterns
                resource_id = (
                    kwargs.get('resource_id')
                    or kwargs.get('id')
                    or kwargs.get(f'{resource_type}_id' if resource_type else '')
                )

            # Convert to string if needed
            if resource_id is not None:
                resource_id = str(resource_id)

            # Extract details
            details = {}
            if get_details:
                details = get_details(kwargs) or {}

            # Execute the function
            try:
                result = await func(*args, **kwargs)
                details['success'] = True
            except Exception as e:
                details['success'] = False
                details['error'] = str(e)
                raise
            finally:
                # Log the audit event
                await audit_logger.log(
                    action=action,
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details,
                    request=request,
                )

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar logic but for sync functions
            request = kwargs.get('request')
            if request is None:
                for arg in args:
                    if hasattr(arg, 'headers') and hasattr(arg, 'client'):
                        request = arg
                        break

            user_id = None
            if get_user_id:
                user_id = get_user_id(kwargs)
            else:
                current_user = kwargs.get('current_user')
                if current_user and hasattr(current_user, 'id'):
                    user_id = current_user.id

            resource_id = None
            if get_resource_id:
                resource_id = get_resource_id(kwargs)
            else:
                resource_id = (
                    kwargs.get('resource_id')
                    or kwargs.get('id')
                    or kwargs.get(f'{resource_type}_id' if resource_type else '')
                )

            if resource_id is not None:
                resource_id = str(resource_id)

            details = {}
            if get_details:
                details = get_details(kwargs) or {}

            try:
                result = func(*args, **kwargs)
                details['success'] = True
            except Exception as e:
                details['success'] = False
                details['error'] = str(e)
                raise
            finally:
                audit_logger.log_sync(
                    action=action,
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details,
                    request=request,
                )

            return result

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
