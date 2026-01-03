"""
RBAC providers.

Available providers:
- DatabaseRBACProvider: Database-backed RBAC using trusted proxy headers
"""

from integrations.rbac.providers.database import DatabaseRBACProvider

__all__ = [
    "DatabaseRBACProvider",
]
