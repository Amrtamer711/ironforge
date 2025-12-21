"""
CRM Security SDK

Provides consistent security patterns across all services:
- Trusted header parsing (from unified-ui gateway)
- RBAC permission checking (local, no network)
- Audit logging to security-service (async HTTP)
- API key authentication
- Rate limiting
- FastAPI middleware and dependencies

Install:
    pip install "crm-security[fastapi] @ git+https://github.com/org/CRM.git#subdirectory=src/security/sdk"

Usage:
    from crm_security import (
        require_auth,
        require_permission,
        TrustedUserContext,
        audit_log,
        audit,
    )

    @router.get("/protected")
    async def protected(user: TrustedUserContext = Depends(require_auth)):
        return {"user": user["id"]}

    @audit(action="create", resource_type="proposal")
    async def create_proposal(user: TrustedUserContext, data: ProposalCreate):
        ...

    # Or direct logging
    await audit_log(
        action="create",
        actor_id=user["id"],
        resource_type="proposal",
        resource_id=proposal.id,
    )
"""

# Models
from .models import AuthUser

# Config
from .config import (
    security_config,
    SecurityConfig,
    get_security_config,
)

# Trusted Headers
from .trusted_headers import (
    TrustedUserContext,
    TRUSTED_HEADERS,
    HEADER_PROXY_SECRET,
    HEADER_USER_ID,
    HEADER_USER_EMAIL,
    HEADER_USER_NAME,
    HEADER_USER_PROFILE,
    HEADER_USER_PERMISSIONS,
    HEADER_USER_COMPANIES,
    parse_user_context,
    verify_proxy_secret,
)

# RBAC
from .rbac import (
    matches_wildcard,
    has_permission,
    has_any_permission,
    has_all_permissions,
    PERMISSIONS,
    # Data Access Helpers (5-Level RBAC)
    can_access_user_data,
    can_access_record,
    get_shared_record_ids,
    get_accessible_user_ids,
)

# Auth Dependencies (TrustedUserContext - dict-style access)
from .dependencies import (
    get_current_user,
    require_auth,
    require_permission,
    require_any_permission,
    require_profile,
    require_any_profile,
    require_company_access,
    require_admin,
)

# Auth Dependencies (AuthUser - dataclass-style access)
from .dependencies import (
    get_current_auth_user,
    require_auth_user,
    require_permission_user,
    require_any_permission_user,
    require_profile_user,
    require_any_profile_user,
    require_admin_user,
)

# Inter-Service Auth
from .service_auth import (
    ServiceAuthClient,
    verify_service_token,
    require_service_auth,
    require_service,
)

# Audit Logging
from .audit import (
    AuditAction,
    AuditClient,
    audit_log,
    audit,
    # Legacy aliases
    audit_logger,
    audit_action,
    create_audit_logger,
)

# API Keys (thin client - validates via security-service)
from .api_keys import (
    APIKeyScope,
    APIKeyInfo,
    get_api_key,
    require_api_key,
    api_key_required,  # alias
    # Utility functions
    generate_api_key,
    hash_api_key,
)

# Rate Limiting (thin client - checks via security-service)
from .rate_limit import (
    RateLimitInfo,
    RateLimiter,
    rate_limit,
    get_rate_limiter,
)

# Middleware
from .middleware import (
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    TrustedUserMiddleware,
)

# Context Management
from .context import (
    set_user_context,
    get_user_context,
    clear_user_context,
    get_current_user_id,
    get_current_user_permissions,
    get_current_user_companies,
    get_current_user_profile,
    is_authenticated,
    set_dev_auth_context,
)

__all__ = [
    # Models
    "AuthUser",
    # Config
    "security_config",
    "SecurityConfig",
    "get_security_config",
    # Trusted Headers
    "TrustedUserContext",
    "TRUSTED_HEADERS",
    "HEADER_PROXY_SECRET",
    "HEADER_USER_ID",
    "HEADER_USER_EMAIL",
    "HEADER_USER_NAME",
    "HEADER_USER_PROFILE",
    "HEADER_USER_PERMISSIONS",
    "HEADER_USER_COMPANIES",
    "parse_user_context",
    "verify_proxy_secret",
    # RBAC
    "matches_wildcard",
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    "PERMISSIONS",
    # Data Access Helpers
    "can_access_user_data",
    "can_access_record",
    "get_shared_record_ids",
    "get_accessible_user_ids",
    # Auth Dependencies (TrustedUserContext)
    "get_current_user",
    "require_auth",
    "require_permission",
    "require_any_permission",
    "require_profile",
    "require_any_profile",
    "require_company_access",
    "require_admin",
    # Auth Dependencies (AuthUser)
    "get_current_auth_user",
    "require_auth_user",
    "require_permission_user",
    "require_any_permission_user",
    "require_profile_user",
    "require_any_profile_user",
    "require_admin_user",
    # Inter-Service Auth
    "ServiceAuthClient",
    "verify_service_token",
    "require_service_auth",
    "require_service",
    # Audit
    "AuditAction",
    "AuditClient",
    "audit_log",
    "audit",
    "audit_logger",
    "audit_action",
    "create_audit_logger",
    # API Keys (thin client)
    "APIKeyScope",
    "APIKeyInfo",
    "get_api_key",
    "require_api_key",
    "api_key_required",
    "generate_api_key",
    "hash_api_key",
    # Rate Limiting (thin client)
    "RateLimitInfo",
    "RateLimiter",
    "rate_limit",
    "get_rate_limiter",
    # Middleware
    "SecurityHeadersMiddleware",
    "RequestLoggingMiddleware",
    "TrustedUserMiddleware",
    # Context Management
    "set_user_context",
    "get_user_context",
    "clear_user_context",
    "get_current_user_id",
    "get_current_user_permissions",
    "get_current_user_companies",
    "get_current_user_profile",
    "is_authenticated",
    "set_dev_auth_context",
]
