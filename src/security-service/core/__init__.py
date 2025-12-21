"""
Security Service Core Logic.

Business logic layer that uses the database layer for data access.

Usage:
    from core import auth_service, rbac_service, audit_service, api_key_service

    # Validate token and get user context
    result = auth_service.validate_token(token)

    # Check permission
    allowed = rbac_service.check_permission(user_id, "sales:proposals:create")

    # Log audit event
    audit_service.log_event(...)
"""

from .auth import auth_service, AuthService
from .rbac import rbac_service, RBACService
from .audit import audit_service, AuditService
from .api_keys import api_key_service, APIKeyService
from .rate_limit import rate_limit_service, RateLimitService

__all__ = [
    # Services
    "auth_service",
    "rbac_service",
    "audit_service",
    "api_key_service",
    "rate_limit_service",
    # Classes (for typing)
    "AuthService",
    "RBACService",
    "AuditService",
    "APIKeyService",
    "RateLimitService",
]
