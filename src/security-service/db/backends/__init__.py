"""
Database backends for security-service.

Available backends:
- SupabaseBackend: Uses Security Supabase + UI Supabase (read-only)
"""

from .supabase import SupabaseBackend

__all__ = ["SupabaseBackend"]
