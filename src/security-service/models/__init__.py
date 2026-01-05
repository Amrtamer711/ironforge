"""
Security Service Models.

Exports all models used by the security-service API.
"""

# Auth Models
from .auth import (
    AuthUser,
    UserContext,
    TokenValidationRequest,
    TokenValidationResponse,
    ServiceTokenRequest,
    ServiceTokenResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
)

# RBAC Models
from .rbac import (
    # Enums
    PermissionAction,
    AccessLevel,
    TeamRole,
    # Dataclasses
    Permission,
    Profile,
    PermissionSet,
    Team,
    TeamMember,
    SharingRule,
    RecordShare,
    # Pydantic
    ProfileResponse,
    PermissionSetResponse,
    TeamResponse,
    PermissionResponse,
    UserRBACResponse,
    # Functions
    matches_wildcard,
    has_permission,
    has_any_permission,
    has_all_permissions,
)

# Audit Models
from .audit import (
    # Enums
    AuditAction,
    AuditResult,
    ActorType,
    # Dataclasses
    AuditEvent,
    # Pydantic
    AuditLogRequest,
    AuditLogResponse,
    AuditLogQuery,
    AuditLogListResponse,
)

# API Key Models
from .api_keys import (
    # Enums
    APIKeyScope,
    # Dataclasses
    APIKeyInfo,
    # Pydantic
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdateRequest,
    APIKeyValidateRequest,
    APIKeyValidateResponse,
    APIKeyListResponse,
    APIKeyUsageResponse,
)

# Rate Limit Models
from .rate_limit import (
    # Dataclasses
    RateLimitInfo,
    RateLimitState,
    # Pydantic
    RateLimitCheckRequest,
    RateLimitCheckResponse,
    RateLimitIncrementRequest,
    RateLimitIncrementResponse,
    RateLimitStatusResponse,
)

__all__ = [
    # Auth
    "AuthUser",
    "UserContext",
    "TokenValidationRequest",
    "TokenValidationResponse",
    "ServiceTokenRequest",
    "ServiceTokenResponse",
    "PermissionCheckRequest",
    "PermissionCheckResponse",
    # RBAC Enums
    "PermissionAction",
    "AccessLevel",
    "TeamRole",
    # RBAC Dataclasses
    "Permission",
    "Profile",
    "PermissionSet",
    "Team",
    "TeamMember",
    "SharingRule",
    "RecordShare",
    # RBAC Pydantic
    "ProfileResponse",
    "PermissionSetResponse",
    "TeamResponse",
    "PermissionResponse",
    "UserRBACResponse",
    # RBAC Functions
    "matches_wildcard",
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    # Audit Enums
    "AuditAction",
    "AuditResult",
    "ActorType",
    # Audit Dataclasses
    "AuditEvent",
    # Audit Pydantic
    "AuditLogRequest",
    "AuditLogResponse",
    "AuditLogQuery",
    "AuditLogListResponse",
    # API Key Enums
    "APIKeyScope",
    # API Key Dataclasses
    "APIKeyInfo",
    # API Key Pydantic
    "APIKeyCreateRequest",
    "APIKeyCreateResponse",
    "APIKeyResponse",
    "APIKeyUpdateRequest",
    "APIKeyValidateRequest",
    "APIKeyValidateResponse",
    "APIKeyListResponse",
    "APIKeyUsageResponse",
    # Rate Limit Dataclasses
    "RateLimitInfo",
    "RateLimitState",
    # Rate Limit Pydantic
    "RateLimitCheckRequest",
    "RateLimitCheckResponse",
    "RateLimitIncrementRequest",
    "RateLimitIncrementResponse",
    "RateLimitStatusResponse",
]
