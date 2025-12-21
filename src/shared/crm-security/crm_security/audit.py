"""
Audit Logging SDK Client.

Sends audit events to the security-service via HTTP.
All persistence is handled by the security-service.

Usage:
    from crm_security import audit_log, audit

    # Direct logging (fire-and-forget async)
    await audit_log(
        actor_type="user",
        actor_id="user-123",
        action="create",
        resource_type="proposal",
        resource_id="PROP-001",
    )

    # Decorator-based logging
    @audit(action="create", resource_type="proposal")
    async def create_proposal(user: UserContext, data: ProposalCreate):
        ...
"""

import asyncio
import functools
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

import httpx

from .config import security_config

logger = logging.getLogger(__name__)


# Request ID context
_request_id_var: str | None = None


def get_request_id() -> str:
    """Get current request ID or generate one."""
    global _request_id_var
    if _request_id_var:
        return _request_id_var
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """Set current request ID."""
    global _request_id_var
    _request_id_var = request_id


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

    # Assets
    NETWORK_CREATE = "network.create"
    NETWORK_UPDATE = "network.update"
    NETWORK_DELETE = "network.delete"
    LOCATION_CREATE = "location.create"
    LOCATION_UPDATE = "location.update"
    LOCATION_DELETE = "location.delete"
    PACKAGE_CREATE = "package.create"
    PACKAGE_UPDATE = "package.update"
    PACKAGE_DELETE = "package.delete"

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


