"""
RBAC providers.

Available providers:
- DatabaseRBACProvider: Database-backed RBAC using the unified schema
- StaticRBACProvider: Static configuration-based RBAC (for development)
"""

from integrations.rbac.providers.database import DatabaseRBACProvider
from integrations.rbac.providers.static import StaticRBACProvider

__all__ = [
    "DatabaseRBACProvider",
    "StaticRBACProvider",
]
