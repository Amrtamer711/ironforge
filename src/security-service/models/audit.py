"""
Audit Logging Models.

Adapted from shared/security/audit.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

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


class AuditResult(str, Enum):
    """Result of an audited action."""
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class ActorType(str, Enum):
    """Type of actor performing an action."""
    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


# =============================================================================
# DATACLASS MODELS (Internal use)
# =============================================================================

@dataclass
class AuditEvent:
    """
    Represents a single audit log event.

    Adapted from shared/security/audit.py.
    """
    # Who
    actor_type: str  # 'user', 'service', 'system', 'anonymous'
    actor_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None

    # What
    service: str = ""
    action: str = ""
    resource_type: str | None = None
    resource_id: str | None = None

    # Result
    result: str = "success"
    error_message: str | None = None

    # Context
    request_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    request_body: dict | None = None
    response_status: int | None = None
    duration_ms: int | None = None

    # Additional
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "actor_email": self.actor_email,
            "actor_ip": self.actor_ip,
            "service": self.service,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "result": self.result,
            "error_message": self.error_message,
            "request_id": self.request_id,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "request_body": self.request_body,
            "response_status": self.response_status,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


# =============================================================================
# PYDANTIC MODELS (API Request/Response)
# =============================================================================

class AuditLogRequest(BaseModel):
    """Request to create an audit log entry."""
    actor_type: ActorType = ActorType.USER
    actor_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    service: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    result: AuditResult = AuditResult.SUCCESS
    error_message: str | None = None
    request_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    response_status: int | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogResponse(BaseModel):
    """Audit log entry returned from API."""
    id: str
    timestamp: datetime
    actor_type: str
    actor_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    service: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    result: str
    error_message: str | None = None
    request_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    response_status: int | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogQuery(BaseModel):
    """Query parameters for searching audit logs."""
    actor_id: str | None = None
    actor_type: ActorType | None = None
    service: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    result: AuditResult | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs."""
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
