"""
API Routers for Security Service.
"""

from .health import router as health_router
from .auth import router as auth_router
from .rbac import router as rbac_router
from .audit import router as audit_router
from .api_keys import router as api_keys_router
from .rate_limit import router as rate_limit_router

__all__ = [
    "health_router",
    "auth_router",
    "rbac_router",
    "audit_router",
    "api_keys_router",
    "rate_limit_router",
]
