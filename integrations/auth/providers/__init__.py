"""
Authentication providers.

Available providers:
- SupabaseAuthProvider: Production Supabase Auth
- LocalDevAuthProvider: Local development with hardcoded users
"""

from integrations.auth.providers.local_dev import LocalDevAuthProvider
from integrations.auth.providers.supabase import SupabaseAuthProvider

__all__ = [
    "SupabaseAuthProvider",
    "LocalDevAuthProvider",
]
