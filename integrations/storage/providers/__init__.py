"""
Storage providers.

Available providers:
- LocalStorageProvider: Local filesystem storage
- SupabaseStorageProvider: Supabase Storage (S3-compatible)
"""

from integrations.storage.providers.local import LocalStorageProvider
from integrations.storage.providers.supabase import SupabaseStorageProvider

__all__ = [
    "LocalStorageProvider",
    "SupabaseStorageProvider",
]