class AuditClient:
    """
    HTTP client for sending audit logs to security-service.

    All writes are fire-and-forget async to avoid blocking the main request.
    """

    def __init__(self, service_name: str | None = None):
        self._service_name = service_name or security_config.service_name
        self._base_url = security_config.security_service_url
        self._timeout = 5.0  # Short timeout for audit logs

    def _get_headers(self) -> dict[str, str]:
        """Get headers for security-service authentication."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": self._service_name,
        }
        if security_config.service_api_secret:
            headers["X-Service-Secret"] = security_config.service_api_secret
        return headers

    def _extract_request_info(self, request: Any) -> dict[str, str | None]:
        """Extract IP address and user agent from a request object."""
        ip_address = None
        user_agent = None

        if request is not None:
            if hasattr(request, 'headers'):
                ip_address = (
                    request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                    or request.headers.get('X-Real-IP')
                )
                user_agent = request.headers.get('User-Agent')

            if not ip_address and hasattr(request, 'client') and request.client:
                ip_address = request.client.host

        return {"ip_address": ip_address, "user_agent": user_agent}

    async def log(
        self,
        action: str | AuditAction,
        actor_type: str = "user",
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
        response_status: int | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
        request: Any | None = None,
    ) -> None:
        """
        Log an audit event to security-service (async, fire-and-forget).

        Args:
            action: The action being logged
            actor_type: 'user', 'service', 'system', or 'anonymous'
            actor_id: ID of the actor (user ID or service name)
            actor_email: Email of the actor (for users)
            actor_ip: IP address (extracted from request if not provided)
            resource_type: Type of resource affected
            resource_id: ID of the resource affected
            result: 'success', 'denied', or 'error'
            error_message: Error message if result is 'error'
            request_id: Request correlation ID
            request_method: HTTP method
            request_path: Request path
            response_status: HTTP response status code
            duration_ms: Request duration in milliseconds
            metadata: Additional context
            request: FastAPI Request object for auto-extracting IP/user-agent
        """
        if not security_config.audit_enabled:
            return

        # Convert enum to string
        if isinstance(action, AuditAction):
            action = action.value

        # Extract request info
        request_info = self._extract_request_info(request)
        actor_ip = actor_ip or request_info["ip_address"]

        # Build payload
        payload = {
            "action": action,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "actor_ip": actor_ip,
            "service": self._service_name,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "result": result,
            "error_message": error_message,
            "request_id": request_id or get_request_id(),
            "request_method": request_method,
            "request_path": request_path,
            "response_status": response_status,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Always log locally
        logger.info(
            f"[AUDIT] {action} by {actor_type}:{actor_id or 'unknown'} "
            f"on {resource_type or '-'}/{resource_id or '-'} -> {result}"
        )

        # Fire-and-forget to security-service
        asyncio.create_task(self._send_to_service(payload))

    async def _send_to_service(self, payload: dict[str, Any]) -> None:
        """Send audit log to security-service (non-blocking)."""
        if not self._base_url:
            logger.debug("[AUDIT] SECURITY_SERVICE_URL not configured, skipping HTTP send")
            return

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/audit/log",
                    json=payload,
                    headers=self._get_headers(),
                )
                if response.status_code >= 400:
                    logger.warning(f"[AUDIT] Failed to send to security-service: {response.status_code}")
        except httpx.TimeoutException:
            logger.debug("[AUDIT] Timeout sending to security-service (non-critical)")
        except Exception as e:
            logger.warning(f"[AUDIT] Error sending to security-service: {e}")

    def log_sync(
        self,
        action: str | AuditAction,
        actor_type: str = "user",
        actor_id: str | None = None,
        **kwargs,
    ) -> None:
        """
        Synchronous version - logs locally only to avoid blocking.
        For full audit trail, use async log() method.
        """
        if not security_config.audit_enabled:
            return

        if isinstance(action, AuditAction):
            action = action.value

        resource_type = kwargs.get("resource_type")
        resource_id = kwargs.get("resource_id")
        result = kwargs.get("result", "success")

        logger.info(
            f"[AUDIT] {action} by {actor_type}:{actor_id or 'unknown'} "
            f"on {resource_type or '-'}/{resource_id or '-'} -> {result}"
        )


# Global audit client instance
_audit_client = AuditClient()


async def audit_log(
    action: str | AuditAction,
    actor_type: str = "user",
    actor_id: str | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str = "success",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
    request: Any | None = None,
    **kwargs,
) -> None:
    """
    Convenience function to log an audit event.

    Usage:
        await audit_log(
            action="create",
            actor_id=user.id,
            resource_type="proposal",
            resource_id=proposal.id,
        )
    """
    await _audit_client.log(
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_email=actor_email,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        error_message=error_message,
        metadata=metadata,
        request=request,
        **kwargs,
    )


def audit(
    action: str | AuditAction,
    resource_type: str | None = None,
    get_resource_id: Callable | None = None,
    get_actor_id: Callable | None = None,
    get_metadata: Callable | None = None,
):
    """
    Decorator to automatically log audit events.

    Args:
        action: The action type to log
        resource_type: Type of resource being affected
        get_resource_id: Callable to extract resource ID from function args
        get_actor_id: Callable to extract actor ID from function args
        get_metadata: Callable to extract additional metadata from function args

    Usage:
        @audit(action="create", resource_type="proposal")
        async def create_proposal(user: UserContext, data: ProposalCreate):
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

            # Extract actor ID
            actor_id = None
            actor_email = None
            if get_actor_id:
                actor_id = get_actor_id(kwargs)
            else:
                # Try common patterns: user, current_user
                user = kwargs.get('user') or kwargs.get('current_user')
                if user:
                    if hasattr(user, 'id'):
                        actor_id = user.id
                        actor_email = getattr(user, 'email', None)
                    elif isinstance(user, dict):
                        actor_id = user.get('id')
                        actor_email = user.get('email')

            # Extract resource ID
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

            # Extract metadata
            metadata = {}
            if get_metadata:
                metadata = get_metadata(kwargs) or {}

            # Execute the function
            result = "success"
            error_message = None
            try:
                return_value = await func(*args, **kwargs)
            except Exception as e:
                result = "error"
                error_message = str(e)
                raise
            finally:
                await _audit_client.log(
                    action=action,
                    actor_type="user" if actor_id else "anonymous",
                    actor_id=actor_id,
                    actor_email=actor_email,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    result=result,
                    error_message=error_message,
                    metadata=metadata,
                    request=request,
                )

            return return_value

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, just log locally
            request = kwargs.get('request')
            user = kwargs.get('user') or kwargs.get('current_user')
            actor_id = None
            if user:
                actor_id = user.id if hasattr(user, 'id') else user.get('id')

            resource_id = kwargs.get('resource_id') or kwargs.get('id')
            if resource_id is not None:
                resource_id = str(resource_id)

            try:
                return_value = func(*args, **kwargs)
                _audit_client.log_sync(
                    action=action,
                    actor_type="user" if actor_id else "anonymous",
                    actor_id=actor_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    result="success",
                )
                return return_value
            except Exception as e:
                _audit_client.log_sync(
                    action=action,
                    actor_type="user" if actor_id else "anonymous",
                    actor_id=actor_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    result="error",
                    error_message=str(e),
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Legacy aliases for backwards compatibility
audit_logger = _audit_client
audit_action = audit
create_audit_logger = lambda name=None: AuditClient(name)
